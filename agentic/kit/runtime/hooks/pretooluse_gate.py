#!/usr/bin/env python3
"""Claude Code PreToolUse hook: gate native tool calls against an active governed run.

Wired via .claude/settings.json (matcher "Bash|Write|Edit|NotebookEdit"). While a
governed task is active (.agent/local/active-task.json), every matched call is
checked against that task's permissions; unreadable state and internal gate
failures deny matched tools until an operator diagnoses and recovers the task.

With no active task, Write/Edit/NotebookEdit into project code are denied while
any run is still RUNNING/BLOCKED (`require_task_for_code_writes`, default on):
skipping `task-start` must not skip governance. Documents under agentic/data/
and .agent/, files outside the project, and Bash stay allowed. With no open run
at all, nothing is enforced except the runtime ledger's write protection.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'runtime/python'))
from agentic_runtime.paths import KIT, REPO_ROOT, RUNS_DIR, ACTIVE_TASK_POINTER as STATE
GOVERNED_TOOLS = {'Bash', 'Write', 'Edit', 'NotebookEdit'}
WRITE_TOOLS = {'Write', 'Edit', 'NotebookEdit'}


def _emit(decision, reason):
    # Only a governed pass (allowlisted by an active task) or a denial carries a
    # decision. Anything the harness does not govern defers to the host's normal
    # permission flow: an 'allow' there would skip the user's own permission prompts.
    if decision == 'defer':
        print(json.dumps({'hookSpecificOutput': {'hookEventName': 'PreToolUse'}, 'suppressOutput': True}))
        return 0
    print(json.dumps({'hookSpecificOutput': {
        'hookEventName': 'PreToolUse',
        'permissionDecision': decision,
        'permissionDecisionReason': reason,
    }}))
    return 0


def _without_task(payload):
    tool_name = payload.get('tool_name')
    if tool_name not in WRITE_TOOLS:
        return _emit('defer', 'No governed task is active; nothing to enforce')
    from agentic_runtime.hooks_support import ungoverned_write_denial
    tool_input = payload.get('tool_input') or {}
    policy = json.loads((KIT / 'config/platform.json').read_text(encoding='utf-8'))
    reason = ungoverned_write_denial(REPO_ROOT, tool_input.get('file_path') or tool_input.get('notebook_path'),
                                     RUNS_DIR, policy)
    return _emit('deny', reason) if reason else _emit('defer', 'No governed task is active; write is not project code')


def main():
    try:
        payload = json.loads(sys.stdin.buffer.read().decode('utf-8', 'replace') or '{}')
        tool_name = payload.get('tool_name')
    except (OSError, ValueError) as exc:
        if not STATE.exists():
            return _emit('defer', 'No governed run is active; unreadable hook input: ' + str(exc))
        return _emit('deny', 'Cannot verify governed state. Run doctor and repair-marker after stopping workers: ' + str(exc))
    if not STATE.exists():
        try:
            return _without_task(payload)
        except Exception as exc:
            # Fail open with no task: the no-task rule is a guard rail, not a lock.
            return _emit('defer', 'Could not evaluate open runs (allowed): ' + str(exc))
    if tool_name not in GOVERNED_TOOLS:
        return _emit('defer', 'Tool is not governed by the harness')
    try:
        from agentic_runtime.hooks_support import load_active_task
        from agentic_runtime.orchestrator import Orchestrator
        tool_input = payload.get('tool_input') or {}
        command = tool_input.get('command') if tool_name == 'Bash' else None
        pointer, store, _run = load_active_task(STATE)
        Orchestrator(store, KIT).guard(pointer['run_id'], pointer['task_id'], tool_name, command, tool_input)
    except (PermissionError, ValueError, TimeoutError) as exc:
        return _emit('deny', str(exc))
    except Exception as exc:
        return _emit('deny', 'Cannot verify governed task; run doctor and recover from an operator terminal: ' + str(exc))
    return _emit('allow', 'Permitted by governed run ' + pointer['run_id'])


if __name__ == '__main__':
    raise SystemExit(main())
