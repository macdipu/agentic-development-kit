#!/usr/bin/env python3
import argparse
import json
import sqlite3
import sys
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from agentic_runtime.dependency_graph import DependencyGraph
from agentic_runtime.orchestrator import Orchestrator
from agentic_runtime.policy import PLANNING, STAGES, WORK_TYPES
from agentic_runtime.store import RuntimeStore
from agentic_runtime.tools import NATIVE_TOOL_CAPABILITY, build_default_tools
from agentic_runtime.paths import KIT, AGENTIC, DB, ACTIVE_TASK_POINTER
from agentic_runtime import markers
from agentic_runtime.timing import now

def main(argv=None):
    parser = argparse.ArgumentParser(description='Local governed workflow runtime (trusted operator)')
    parser.add_argument('--db', type=Path, default=DB)
    sub = parser.add_subparsers(dest='cmd', required=True)
    sub.add_parser('init')
    sub.add_parser('list')
    doctor = sub.add_parser('doctor', help='Check installed modes, tools, storage, and hooks')
    doctor.add_argument('--repo', type=Path, default=AGENTIC.parent)
    production = sub.add_parser('production-check', help='Validate bound readiness evidence; does not authorize or deploy')
    production.add_argument('--file', type=Path, required=True)
    repair = sub.add_parser('repair-marker', help='Clear a damaged marker after database recovery and worker shutdown')
    repair.add_argument('--workers-stopped', action='store_true', required=True)
    repair.add_argument('--reason', required=True)
    start = sub.add_parser('start')
    start.add_argument('--project', required=True)
    start.add_argument('--type', choices=sorted(WORK_TYPES), required=True)
    start.add_argument('--title', required=True)
    start.add_argument('--repo', type=Path, default=AGENTIC.parent)
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
    guard.add_argument('--input', default='{}', help='JSON native tool input including write paths')
    args = parser.parse_args(argv)
    store = None
    try:
        if args.cmd == 'production-check':
            from agentic_runtime.production import check_readiness
            report = check_readiness(json.loads(args.file.read_text()), args.file.resolve().parent)
            print(json.dumps(report, indent=2))
            return 0 if report['status'] == 'EVIDENCE_COMPLETE' else 1
        if args.cmd == 'doctor':
            from agentic_runtime.doctor import diagnose
            report = diagnose(args.repo)
            print(json.dumps(report, indent=2))
            return 0 if report['ok'] else 1
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
                markers.clear(ACTIVE_TASK_POINTER, args.db, args.run_id)
        elif args.cmd == 'repair-marker':
            if not args.reason.strip() or any(json.loads(r['metadata_json']).get('active_task') for r in store.list_runs()):
                raise ValueError('Recover active database tasks before repairing their marker')
            # Explicit operator recovery; retain damaged contents for diagnosis.
            if ACTIVE_TASK_POINTER.exists():
                try:
                    pointer = json.loads(ACTIVE_TASK_POINTER.read_text())
                except ValueError:
                    pointer = {}
                if isinstance(pointer, dict) and pointer.get('db') and Path(pointer['db']).resolve() != args.db.resolve():
                    raise ValueError('Marker belongs to a different database; select it explicitly with --db')
                backup = ACTIVE_TASK_POINTER.with_name('active-task.recovered-' + uuid.uuid4().hex + '.json')
                ACTIVE_TASK_POINTER.rename(backup)
                store.audit('marker-recovery', 'MARKER_RECOVERED', {'reason': args.reason, 'backup': str(backup)}, now())
            output = {'repaired': True}
        elif args.cmd == 'task-start':
            markers.reserve(ACTIVE_TASK_POINTER, args.db, args.run_id)
            task = None
            try:
                task, context = orch.start_task(args.run_id, args.skill)
                markers.activate(ACTIVE_TASK_POINTER, args.db, args.run_id, task['id'])
            except BaseException as exc:
                if task:
                    orch.fail_task(args.run_id, task['id'], exc)
                markers.clear(ACTIVE_TASK_POINTER, args.db, args.run_id)
                raise
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
            markers.clear(ACTIVE_TASK_POINTER, args.db, args.run_id, args.task_id)
        elif args.cmd == 'task-fail':
            orch.fail_task(args.run_id, args.task_id, args.error)
            markers.clear(ACTIVE_TASK_POINTER, args.db, args.run_id, args.task_id)
            output = {'task_id': args.task_id, 'failed': True}
        elif args.cmd == 'guard':
            output = orch.guard(args.run_id, args.task_id, args.tool, args.command, json.loads(args.input))
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
            markers.clear(ACTIVE_TASK_POINTER, args.db, args.run_id)
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
