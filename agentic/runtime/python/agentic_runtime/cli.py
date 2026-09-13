#!/usr/bin/env python3
import argparse
import json
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from agentic_runtime.dependency_graph import DependencyGraph
from agentic_runtime.orchestrator import Orchestrator
from agentic_runtime.policy import PLANNING, STAGES, WORK_TYPES
from agentic_runtime.store import RuntimeStore
from agentic_runtime.tools import NATIVE_TOOL_CAPABILITY, build_default_tools

KIT = HERE.parents[2]
DB = KIT / 'runtime/state/agentic.db'
ACTIVE_TASK_POINTER = KIT / 'runtime/state/active-task.json'


def _write_active_task(db, run_id, task_id):
    ACTIVE_TASK_POINTER.parent.mkdir(parents=True, exist_ok=True)
    ACTIVE_TASK_POINTER.write_text(json.dumps({'db': str(Path(db).resolve()), 'run_id': run_id, 'task_id': task_id}))


def _clear_active_task():
    ACTIVE_TASK_POINTER.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Local governed workflow runtime (trusted operator)')
    parser.add_argument('--db', type=Path, default=DB)
    sub = parser.add_subparsers(dest='cmd', required=True)
    sub.add_parser('init')
    sub.add_parser('list')
    start = sub.add_parser('start')
    start.add_argument('--project', required=True)
    start.add_argument('--type', choices=sorted(WORK_TYPES), required=True)
    start.add_argument('--title', required=True)
    start.add_argument('--repo', type=Path, default=KIT.parent)
    start.add_argument('--planning', choices=sorted(PLANNING), default='NO_REPLAN')
    start.add_argument('--dry-run', action='store_true')
    for name in ('show', 'eligible', 'cancel'):
        sub.add_parser(name).add_argument('run_id')
    transition = sub.add_parser('transition')
    transition.add_argument('run_id')
    transition.add_argument('stage', choices=sorted(STAGES))
    approval = sub.add_parser('approve')
    approval.add_argument('run_id')
    approval.add_argument('--gate', choices=['technical', 'release', 'uat'], required=True)
    approval.add_argument('--by', required=True)
    approval.add_argument('--decision', choices=['APPROVED', 'REJECTED'], default='APPROVED')
    approval.add_argument('--comment', default='')
    context = sub.add_parser('context')
    context.add_argument('run_id')
    context.add_argument('paths', nargs='+', help='Reviewed scope files, relative to --repo from start')
    result = sub.add_parser('result')
    result.add_argument('run_id')
    result.add_argument('--skill', required=True)
    result.add_argument('--file', type=Path, required=True)
    timing = sub.add_parser('timing', help='Query recorded task timing/duration events for a run')
    timing.add_argument('run_id')
    timing.add_argument('--task', help='Filter to one task id')
    for name in ('reopen', 'recover'):
        command = sub.add_parser(name)
        command.add_argument('run_id')
        command.add_argument('--reason', required=True)
    task_start = sub.add_parser('task-start', help='Begin a governed task for a cross-process adapter (Python or CLI-driven)')
    task_start.add_argument('run_id')
    task_start.add_argument('--skill', required=True)
    call_tool = sub.add_parser('call-tool', help='Invoke a registered gateway tool for an active task')
    call_tool.add_argument('run_id')
    call_tool.add_argument('task_id')
    call_tool.add_argument('--name', required=True)
    call_tool.add_argument('--args', default='{}', help='JSON object of tool arguments')
    call_tool.add_argument('--idempotency-key')
    task_finish = sub.add_parser('task-finish', help='Submit the handoff envelope for an active task and close it')
    task_finish.add_argument('run_id')
    task_finish.add_argument('task_id')
    task_finish.add_argument('--file', type=Path, required=True)
    task_fail = sub.add_parser('task-fail', help='Record an interrupted or errored task without accepting a result')
    task_fail.add_argument('run_id')
    task_fail.add_argument('task_id')
    task_fail.add_argument('--error', required=True)
    impact = sub.add_parser('impact', help='Query the transitive dependency closure of changed modules')
    impact.add_argument('modules', nargs='+', help='Changed module names to expand')
    impact.add_argument('--edges', type=Path, required=True, help='JSON file mapping module name to a list of the modules that depend on it')
    guard = sub.add_parser('guard', help='Permission check for a native coding-agent tool call (used by the PreToolUse hook)')
    guard.add_argument('run_id')
    guard.add_argument('task_id')
    guard.add_argument('--tool', required=True, choices=sorted(NATIVE_TOOL_CAPABILITY))
    guard.add_argument('--command', help='The Bash command text, required when --tool Bash')
    args = parser.parse_args(argv)
    store = None
    try:
        store = RuntimeStore(str(args.db))
        orch = Orchestrator(store, KIT)
        if args.cmd == 'init':
            output = {'db': str(args.db.resolve())}
        elif args.cmd == 'list':
            output = store.list_runs()
        elif args.cmd == 'start':
            output = orch.start(args.project, args.type, args.title, args.dry_run, args.repo, args.planning)
        elif args.cmd == 'show':
            output = store.get_run(args.run_id)
            if output is None:
                raise ValueError('Unknown run')
        elif args.cmd == 'eligible':
            output = orch.eligible_skills(args.run_id)
        elif args.cmd == 'transition':
            output = orch.transition(args.run_id, args.stage)
        elif args.cmd == 'approve':
            output = orch.approve(args.run_id, args.gate, args.by, args.decision, args.comment)
        elif args.cmd == 'context':
            output = orch.record_context(args.run_id, args.paths)
        elif args.cmd == 'timing':
            output = orch.task_timings(args.run_id, args.task)
        elif args.cmd == 'result':
            submitted = json.loads(args.file.read_text())
            output = orch.execute(args.run_id, args.skill, lambda context, call_tool: submitted)
        elif args.cmd in {'reopen', 'recover'}:
            output = getattr(orch, args.cmd)(args.run_id, args.reason)
            if args.cmd == 'recover':
                _clear_active_task()
        elif args.cmd == 'task-start':
            task, context = orch.start_task(args.run_id, args.skill)
            _write_active_task(args.db, args.run_id, task['id'])
            output = {'task_id': task['id'], 'context': context}
        elif args.cmd == 'call-tool':
            run = store.get_run(args.run_id)
            if run is None:
                raise ValueError('Unknown run')
            tools = build_default_tools(run.metadata['repo'], orch.allowed_commands)
            output = Orchestrator(store, KIT, tools).call_tool(args.run_id, args.task_id, args.name, json.loads(args.args), args.idempotency_key)
        elif args.cmd == 'task-finish':
            submitted = json.loads(args.file.read_text())
            output = orch.finish_task(args.run_id, args.task_id, submitted)
            _clear_active_task()
        elif args.cmd == 'task-fail':
            orch.fail_task(args.run_id, args.task_id, args.error)
            _clear_active_task()
            output = {'task_id': args.task_id, 'failed': True}
        elif args.cmd == 'guard':
            output = orch.guard(args.run_id, args.task_id, args.tool, args.command)
        elif args.cmd == 'impact':
            edges = json.loads(args.edges.read_text())
            if not isinstance(edges, dict) or not all(isinstance(v, list) for v in edges.values()):
                raise ValueError('Edges file must map module name to a list of dependent module names')
            graph = DependencyGraph()
            for module, dependents in edges.items():
                for dependent in dependents:
                    graph.add(module, dependent)
            output = {'modules': graph.closure(args.modules)}
        else:
            output = orch.cancel(args.run_id)
            _clear_active_task()
        print(json.dumps(output.to_dict() if hasattr(output, 'to_dict') else output, indent=2))
        return 0
    except (ValueError, OSError, RuntimeError, sqlite3.Error) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    finally:
        if store:
            store.conn.close()


if __name__ == '__main__':
    raise SystemExit(main())
