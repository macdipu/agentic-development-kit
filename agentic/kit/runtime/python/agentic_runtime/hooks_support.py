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
    pointer = json.loads(pointer_path.read_text())
    if not Path(pointer['store_dir']).is_dir():
        raise ValueError('Active-task store is missing')
    from .store import RuntimeStore
    store = RuntimeStore(pointer['store_dir'])
    run = store.get_run(pointer['run_id'])
    return pointer, store, run
