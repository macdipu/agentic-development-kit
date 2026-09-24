#!/usr/bin/env python3
"""Claude Code SessionStart hook: surface any midflight governed task/run.

Wired via .claude/settings.json (event SessionStart, no matcher -- runs on
startup/resume/clear alike). Order of checks:

1. .agent/runtime/active-task.json present -> a task-start was never
   closed by task-finish/task-fail/cancel/recover. Report it as midflight.
2. No active-task pointer, but the default run store
   (.agent/runtime/runs/) has a run whose status is RUNNING or
   BLOCKED -> report the most recently updated one as midflight.
3. Otherwise -> nothing in flight, clear to start the next work item.

Unreadable state is reported as UNKNOWN with explicit recovery instructions.
The session remains available for diagnosis, but must not assume there is no work.

Also surfaces a condensed `.agent/HANDOFF.md` (plus the latest `.agent/sessions/*.md`
entry only when it differs) as pickup context -- see handoff.pickup_summary. A note
about a different run than the midflight one is flagged stale. The full record stays
on disk: `agentic_runtime.cli pickup --full`.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'runtime/python'))
from agentic_runtime.paths import REPO_ROOT, ACTIVE_TASK_POINTER, RUNS_DIR as DEFAULT_RUNS_DIR
UNFINISHED_STATUSES = {'RUNNING', 'BLOCKED'}


def _emit(context):
    print(json.dumps({'hookSpecificOutput': {
        'hookEventName': 'SessionStart',
        'additionalContext': context,
    }}))
    return 0


def _check_active_task():
    from agentic_runtime.hooks_support import load_active_task
    pointer, _store, run = load_active_task(ACTIVE_TASK_POINTER)
    if pointer is None:
        return None, None
    detail = f"run_id={pointer['run_id']} task_id={pointer['task_id']}"
    if run:
        detail += f" stage={run.stage} status={run.status} title={run.title!r}"
    return (
        'MIDFLIGHT TASK: an active governed task was never closed '
        f'({detail}). Resume it (continue the work, then `task-finish` or '
        '`task-fail`) before starting anything new. Do not start a new run '
        'for this work item.'
    ), pointer['run_id']


def _check_unfinished_run():
    if not DEFAULT_RUNS_DIR.is_dir():
        return None, None
    from agentic_runtime.store import RuntimeStore
    store = RuntimeStore(str(DEFAULT_RUNS_DIR))
    runs = store.list_runs()
    unfinished = [r for r in runs if r['status'] in UNFINISHED_STATUSES]
    if not unfinished:
        return None, None
    unfinished.sort(key=lambda r: r['updated_at'], reverse=True)
    run = unfinished[0]
    return (
        'MIDFLIGHT RUN: the most recently updated workflow run is not '
        f"COMPLETED (run_id={run['run_id']} stage={run['stage']} "
        f"status={run['status']} title={run['title']!r}). Resume it "
        '(`agentic_runtime.cli show <run_id>`, then continue or `recover`) '
        'before starting the next work item.'
    ), run['run_id']


def _check_handoff(active_run_id):
    from agentic_runtime import handoff
    return handoff.pickup_summary(REPO_ROOT, active_run_id=active_run_id)


def main():
    run_id = None
    try:
        context, run_id = _check_active_task()
        if context is None:
            context, run_id = _check_unfinished_run()
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
    try:
        handoff_context = _check_handoff(run_id)
    except Exception as exc:
        handoff_context = f'Could not read cross-agent handoff notes: {exc}'
    if handoff_context:
        context = f'{context}\n\n{handoff_context}'
    return _emit(context)


if __name__ == '__main__':
    raise SystemExit(main())
