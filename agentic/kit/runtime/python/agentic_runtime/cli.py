#!/usr/bin/env python3
import argparse
import json
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
from agentic_runtime.paths import KIT, AGENTIC, REPO_ROOT, RUNS_DIR, ACTIVE_TASK_POINTER, ROUTE_CACHE_FILE
from agentic_runtime import markers, handoff, commits
from agentic_runtime.routing_cache import RoutingCache, PROJECT_TYPES, cache_key, compute_kit_version
from agentic_runtime.timing import now


def _cmd_init(args, store, orch):
    return {'store_dir': str(args.store_dir.resolve())}


def _cmd_list(args, store, orch):
    return store.list_runs()


def _cmd_start(args, store, orch):
    return orch.start(args.project, args.type, args.title, args.dry_run, args.repo, args.planning)


def _cmd_show(args, store, orch):
    run = store.get_run(args.run_id)
    if run is None:
        raise ValueError('Unknown run')
    return run


def _cmd_eligible(args, store, orch):
    return orch.eligible_skills(args.run_id)


def _cmd_transition(args, store, orch):
    return orch.transition(args.run_id, args.stage)


def _cmd_approve(args, store, orch):
    if args.auto:
        if args.by or args.decision != 'APPROVED':
            raise ValueError('--auto cannot be combined with --by or --decision')
        if not args.comment.strip():
            raise ValueError('--auto requires --comment as the auto-approval reason')
        return orch.auto_approve(args.run_id, args.gate, args.comment)
    if not args.by:
        raise ValueError('--by is required unless --auto is set')
    return orch.approve(args.run_id, args.gate, args.by, args.decision, args.comment)


def _cmd_context(args, store, orch):
    return orch.record_context(args.run_id, args.paths)


def _cmd_timing(args, store, orch):
    return orch.task_timings(args.run_id, args.task)


def _cmd_result(args, store, orch):
    submitted = json.loads(args.file.read_text())
    return orch.execute(args.run_id, args.skill, lambda context, call_tool: submitted)


def _cmd_reopen(args, store, orch):
    return orch.reopen(args.run_id, args.reason)


def _cmd_adjust_budget(args, store, orch):
    return orch.adjust_budget(args.run_id, args.by, args.reason,
                              args.max_agent_retries, args.max_task_seconds)


def _cmd_recover(args, store, orch):
    output = orch.recover(args.run_id, args.reason)
    markers.clear(ACTIVE_TASK_POINTER, args.store_dir, args.run_id)
    return output


def _cmd_repair_marker(args, store, orch):
    if not args.reason.strip() or any(r['metadata'].get('active_task') for r in store.list_runs()):
        raise ValueError('Recover active database tasks before repairing their marker')
    # Explicit operator recovery; retain damaged contents for diagnosis.
    if ACTIVE_TASK_POINTER.exists():
        try:
            pointer = json.loads(ACTIVE_TASK_POINTER.read_text())
        except ValueError:
            pointer = {}
        if isinstance(pointer, dict) and pointer.get('store_dir') and markers.store_dir_of(ACTIVE_TASK_POINTER, pointer) != args.store_dir.resolve():
            raise ValueError('Marker belongs to a different store; select it explicitly with --store-dir')
        backup = ACTIVE_TASK_POINTER.with_name('active-task.recovered-' + uuid.uuid4().hex + '.json')
        ACTIVE_TASK_POINTER.rename(backup)
        store.audit('marker-recovery', 'MARKER_RECOVERED', {'reason': args.reason, 'backup': str(backup)}, now())
    return {'repaired': True}


def _cmd_task_start(args, store, orch):
    markers.reserve(ACTIVE_TASK_POINTER, args.store_dir, args.run_id)
    task = None
    try:
        task, context = orch.start_task(args.run_id, args.skill)
        markers.activate(ACTIVE_TASK_POINTER, args.store_dir, args.run_id, task['id'])
    except BaseException as exc:
        if task:
            orch.fail_task(args.run_id, task['id'], exc)
        markers.clear(ACTIVE_TASK_POINTER, args.store_dir, args.run_id)
        raise
    return {'task_id': task['id'], 'context': context}


def _cmd_call_tool(args, store, orch):
    run = store.get_run(args.run_id)
    if run is None:
        raise ValueError('Unknown run')
    tools = build_default_tools(run.metadata['repo'], orch.allowed_commands)
    return Orchestrator(store, KIT, tools).call_tool(args.run_id, args.task_id, args.name, json.loads(args.args), args.idempotency_key)


def _cmd_task_finish(args, store, orch):
    submitted = json.loads(args.file.read_text())
    output = orch.finish_task(args.run_id, args.task_id, submitted)
    markers.clear(ACTIVE_TASK_POINTER, args.store_dir, args.run_id, args.task_id)
    return output


def _cmd_task_fail(args, store, orch):
    orch.fail_task(args.run_id, args.task_id, args.error)
    markers.clear(ACTIVE_TASK_POINTER, args.store_dir, args.run_id, args.task_id)
    return {'task_id': args.task_id, 'failed': True}


def _cmd_guard(args, store, orch):
    return orch.guard(args.run_id, args.task_id, args.tool, args.command, json.loads(args.input))


def _cmd_close_session(args, store, orch):
    run_id = args.run
    if run_id is None and ACTIVE_TASK_POINTER.exists():
        run_id = json.loads(ACTIVE_TASK_POINTER.read_text()).get('run_id')
    return handoff.close_session(args.repo, agent=args.agent, status=args.status,
                                  task=args.task, completed=args.completed,
                                  changed_files=args.changed_files, tests=args.tests,
                                  blockers=args.blockers, decisions=args.decisions,
                                  next_action=args.next_action, store=store, run_id=run_id)


def _cmd_record_commit(args, store, orch):
    run = store.get_run(args.run_id)
    if run is None:
        raise ValueError('Unknown run')
    info = commits.commit_info(run.metadata['repo'], args.rev)
    if info.get('commit_trigger') not in commits.TRIGGERS:
        raise ValueError(f'Commit {info["sha"]} has no valid Commit-Trigger trailer; use commit-message to build it')
    store.audit(args.run_id, 'COMMIT_RECORDED', info, now())
    return info


def _cmd_impact(args, store, orch):
    edges = json.loads(args.edges.read_text())
    if not isinstance(edges, dict) or not all(isinstance(v, list) for v in edges.values()):
        raise ValueError('Edges file must map module name to a list of dependent module names')
    graph = DependencyGraph()
    for module, dependents in edges.items():
        for dependent in dependents:
            graph.add(module, dependent)
    return {'modules': graph.closure(args.modules)}


def _cmd_cancel(args, store, orch):
    output = orch.cancel(args.run_id)
    markers.clear(ACTIVE_TASK_POINTER, args.store_dir, args.run_id)
    return output


def _cmd_route_cache_get(args):
    cache = RoutingCache(ROUTE_CACHE_FILE)
    key = cache_key(args.work_type, args.project_type, args.module)
    version = compute_kit_version(args.repo, KIT)
    entry = cache.get(key, version)
    return {'hit': entry is not None, 'key': key, 'kit_version': version, 'entry': entry}


def _cmd_route_cache_put(args):
    cache = RoutingCache(ROUTE_CACHE_FILE)
    key = cache_key(args.work_type, args.project_type, args.module)
    version = compute_kit_version(args.repo, KIT)
    decision = json.loads(args.file.read_text())
    entry = cache.put(key, version, decision, now())
    return {'stored': True, 'key': key, 'entry': entry}


def _cmd_route_cache_clear(args):
    RoutingCache(ROUTE_CACHE_FILE).clear()
    return {'cleared': True}


COMMANDS = {
    'init': _cmd_init, 'list': _cmd_list, 'start': _cmd_start, 'show': _cmd_show,
    'eligible': _cmd_eligible, 'transition': _cmd_transition, 'approve': _cmd_approve,
    'context': _cmd_context, 'timing': _cmd_timing, 'result': _cmd_result,
    'reopen': _cmd_reopen, 'recover': _cmd_recover, 'repair-marker': _cmd_repair_marker,
    'task-start': _cmd_task_start, 'call-tool': _cmd_call_tool, 'task-finish': _cmd_task_finish,
    'task-fail': _cmd_task_fail, 'guard': _cmd_guard, 'close-session': _cmd_close_session,
    'impact': _cmd_impact, 'cancel': _cmd_cancel,
    'adjust-budget': _cmd_adjust_budget, 'record-commit': _cmd_record_commit,
}


def main(argv=None):
    parser = argparse.ArgumentParser(description='Local governed workflow runtime (trusted operator)')
    parser.add_argument('--store-dir', type=Path, default=RUNS_DIR, dest='store_dir')
    sub = parser.add_subparsers(dest='cmd', required=True)
    sub.add_parser('init')
    sub.add_parser('list')
    doctor = sub.add_parser('doctor', help='Check installed modes, tools, storage, and hooks')
    doctor.add_argument('--repo', type=Path, default=AGENTIC.parent)
    install_hooks = sub.add_parser('install-hooks', help='Merge the kit hooks into .claude/settings.json; existing settings and hooks are preserved')
    install_hooks.add_argument('--repo', type=Path, default=REPO_ROOT)
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
    approval.add_argument('--by', help='Human approver identity; required unless --auto is set')
    approval.add_argument('--decision', choices=['APPROVED', 'REJECTED'], default='APPROVED')
    approval.add_argument('--comment', default='')
    approval.add_argument('--auto', action='store_true',
                           help='Auto-approve via the narrow TASK_ONLY + single-file + TECHNICAL_READY exception '
                                '(technical gate only; never release/uat). Mutually exclusive with --by/--decision; '
                                'requires --comment as the reason. Recorded under a distinct synthetic approver so '
                                'the audit trail can tell it apart from a human approval.')
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
    budget = sub.add_parser('adjust-budget', help='Record an operator-authorized budget adjustment for one inactive run; preserve history and approvals')
    budget.add_argument('run_id')
    budget.add_argument('--by', required=True)
    budget.add_argument('--reason', required=True)
    budget.add_argument('--max-agent-retries', type=int)
    budget.add_argument('--max-task-seconds', type=int)
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
    pickup = sub.add_parser('pickup', help='Print the condensed handoff note (what SessionStart injects) for a hookless CLI/platform')
    pickup.add_argument('--repo', type=Path, default=REPO_ROOT)
    pickup.add_argument('--full', action='store_true', help='Print HANDOFF.md and the latest session record verbatim')
    route_cache_get = sub.add_parser('route-cache-get', help='Look up a cached routing decision; skip re-reading meta-docs in full on a hit')
    route_cache_get.add_argument('--work-type', choices=sorted(WORK_TYPES), required=True)
    route_cache_get.add_argument('--project-type', choices=list(PROJECT_TYPES), required=True)
    route_cache_get.add_argument('--module', required=True)
    route_cache_get.add_argument('--repo', type=Path, default=REPO_ROOT)
    route_cache_put = sub.add_parser('route-cache-put', help='Cache a routing decision (route, matched workflow/persona/skill docs) for later sessions to reuse')
    route_cache_put.add_argument('--work-type', choices=sorted(WORK_TYPES), required=True)
    route_cache_put.add_argument('--project-type', choices=list(PROJECT_TYPES), required=True)
    route_cache_put.add_argument('--module', required=True)
    route_cache_put.add_argument('--repo', type=Path, default=REPO_ROOT)
    route_cache_put.add_argument('--file', type=Path, required=True, help='JSON decision payload: at least route, workflow_doc, skill_docs')
    route_cache_clear = sub.add_parser('route-cache-clear', help='Wipe the routing cache, e.g. after a kit upgrade you want to force a fresh read for')
    route_cache_clear.add_argument('--repo', type=Path, default=REPO_ROOT)
    close_session = sub.add_parser('close-session', help='Write .agent/HANDOFF.md + a session record for cross-agent-platform handoff (agent-handoff compatible)')
    close_session.add_argument('--agent', required=True, choices=sorted(handoff.VALID_AGENTS))
    close_session.add_argument('--task', required=True, help='What this run/session is for')
    close_session.add_argument('--completed', required=True, help='What was done this session')
    close_session.add_argument('--changed-files', nargs='*', default=[], dest='changed_files')
    close_session.add_argument('--tests', default='', help='Test results, e.g. "npm test passes"')
    close_session.add_argument('--blockers', default='')
    close_session.add_argument('--decisions', default='', help='Notable decisions made this session')
    close_session.add_argument('--next-action', default='', dest='next_action')
    close_session.add_argument('--status', choices=['RUNNING', 'BLOCKED', 'COMPLETED', 'CANCELLED'], required=True)
    close_session.add_argument('--run', default=None, help='Run to summarize in the Runtime section (default: the active task\'s run)')
    close_session.add_argument('--repo', type=Path, default=REPO_ROOT)
    commit_message = sub.add_parser('commit-message', help='Print a policy-conformant commit message (Conventional Commits + traceability trailers)')
    commit_message.add_argument('--type', choices=commits.COMMIT_TYPES, required=True)
    commit_message.add_argument('--scope', default='', help='Module/feature, e.g. auth')
    commit_message.add_argument('--subject', required=True, help='Imperative, no trailing period')
    commit_message.add_argument('--body', default='', help='Why the change was made')
    commit_message.add_argument('--trigger', choices=commits.TRIGGERS, required=True)
    commit_message.add_argument('--work-item', default='', dest='work_item', help='e.g. FEAT-12, CR-3, BUG-7')
    commit_message.add_argument('--task', default='', help='Task id the commit closes')
    commit_message.add_argument('--run', default='', help='Governed run id, when one is active')
    commit_message.add_argument('--breaking', action='store_true')
    record_commit = sub.add_parser('record-commit', help="Append a commit (with its trigger/traceability trailers) to a run's audit log")
    record_commit.add_argument('run_id')
    record_commit.add_argument('--rev', default='HEAD')
    args = parser.parse_args(argv)
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
        if args.cmd == 'install-hooks':
            from agentic_runtime.installation import install_claude_hooks
            print(json.dumps(install_claude_hooks(args.repo, KIT / 'config/hooks.json'), indent=2))
            return 0
        if args.cmd == 'pickup':
            if not args.full:
                pointer = args.repo / '.agent/runtime/active-task.json'
                active_run = json.loads(pointer.read_text()).get('run_id') if pointer.is_file() else None
                print(handoff.pickup_summary(args.repo, active_run_id=active_run) or 'No .agent/HANDOFF.md yet.')
                return 0
            note = handoff.read_handoff(args.repo)
            session = handoff.read_latest_session(args.repo)
            print(note or 'No .agent/HANDOFF.md yet.')
            if session:
                print('\n' + session)
            return 0
        if args.cmd == 'commit-message':
            sys.stdout.write(commits.render_message(
                type=args.type, scope=args.scope, subject=args.subject, body=args.body,
                trigger=args.trigger, work_item=args.work_item, task=args.task, run=args.run,
                breaking=args.breaking))
            return 0
        if args.cmd == 'route-cache-get':
            print(json.dumps(_cmd_route_cache_get(args), indent=2))
            return 0
        if args.cmd == 'route-cache-put':
            print(json.dumps(_cmd_route_cache_put(args), indent=2))
            return 0
        if args.cmd == 'route-cache-clear':
            print(json.dumps(_cmd_route_cache_clear(args), indent=2))
            return 0
        store = RuntimeStore(str(args.store_dir))
        orch = Orchestrator(store, KIT)
        output = COMMANDS[args.cmd](args, store, orch)
        print(json.dumps(output.to_dict() if hasattr(output, 'to_dict') else output, indent=2))
        return 0
    except (ValueError, OSError, RuntimeError, TimeoutError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
