"""Which clone is working on which run -- the cross-machine lock, carried by git.

Claims are append-only event files, `.agent/state/claims/<run_id>/<stamp>-<id>.json`,
committed with the rest of `.agent/state/`. The newest event decides: a `claim`
(or `takeover`) by a clone makes it the holder until `expires_at`; that clone's
`release` frees the run. Because files are only added, two machines' claim
histories merge without conflicts on `git pull`.

A clone claims a run at its first `task-start` (committed right away) and keeps
it across tasks until the run completes or is cancelled, or `handoff` passes it on.
Machine B therefore sees machine A's claim as soon as any commit of A's after that
point is pushed and pulled -- a claim protects only as far as git has carried it.
An expired claim of another clone is taken over automatically, with the expiry
recorded as the reason. The clone id is per checkout and never committed
(`.agent/local/clone-id`).
"""
import json
import os
import socket
import subprocess
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

_STAMP = '%Y%m%dT%H%M%S%fZ'
DEFAULT_TTL_SECONDS = 86400  # a run is held across tasks; refreshed on every task start/end


class ClaimHeld(ValueError):
    def __init__(self, run_id, claim):
        self.claim = claim
        super().__init__(
            f"Run {run_id} is claimed by {claim.get('machine')} ({claim.get('operator')}, {claim.get('agent')}) "
            f"until {claim.get('expires_at')}. Continue it there, or ask that machine to run "
            f"`agentic_runtime.cli handoff`, or take it over explicitly: "
            f"`agentic_runtime.cli resume {run_id} --takeover --reason \"...\"`.")


def _now():
    return datetime.now(timezone.utc)


def _operator(repo):
    def cfg(key):
        try:
            result = subprocess.run(['git', 'config', key], cwd=repo, capture_output=True, text=True,
                                    timeout=10, encoding='utf-8', errors='replace')
            return result.stdout.strip() if result.returncode == 0 else ''
        except (OSError, subprocess.SubprocessError):
            return ''
    name, email = cfg('user.name'), cfg('user.email')
    return f'{name} <{email}>' if name and email else (name or email or '(unknown)')


class Claims:
    def __init__(self, claims_dir, local_dir, repo, ttl_seconds=DEFAULT_TTL_SECONDS):
        self.dir = Path(claims_dir)
        self.local_dir = Path(local_dir)
        self.repo = Path(repo)
        self.ttl = ttl_seconds

    def clone_id(self):
        path = self.local_dir / 'clone-id'
        try:
            return path.read_text(encoding='utf-8').strip()
        except OSError:
            path.parent.mkdir(parents=True, exist_ok=True)
            value = uuid.uuid4().hex
            path.write_text(value + '\n', encoding='utf-8', newline='\n')
            return value

    def identity(self):
        return {'clone_id': self.clone_id(), 'machine': socket.gethostname(), 'operator': _operator(self.repo)}

    def _events(self, run_id):
        directory = self.dir / run_id
        if not directory.is_dir():
            return []
        events = []
        for path in sorted(directory.glob('*.json')):
            try:
                events.append(json.loads(path.read_text(encoding='utf-8')))
            except (OSError, ValueError):
                continue
        return events

    def current(self, run_id):
        """The holder's latest claim event, or None when free. Expired claims are
        returned with `expired: True` (still attributed, no longer binding)."""
        holder = None
        for event in self._events(run_id):
            if event.get('action') in ('claim', 'takeover'):
                holder = event
            elif event.get('action') == 'release' and holder and event.get('clone_id') == holder.get('clone_id'):
                holder = None
        if holder is None:
            return None
        return {**holder, 'expired': holder.get('expires_at', '') < _now().isoformat(),
                'mine': holder.get('clone_id') == self.clone_id()}

    def _write(self, run_id, event):
        directory = self.dir / run_id
        directory.mkdir(parents=True, exist_ok=True)
        names = sorted(p.name for p in directory.glob('*.json'))
        stamp = _now()
        if names:
            try:
                last = datetime.strptime(names[-1].split('-', 1)[0], _STAMP).replace(tzinfo=timezone.utc)
                stamp = max(stamp, last + timedelta(microseconds=1))
            except ValueError:
                pass
        name = f"{stamp.strftime(_STAMP)}-{uuid.uuid4().hex[:8]}.json"
        tmp = directory / f'.{name}.tmp'
        tmp.write_text(json.dumps(event, indent=2, sort_keys=True) + '\n', encoding='utf-8', newline='\n')
        os.replace(tmp, directory / name)
        return event

    def holder_other(self, run_id):
        """Another clone's unexpired claim on run_id, or None."""
        current = self.current(run_id)
        return current if current and not current['mine'] and not current['expired'] else None

    def claim(self, run_id, agent='', task=None, takeover=False, reason=''):
        """Acquire or refresh this clone's claim. Raises ClaimHeld for another clone's
        unexpired claim unless an explicit, reasoned takeover is requested."""
        current = self.current(run_id)
        me = self.identity()
        if current and not current['mine']:
            if not current['expired'] and not takeover:
                raise ClaimHeld(run_id, current)
            if not reason.strip():
                if not current['expired']:
                    raise ValueError("Taking over another clone's claim requires --reason (it is recorded)")
                reason = f"previous claim expired at {current.get('expires_at')}"
        now = _now()
        event = {**me, 'action': 'claim', 'run_id': run_id, 'agent': agent, 'task': task,
                 'at': now.isoformat(), 'expires_at': (now + timedelta(seconds=self.ttl)).isoformat()}
        if current and not current['mine']:
            event['action'] = 'takeover'
            event['previous'] = {k: current.get(k) for k in ('clone_id', 'machine', 'operator', 'agent', 'expires_at')}
            event['reason'] = reason
            event['previous_expired'] = current['expired']
        elif current and current['mine'] and current.get('expires_at', '') > (now + timedelta(seconds=self.ttl / 2)).isoformat():
            return current  # fresh enough; no new file for every refresh (renewed past half its lifetime)
        return self._write(run_id, event)

    def release(self, run_id):
        current = self.current(run_id)
        if not current or not current['mine']:
            return None
        return self._write(run_id, {**self.identity(), 'action': 'release', 'run_id': run_id, 'at': _now().isoformat()})

    def all(self):
        found = []
        for directory in sorted(self.dir.iterdir()) if self.dir.is_dir() else []:
            current = self.current(directory.name) if directory.is_dir() else None
            if current:
                found.append(current)
        return found

    def report(self):
        lines = []
        for claim in self.all():
            who = 'THIS CLONE' if claim['mine'] else f"{claim.get('machine')} ({claim.get('operator')}, {claim.get('agent')})"
            state = 'EXPIRED' if claim['expired'] else 'until ' + claim.get('expires_at', '?')
            lines.append(f"- {claim['run_id']}: claimed by {who}, {state}")
        return lines


def default_claims(repo_root=None, kit_dir=None):
    from .paths import CLAIMS_DIR, KIT, LOCAL_DIR, REPO_ROOT
    config = {}
    path = Path(kit_dir or KIT) / 'config/state.json'
    try:
        config = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        pass
    root = Path(repo_root) if repo_root else REPO_ROOT
    return Claims(root / '.agent/state/claims' if repo_root else CLAIMS_DIR,
                  root / '.agent/local' if repo_root else LOCAL_DIR, root,
                  config.get('claim_ttl_seconds', DEFAULT_TTL_SECONDS))
