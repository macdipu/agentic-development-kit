#!/usr/bin/env python3
"""Claude Code Stop hook: write cross-agent-platform handoff notes for a governed run.

Wired via .claude/settings.json (event Stop, matcher "*" -- fires whenever Claude
finishes responding). Only acts when a governed task is active
(.agent/runtime/active-task.json), same convention as
pretooluse_gate.py/precompact_checkpoint.py -- a session with no governed work
in flight leaves `.agent/` untouched, so casual turns don't spam it with files.

When a task is active, writes `.agent/HANDOFF.md` + a new `.agent/sessions/*.md`
entry (git-tracked, format compatible with github.com/ishipu/agent-handoff), with a
Runtime section summarizing the run's ledger, so a
different agent platform (or a different machine, after `git pull`) can pick up
this run's state. One record per Claude session (keyed by the hook payload's
session_id), rewritten on each Stop rather than one new file per reply. Never
blocks Stop: any error is reported, not enforced.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'runtime/python'))
from agentic_runtime.paths import REPO_ROOT, ACTIVE_TASK_POINTER


def _emit(message):
    print(json.dumps({'systemMessage': message}))
    return 0


def _close_active_run(session_id=None):
    from agentic_runtime.hooks_support import load_active_task
    from agentic_runtime import handoff
    _pointer, store, run = load_active_task(ACTIVE_TASK_POINTER)
    if run is None:
        return None
    task = run.metadata.get('active_task') or {}
    changed_files = sorted(run.metadata.get('context', {}).get('files', {}))
    next_action = (
        f"Resume task {task['id']} (skill {task['skill']}) via task-finish/task-fail, "
        f"then `agentic_runtime.cli show {run.run_id}`."
        if task else f"Continue via `agentic_runtime.cli show {run.run_id}`."
    )
    result = handoff.close_session(
        REPO_ROOT, agent='claude', status=run.status, task=run.title,
        completed=f"Reached stage {run.stage} (status {run.status}).",
        changed_files=changed_files,
        blockers='Task was still active when Claude stopped.' if task else '',
        next_action=next_action, store=store, run_id=run.run_id, session_id=session_id,
    )
    return f"Wrote handoff notes for run {run.run_id} ({result['handoff']})."


def main():
    try:
        payload = json.loads(sys.stdin.read() or '{}')
        note = _close_active_run(payload.get('session_id'))
    except Exception as exc:
        note = f'Could not write handoff notes (fail open): {exc}'
    return _emit(note or 'No governed run is active; nothing to hand off.')


if __name__ == '__main__':
    raise SystemExit(main())
