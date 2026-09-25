"""Commit message format and commit log for governed work (see policies/commit-policy.md).

Messages are Conventional Commits plus git trailers that carry traceability
(request -> work item -> task -> run -> commit) and *why* the commit was made:
`Commit-Trigger: task-finish` (one commit per finished task, checks green) or
`Commit-Trigger: user-request` (the user explicitly asked). Because the trigger
lives in the commit itself, the session log is derived from git alone and stays
readable on any platform and machine.
"""
import re
import subprocess
from pathlib import Path
from typing import List, Optional

COMMIT_TYPES = ('feat', 'fix', 'refactor', 'perf', 'test', 'docs', 'build', 'ci', 'chore', 'revert', 'style')
# task-finish / user-request: code commits (commit policy). agent-state: the runtime's
# own state-only commit at task end. handoff: work in progress committed to switch machines.
TRIGGERS = ('task-finish', 'user-request', 'agent-state', 'handoff')
MAX_HEADER = 72
TRAILER_KEYS = ('Work-Item', 'Task', 'Run', 'Commit-Trigger')
_SCOPE = re.compile(r'^[a-z0-9][a-z0-9._/-]*$')
_FIELD_SEP = '\x1f'
_RECORD_SEP = '\x1e'


_TRAILER = re.compile(r'^[A-Za-z][A-Za-z0-9-]*: \S.*$')


def render_message(*, type: str, subject: str, trigger: str, scope: str = '', body: str = '',
                   work_item: str = '', task: str = '', run: str = '', breaking: bool = False,
                   extra_trailers: Optional[List[str]] = None) -> str:
    """Policy-conformant message. `extra_trailers` (e.g. platform attribution such as
    `Co-Authored-By: ...`) join the same trailer block after the traceability trailers --
    a blank line between them would split the block and hide Commit-Trigger from git."""
    if type not in COMMIT_TYPES:
        raise ValueError(f'type must be one of {COMMIT_TYPES}, got {type!r}')
    if trigger not in TRIGGERS:
        raise ValueError(f'trigger must be one of {TRIGGERS}, got {trigger!r}')
    subject = subject.strip()
    if not subject or '\n' in subject:
        raise ValueError('subject must be one non-empty line')
    if subject.endswith('.'):
        raise ValueError('subject must not end with a period')
    if scope and not _SCOPE.match(scope):
        raise ValueError(f'scope must be lowercase kebab/path form, got {scope!r}')
    header = f"{type}{f'({scope})' if scope else ''}{'!' if breaking else ''}: {subject}"
    if len(header) > MAX_HEADER:
        raise ValueError(f'header is {len(header)} chars; keep it <= {MAX_HEADER}')
    trailers = [f'{key}: {value.strip()}' for key, value in
                (('Work-Item', work_item), ('Task', task), ('Run', run), ('Commit-Trigger', trigger))
                if value.strip()]
    for extra in extra_trailers or []:
        extra = extra.strip()
        if not _TRAILER.match(extra) or '\n' in extra:
            raise ValueError(f'trailer must be one "Key: value" line, got {extra!r}')
        if extra.split(':', 1)[0] in TRAILER_KEYS:
            raise ValueError(f'use the dedicated option for the {extra.split(":", 1)[0]} trailer')
        trailers.append(extra)
    parts = [header]
    if body.strip():
        parts.append(body.strip())
    parts.append('\n'.join(trailers))
    return '\n\n'.join(parts) + '\n'


def commit(repo_root, message: str, paths: Optional[List[str]] = None, include_state: bool = True) -> dict:
    """Stage exactly `paths` (when given), then `git commit -F <file>` with an already
    validated message. Nothing reaches git until the message is valid, and git's own
    failure (hooks, nothing staged) is surfaced instead of committing error text.
    Pending agent state (.agent/state, .agent/sessions) joins the task's commit, so
    the ledger travels with the code it describes."""
    import tempfile
    root = Path(repo_root)
    def git(*args, timeout=120):
        return subprocess.run(['git', *args], cwd=root, capture_output=True, text=True,
                              timeout=timeout, encoding='utf-8', errors='replace')
    if paths:
        added = git('add', '--', *paths)
        if added.returncode:
            raise ValueError('git add failed: ' + (added.stderr or added.stdout).strip())
    if git('diff', '--cached', '--quiet').returncode == 0:
        raise ValueError('Nothing staged to commit; pass --path for the task\'s files')
    if include_state:
        state = [p for p in ('.agent/state', '.agent/sessions') if (root / p).exists()]
        if state:
            git('add', '-A', '--', *state)
    handle = tempfile.NamedTemporaryFile('w', suffix='.commitmsg', delete=False, encoding='utf-8', newline='\n')
    try:
        with handle:
            handle.write(message)
        # Hooks run; never --no-verify (commit policy). Hooks may be slow: generous timeout.
        result = git('commit', '-F', handle.name, timeout=600)
    finally:
        Path(handle.name).unlink(missing_ok=True)
    if result.returncode:
        raise ValueError('git commit failed: ' + (result.stderr or result.stdout).strip())
    return commit_info(root, 'HEAD')


def _git(repo_root, *args) -> Optional[str]:
    result = subprocess.run(['git', *args], cwd=Path(repo_root), capture_output=True, text=True, timeout=10, encoding='utf-8', errors='replace')
    return result.stdout if result.returncode == 0 else None


def _log(repo_root, *rev_args) -> Optional[List[dict]]:
    trailer_fmt = _FIELD_SEP.join(f'%(trailers:key={key},valueonly,separator=%x2C)' for key in TRAILER_KEYS)
    out = _git(repo_root, 'log', f'--format=%h{_FIELD_SEP}%s{_FIELD_SEP}{trailer_fmt}{_RECORD_SEP}', *rev_args)
    if out is None:
        return None
    commits = []
    for record in out.split(_RECORD_SEP):
        fields = record.strip('\n').split(_FIELD_SEP)
        if len(fields) != 2 + len(TRAILER_KEYS):
            continue
        sha, subject, *values = fields
        commit = {'sha': sha, 'subject': subject}
        commit.update({key.lower().replace('-', '_'): value.strip() for key, value in zip(TRAILER_KEYS, values)})
        commits.append(commit)
    return commits


def commit_info(repo_root, rev: str = 'HEAD') -> dict:
    commits = _log(repo_root, '-1', rev, '--')
    if not commits:
        raise ValueError(f'Unknown commit {rev!r}')
    return commits[0]


def commits_since(repo_root, base: Optional[str], fallback_limit: int = 20) -> List[dict]:
    """Commits after `base` (the previous session's HEAD), newest first.

    With no usable base (first session, or history rewritten) falls back to the
    last `fallback_limit` commits rather than guessing a range."""
    if base and _git(repo_root, 'merge-base', '--is-ancestor', base, 'HEAD') is not None:
        return _log(repo_root, f'{base}..HEAD') or []
    return _log(repo_root, f'--max-count={fallback_limit}') or []


def format_commit_lines(commits: List[dict]) -> List[str]:
    lines = []
    for commit in commits:
        tags = [commit[key] for key in ('commit_trigger', 'work_item', 'task') if commit.get(key)]
        suffix = f" [{' | '.join(tags)}]" if tags else ' [no Commit-Trigger]'
        lines.append(f"{commit['sha']} {commit['subject']}{suffix}")
    return lines
