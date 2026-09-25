"""Shared active-task-pointer loading for the Claude Code hook scripts under runtime/hooks/.

Every hook that acts on a governed task (session_start_check, precompact_checkpoint,
pretooluse_gate, session_stop_handoff) needs the same three steps: read the pointer,
validate its store directory exists, open the store and fetch the run. Centralized
here so that logic -- and its error message -- has one home instead of four.
"""
import json
from pathlib import Path


def load_active_task(pointer_path):
    """Read an active-task pointer file and open its store.

    Returns (pointer, store, run). All three are None if no pointer file exists.
    `run` is None if the pointer exists but its run_id is not found in the store.
    Raises ValueError if the pointer exists but its store directory is missing.
    """
    pointer_path = Path(pointer_path)
    if not pointer_path.exists():
        return None, None, None
    pointer = json.loads(pointer_path.read_text(encoding='utf-8'))
    from .markers import store_dir_of
    store_dir = store_dir_of(pointer_path, pointer)
    if not store_dir.is_dir():
        raise ValueError('Active-task store is missing')
    from .store import RuntimeStore
    store = RuntimeStore(str(store_dir))
    run = store.get_run(pointer['run_id'])
    return pointer, store, run


UNFINISHED = ('RUNNING', 'BLOCKED')
# Paths an agent may write between tasks while a run is open: work-item and
# project-context documents, and handoff notes. Never the ledger itself.
UNGOVERNED_WRITE_PREFIXES = ('agentic/data/', '.agent/')


def open_runs(runs_dir):
    """(run_id, title, status) for every unfinished run in a store; unreadable runs are skipped."""
    runs_dir = Path(runs_dir)
    if not runs_dir.is_dir():
        return []
    from .store import RuntimeStore
    return [(r['run_id'], r.get('title', ''), r['status']) for r in RuntimeStore(str(runs_dir)).list_runs()
            if r.get('status') in UNFINISHED]


def ungoverned_write_denial(repo_root, file_path, runs_dir, policy):
    """Reason to deny a native write made while no governed task is active, or None.

    Without this, skipping `task-start` skipped every control: a run could sit at
    IMPLEMENTATION while code changed with no task, permissions, or timing. Writes
    outside the project (scratch files, agent memory) and to documents are fine.
    """
    from .paths import PROTECTED_DIRS_REL
    root = Path(repo_root).resolve()
    if not file_path:
        return None
    target = Path(file_path)
    target = (target if target.is_absolute() else root / target).resolve()
    if not target.is_relative_to(root):
        return None
    relative = target.relative_to(root).as_posix()
    if any(relative.startswith(d.as_posix() + '/') for d in PROTECTED_DIRS_REL):
        return 'Direct writes to the runtime ledger are denied; use the runtime CLI'
    if not policy.get('require_task_for_code_writes', True) or relative.startswith(UNGOVERNED_WRITE_PREFIXES):
        return None
    runs = open_runs(runs_dir)
    if not runs:
        return None
    run_id, title, status = runs[0]
    more = f' (+{len(runs) - 1} more open)' if len(runs) > 1 else ''
    return (f'Governed run {run_id} "{title}" is {status}{more} but no task is active, so this code write '
            f'is unrecorded. Start one: `agentic_runtime.cli task-start {run_id} --skill implementation-agent` '
            f'(or the stage\'s skill), or finish/cancel the run. Documents under agentic/data/ and '
            f'.agent/sessions/ stay writable (.agent/state/ and .agent/local/ are written only by the CLI); '
            f'set require_task_for_code_writes=false in platform.json to opt out.')
