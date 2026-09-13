#!/usr/bin/env python3
"""Claude Code PreToolUse hook: gate native tool calls against an active governed run.

Wired via .claude/settings.json (matcher "Bash|Write|Edit|NotebookEdit"). When no
governed task is active (agentic/runtime/state/active-task.json is absent), every
call is allowed untouched -- this only enforces the harness during a task started
with `agentic_runtime.cli task-start`. Any error constructing the orchestrator or
reading its state fails open (allow) so a runtime bug never bricks the session;
only an explicit policy decision from Orchestrator.guard denies.
"""
import json
import sys
from pathlib import Path

KIT = Path(__file__).resolve().parents[2]
STATE = KIT / 'runtime/state/active-task.json'
GOVERNED_TOOLS = {'Bash', 'Write', 'Edit', 'NotebookEdit'}


def _emit(decision, reason):
    print(json.dumps({'hookSpecificOutput': {
        'hookEventName': 'PreToolUse',
        'permissionDecision': decision,
        'permissionDecisionReason': reason,
    }}))
    return 0


def main():
    if not STATE.exists():
        return _emit('allow', 'No governed run is active; nothing to enforce')
    try:
        payload = json.loads(sys.stdin.read() or '{}')
        tool_name = payload.get('tool_name')
        if tool_name not in GOVERNED_TOOLS:
            return _emit('allow', 'Tool is not governed by the harness')
        pointer = json.loads(STATE.read_text())
    except (OSError, ValueError) as exc:
        return _emit('allow', 'Active-task pointer unreadable; failing open: ' + str(exc))
    try:
        sys.path.insert(0, str(KIT / 'runtime/python'))
        from agentic_runtime.orchestrator import Orchestrator
        from agentic_runtime.store import RuntimeStore
        tool_input = payload.get('tool_input') or {}
        command = tool_input.get('command') if tool_name == 'Bash' else None
        store = RuntimeStore(pointer['db'])
        try:
            Orchestrator(store, KIT).guard(pointer['run_id'], pointer['task_id'], tool_name, command)
        finally:
            store.conn.close()
    except (PermissionError, ValueError, TimeoutError) as exc:
        return _emit('deny', str(exc))
    except BaseException as exc:  # noqa: BLE001 - a hook bug must not brick the session
        return _emit('allow', 'Gate hook internal error; failing open: ' + str(exc))
    return _emit('allow', 'Permitted by governed run ' + pointer['run_id'])


if __name__ == '__main__':
    raise SystemExit(main())
