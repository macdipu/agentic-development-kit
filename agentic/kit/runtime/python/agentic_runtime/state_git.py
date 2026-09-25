"""Committing agent state with the project's own branches.

`.agent/state/` and `.agent/sessions/` are committed like source: they reach the
other machine through the same `git push`/`git pull` as the code. Three paths:

- `commit_state`: a state-only commit (`chore(agent): ...`, `Commit-Trigger:
  agent-state`) at task end, so ledger changes never wait for a code commit. It
  commits only those paths (`git commit --only`), leaving anything else the user
  staged untouched. Configurable: `auto_commit_state` in config/state.json.
- `cli.py commit` includes pending state in the task's own commit.
- `handoff`: before switching machines, commit everything (work in progress
  included, `Commit-Trigger: handoff`) and push the current branch.

Nothing here pushes except `handoff`, which the user runs to switch machines.
"""
import json
import os
import subprocess
import tempfile
from pathlib import Path

from . import commits

STATE_PATHS = ('.agent/state', '.agent/sessions')


def config(kit_dir):
    try:
        return json.loads((Path(kit_dir) / 'config/state.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def _git(repo, *args, timeout=120):
    # Never block on a credential prompt: a hook or CLI call must fail, not hang.
    env = dict(os.environ, GIT_TERMINAL_PROMPT='0')
    return subprocess.run(['git', *args], cwd=repo, capture_output=True, text=True, timeout=timeout,
                          encoding='utf-8', errors='replace', env=env)


def is_repo(repo):
    try:
        result = _git(repo, 'rev-parse', '--is-inside-work-tree', timeout=10)
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0 and result.stdout.strip() == 'true'


def _existing(repo, paths):
    return [p for p in paths if (Path(repo) / p).exists()]


def stage_state(repo):
    paths = _existing(repo, STATE_PATHS)
    if paths:
        _git(repo, 'add', '-A', '--', *paths)
    return paths


def pending_state(repo):
    """Uncommitted changes under the state paths (porcelain lines)."""
    paths = _existing(repo, STATE_PATHS)
    if not paths or not is_repo(repo):
        return []
    return [l for l in _git(repo, 'status', '--porcelain', '--untracked-files=all', '--', *paths).stdout.splitlines() if l]


def _commit_file(repo, message, *args):
    handle = tempfile.NamedTemporaryFile('w', suffix='.commitmsg', delete=False, encoding='utf-8', newline='\n')
    try:
        with handle:
            handle.write(message)
        return _git(repo, 'commit', '-F', handle.name, *args, timeout=600)
    finally:
        Path(handle.name).unlink(missing_ok=True)


def commit_state(repo, subject, run_id='', kit_dir=None, force=False):
    """State-only commit. Returns commit info, or {'committed': False, 'reason': ...}."""
    if kit_dir is not None and not force and not config(kit_dir).get('auto_commit_state', True):
        return {'committed': False, 'reason': 'auto_commit_state is off'}
    if not is_repo(repo):
        return {'committed': False, 'reason': 'not a git work tree'}
    paths = stage_state(repo)
    if not paths or _git(repo, 'diff', '--cached', '--quiet', '--', *paths).returncode == 0:
        return {'committed': False, 'reason': 'no agent state changes'}
    message = commits.render_message(type='chore', scope='agent', subject=subject[:60].rstrip('.'),
                                     trigger='agent-state', run=run_id)
    result = _commit_file(repo, message, '--only', '--', *paths)
    if result.returncode:
        # Leave the index as the user had it; the state stays in the working tree for the next commit.
        _git(repo, 'reset', '-q', '--', *paths)
        detail = (result.stderr or result.stdout).strip() or 'no output'
        return {'committed': False, 'reason': f'git commit failed (exit {result.returncode}): {detail}'}
    return {'committed': True, **commits.commit_info(repo, 'HEAD')}


def branch_status(repo, fetch=False):
    """(branch, upstream, ahead, behind) of the current branch; fetch first when asked."""
    if not is_repo(repo):
        return None
    if fetch:
        try:
            _git(repo, 'fetch', '--quiet', timeout=20)
        except (OSError, subprocess.SubprocessError):
            pass
    branch = _git(repo, 'rev-parse', '--abbrev-ref', 'HEAD', timeout=10).stdout.strip()
    upstream = _git(repo, 'rev-parse', '--abbrev-ref', '--symbolic-full-name', '@{u}', timeout=10)
    if upstream.returncode:
        return {'branch': branch, 'upstream': None, 'ahead': None, 'behind': None}
    counts = _git(repo, 'rev-list', '--left-right', '--count', 'HEAD...@{u}', timeout=10).stdout.split()
    ahead, behind = (int(counts[0]), int(counts[1])) if len(counts) == 2 else (None, None)
    return {'branch': branch, 'upstream': upstream.stdout.strip(), 'ahead': ahead, 'behind': behind}


def handoff(repo, subject, run_id='', push=True):
    """Commit all work (tracked and untracked, gitignore respected) and push the
    current branch, so another machine continues from `git pull`."""
    if not is_repo(repo):
        raise ValueError('handoff needs a git work tree')
    status = branch_status(repo)
    if push and (not status or status['branch'] == 'HEAD'):
        raise ValueError('handoff needs a branch to push (detached HEAD); check out a branch or pass --no-push')
    added = _git(repo, 'add', '-A')
    if added.returncode:
        raise ValueError('git add failed: ' + added.stderr.strip())
    staged = [f for f in _git(repo, 'diff', '--cached', '--name-only', '-z').stdout.split('\0') if f]
    report = {'files': staged, 'committed': False, 'pushed': False}
    if staged:
        message = commits.render_message(type='chore', scope='handoff', subject=subject[:60].rstrip('.'),
                                         body='Work in progress committed to continue on another machine.',
                                         trigger='handoff', run=run_id)
        result = _commit_file(repo, message)
        if result.returncode:
            raise ValueError('git commit failed: ' + (result.stderr or result.stdout).strip())
        report.update(committed=True, commit=commits.commit_info(repo, 'HEAD'))
    if push:
        if status['upstream']:
            args = ['push']
        else:
            remotes = _git(repo, 'remote').stdout.split()
            if not remotes:
                raise ValueError('Committed, but there is no git remote to push to')
            args = ['push', '-u', 'origin' if 'origin' in remotes else remotes[0], 'HEAD']
        result = _git(repo, *args, timeout=300)
        if result.returncode:
            raise ValueError('Committed, but git push failed (push manually before switching): '
                             + (result.stderr or result.stdout).strip())
        report['pushed'] = True
    return report


def pull(repo):
    """Fast-forward the current branch from its upstream; refuses to merge or rebase."""
    status = branch_status(repo)
    if not status or not status['upstream']:
        return {'pulled': False, 'reason': 'no upstream branch'}
    result = _git(repo, 'pull', '--ff-only', timeout=300)
    if result.returncode:
        raise ValueError('git pull --ff-only failed; reconcile the branch first: ' + (result.stderr or result.stdout).strip())
    return {'pulled': True, 'output': result.stdout.strip()}
