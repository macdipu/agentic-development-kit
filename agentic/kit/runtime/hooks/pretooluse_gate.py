#!/usr/bin/env python3
"""Claude Code PreToolUse hook: gate native tool calls against an active governed run.

Wired via .claude/settings.json (matcher "Bash|Write|Edit|NotebookEdit"). When no
governed task is active (agentic/data/runtime/state/active-task.json is absent), every
call is allowed untouched. While a marker is present, unreadable state and internal
gate failures deny matched tools until an operator diagnoses and recovers the task.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'runtime/python'))
from agentic_runtime.paths import KIT, ACTIVE_TASK_POINTER as STATE
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
        return _emit('deny', 'Cannot verify governed state. Run doctor and repair-marker after stopping workers: ' + str(exc))
    try:
        sys.path.insert(0, str(KIT / 'runtime/python'))
        from agentic_runtime.orchestrator import Orchestrator
        from agentic_runtime.store import RuntimeStore
        tool_input = payload.get('tool_input') or {}
        command = tool_input.get('command') if tool_name == 'Bash' else None
        if not Path(pointer['db']).is_file():
            raise ValueError('Active task database is missing; restore it before recovery')
        store = RuntimeStore(pointer['db'])
        try:
            Orchestrator(store, KIT).guard(pointer['run_id'], pointer['task_id'], tool_name, command, tool_input)
        finally:
            store.conn.close()
    except (PermissionError, ValueError, TimeoutError) as exc:
        return _emit('deny', str(exc))
    except Exception as exc:
        return _emit('deny', 'Cannot verify governed task; run doctor and recover from an operator terminal: ' + str(exc))
    return _emit('allow', 'Permitted by governed run ' + pointer['run_id'])


if __name__ == '__main__':
    raise SystemExit(main())
