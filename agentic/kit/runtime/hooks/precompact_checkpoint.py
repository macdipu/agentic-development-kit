#!/usr/bin/env python3
"""Claude Code PreCompact hook: checkpoint the active run before context is lost.

Wired via .claude/settings.json (event PreCompact, matcher "*" -- fires before
every compaction, manual or automatic). Compaction is the closest local signal
to "the session is running out of room": Claude Code itself does not expose a
context-budget percentage to hooks, so this is the trigger point, not a 95%
threshold.

What it does deterministically (safe, no judgment involved):
  - If a governed task is active (agentic/data/runtime/state/active-task.json),
    write an audit event + checkpoint row recording the run's stage/status at
    this moment, so the DB reflects "still open, last seen here" rather than
    going silent.

What it cannot do deterministically -- "update all docs" and "pick a smaller
task" both require judgment about what changed and what's left, which a hook
script has no visibility into. Instead it returns a `systemMessage`, the one
hook-output field documented to reach Claude across every event type, telling
the agent to do those two things itself before the turn ends.

Never blocks compaction: any error here is reported in the message, not a
`decision: block`, since blocking on a hook bug would strand the session with
no working state at all.
"""
import json
import sys
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'runtime/python'))
from agentic_runtime.paths import KIT, ACTIVE_TASK_POINTER

NUDGE = (
    'Context compaction is about to happen. Before this turn ends: '
    '(1) update every doc this session touched -- work-item status, '
    'README/AGENTS notes, any tracked plan -- so the current state is '
    'readable after compaction, not just in scrollback; '
    '(2) do not start new large work now -- scope whatever is left to the '
    'smallest remaining subtask that can actually finish, and say so '
    'explicitly if you are narrowing scope for this reason.'
)


def _emit(message):
    print(json.dumps({'systemMessage': message}))
    return 0


def _checkpoint_active_task():
    if not ACTIVE_TASK_POINTER.exists():
        return None
    pointer = json.loads(ACTIVE_TASK_POINTER.read_text())
    if not Path(pointer['db']).is_file():
        raise ValueError('Active-task database is missing')
    sys.path.insert(0, str(KIT / 'runtime/python'))
    from agentic_runtime.store import RuntimeStore
    store = RuntimeStore(pointer['db'])
    try:
        run = store.get_run(pointer['run_id'])
        if run is None:
            return None
        ts = datetime.now(timezone.utc).isoformat()
        with store.transaction():
            store.checkpoint(run.run_id, run.stage, run.status, {'reason': 'precompact'}, ts)
            store.audit(run.run_id, 'precompact_checkpoint', {'stage': run.stage, 'status': run.status}, ts)
        return f"Checkpointed active run {run.run_id} (stage={run.stage}, status={run.status})."
    finally:
        store.conn.close()


def main():
    try:
        checkpoint_note = _checkpoint_active_task()
    except Exception as exc:
        checkpoint_note = f'Could not checkpoint active-task state (fail open): {exc}'
    message = NUDGE if checkpoint_note is None else f'{checkpoint_note} {NUDGE}'
    return _emit(message)


if __name__ == '__main__':
    raise SystemExit(main())
