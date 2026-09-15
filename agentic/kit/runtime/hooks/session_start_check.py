#!/usr/bin/env python3
"""Claude Code SessionStart hook: surface any midflight governed task/run.

Wired via .claude/settings.json (event SessionStart, no matcher -- runs on
startup/resume/clear alike). Order of checks:

1. agentic/data/runtime/state/active-task.json present -> a task-start was never
   closed by task-finish/task-fail/cancel/recover. Report it as midflight.
2. No active-task pointer, but the default run DB
   (agentic/data/runtime/state/agentic.db) has a run whose status is RUNNING or
   BLOCKED -> report the most recently updated one as midflight.
3. Otherwise -> nothing in flight, clear to start the next work item.

Unreadable state is reported as UNKNOWN with explicit recovery instructions.
The session remains available for diagnosis, but must not assume there is no work.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'runtime/python'))
from agentic_runtime.paths import KIT, ACTIVE_TASK_POINTER, DB as DEFAULT_DB
UNFINISHED_STATUSES = {'RUNNING', 'BLOCKED'}


def _emit(context):
    print(json.dumps({'hookSpecificOutput': {
        'hookEventName': 'SessionStart',
        'additionalContext': context,
    }}))
    return 0


def _check_active_task():
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
    finally:
        store.conn.close()
    detail = f"run_id={pointer['run_id']} task_id={pointer['task_id']}"
    if run:
        detail += f" stage={run.stage} status={run.status} title={run.title!r}"
    return (
        'MIDFLIGHT TASK: an active governed task was never closed '
        f'({detail}). Resume it (continue the work, then `task-finish` or '
        '`task-fail`) before starting anything new. Do not start a new run '
        'for this work item.'
    )


def _check_unfinished_run():
    if not DEFAULT_DB.exists():
        return None
    sys.path.insert(0, str(KIT / 'runtime/python'))
    from agentic_runtime.store import RuntimeStore
    store = RuntimeStore(str(DEFAULT_DB))
    try:
        runs = store.list_runs()
    finally:
        store.conn.close()
    unfinished = [r for r in runs if r['status'] in UNFINISHED_STATUSES]
    if not unfinished:
        return None
    unfinished.sort(key=lambda r: r['updated_at'], reverse=True)
    run = unfinished[0]
    return (
        'MIDFLIGHT RUN: the most recently updated workflow run is not '
        f"COMPLETED (run_id={run['run_id']} stage={run['stage']} "
        f"status={run['status']} title={run['title']!r}). Resume it "
        '(`agentic_runtime.cli show <run_id>`, then continue or `recover`) '
        'before starting the next work item.'
    )


def main():
    try:
        context = _check_active_task()
        if context is None:
            context = _check_unfinished_run()
        if context is None:
            context = (
                'No midflight task or unfinished run found. Clear to start '
                'the next work item.'
            )
    except Exception as exc:
        context = (
            'Midflight state is UNKNOWN. Do not start new governed work. '
            f'Run doctor and reconcile the database/marker: {exc}'
        )
    return _emit(context)


if __name__ == '__main__':
    raise SystemExit(main())
