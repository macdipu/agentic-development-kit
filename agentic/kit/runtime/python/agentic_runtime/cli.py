#!/usr/bin/env python3
import argparse
import json
import subprocess
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
from agentic_runtime.paths import KIT, AGENTIC, REPO_ROOT, RUNS_DIR, ACTIVE_TASK_POINTER, ROUTE_CACHE_FILE, ACTIVE_TASK_POINTER_REL
from agentic_runtime import markers, handoff, commits, identity, state_git
from agentic_runtime.claims import Claims, ClaimHeld
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


def _run_repo(store, run_id):
    run = store.get_run(run_id)
    if run is None:
        raise ValueError('Unknown run')
    return run.metadata['repo']


def _cmd_approve(args, store, orch):
    if args.auto:
        if args.by or args.decision != 'APPROVED':
            raise ValueError('--auto cannot be combined with --by or --decision')
        if not args.comment.strip():
            raise ValueError('--auto requires --comment as the auto-approval reason')
        return orch.auto_approve(args.run_id, args.gate, args.comment)
    approver = identity.approver(_run_repo(store, args.run_id), args.by)
    return orch.approve(args.run_id, args.gate, approver, args.decision, args.comment)


def _cmd_migrate_pins(args, store, orch):
    return orch.migrate_pins(args.run_id, identity.approver(_run_repo(store, args.run_id), args.by), args.reason)


def _cmd_context(args, store, orch):
    return orch.record_context(args.run_id, args.paths)


def _cmd_timing(args, store, orch):
    return orch.task_timings(args.run_id, args.task)


def _cmd_result(args, store, orch):
    submitted = json.loads(args.file.read_text(encoding='utf-8'))
    return orch.execute(args.run_id, args.skill, lambda context, call_tool: submitted)


def _cmd_reopen(args, store, orch):
    return orch.reopen(args.run_id, args.reason)


def _cmd_adjust_budget(args, store, orch):
    return orch.adjust_budget(args.run_id, identity.approver(_run_repo(store, args.run_id), args.by), args.reason,
                              args.max_agent_retries, args.max_task_seconds)


def _cmd_recover(args, store, orch):
    output = orch.recover(args.run_id, args.reason)
    markers.clear(ACTIVE_TASK_POINTER, args.store_dir, args.run_id)
    _settle(args, store, f'recover {args.run_id}')
    return output


def _cmd_repair_marker(args, store, orch):
    if not args.reason.strip() or any(r['metadata'].get('active_task') for r in store.list_runs()):
        raise ValueError('Recover active database tasks before repairing their marker')
    # Explicit operator recovery; retain damaged contents for diagnosis.
    if ACTIVE_TASK_POINTER.exists():
        try:
            pointer = json.loads(ACTIVE_TASK_POINTER.read_text(encoding='utf-8'))
        except ValueError:
            pointer = {}
        if isinstance(pointer, dict) and pointer.get('store_dir') and markers.store_dir_of(ACTIVE_TASK_POINTER, pointer) != args.store_dir.resolve():
            raise ValueError('Marker belongs to a different store; select it explicitly with --store-dir')
        backup = ACTIVE_TASK_POINTER.with_name('active-task.recovered-' + uuid.uuid4().hex + '.json')
        ACTIVE_TASK_POINTER.rename(backup)
        # Machine-local event: logged beside the pointer, not as a pseudo-run in shared state.
        log = ACTIVE_TASK_POINTER.parent / 'marker-recoveries.jsonl'
        with log.open('a', encoding='utf-8', newline='\n') as handle:
            handle.write(json.dumps({'at': now(), 'reason': args.reason, 'backup': str(backup)}) + '\n')
    return {'repaired': True}


def _claims(args):
    """Claims beside the store: `.agent/state/claims`, clone id in `.agent/local`."""
    state_dir = Path(args.store_dir).resolve().parent
    return Claims(state_dir / 'claims', state_dir.parent / 'local', REPO_ROOT,
                  state_git.config(KIT).get('claim_ttl_seconds', 7200))


def _warn(message):
    if message:
        print('agentic: ' + message, file=sys.stderr)


def _settle(args, store, subject, release=False):
    """Commit the state a task or run left. A clone keeps its claim across tasks (so
    other machines see it whenever this one pushes); only a finished or cancelled
    run, or `handoff`, releases it."""
    claims = _claims(args)
    if release:
        claims.release(args.run_id)
    elif (claims.current(args.run_id) or {}).get('mine'):
        claims.claim(args.run_id, agent=handoff.current_agent(REPO_ROOT))  # renew past half-life
    run = store.get_run(args.run_id)
    repo = run.metadata['repo'] if run else REPO_ROOT
    result = state_git.commit_state(repo, subject, args.run_id, KIT)
    if not result.get('committed') and result.get('reason', '').startswith('git commit failed'):
        _warn('agent state not committed: ' + result['reason'])
    return result


def _cmd_task_start(args, store, orch):
    claims = _claims(args)
    held_before = (claims.current(args.run_id) or {}).get('mine')
    # The claim is the cross-machine lock: another clone's claim (as far as git has
    # carried it here) stops this start.
    claims.claim(args.run_id, agent=handoff.current_agent(REPO_ROOT), task=args.skill)
    task = None
    reserved = False
    try:
        markers.reserve(ACTIVE_TASK_POINTER, args.store_dir, args.run_id)
        reserved = True
        task, context = orch.start_task(args.run_id, args.skill)
        markers.activate(ACTIVE_TASK_POINTER, args.store_dir, args.run_id, task['id'])
    except BaseException as exc:
        if task:
            orch.fail_task(args.run_id, task['id'], exc)
        if reserved:
            markers.clear(ACTIVE_TASK_POINTER, args.store_dir, args.run_id)
        if not held_before:
            claims.release(args.run_id)
        raise
    if not held_before:
        # A new claim is committed at once, so it travels with this clone's next push.
        run = store.get_run(args.run_id)
        state_git.commit_state(run.metadata['repo'] if run else REPO_ROOT, f'claim {args.run_id}', args.run_id, KIT)
    if args.full:
        return {'task_id': task['id'], 'context': context}
    # Token budget: the agent reads files itself. Printing every registered file's
    # content (runs had up to ~250) cost more than the work; paths are enough.
    return {'task_id': task['id'], 'run_id': args.run_id, 'skill': args.skill, 'stage': context['run']['stage'],
            'skill_doc': Path(context['skill_path']).relative_to(REPO_ROOT).as_posix()
            if Path(context['skill_path']).is_relative_to(REPO_ROOT) else context['skill_path'],
            'context_files': sorted(context['context_files'])}


def _end_task(args, store, skill, result=None, error=''):
    """Every task end rewrites the handoff from the ledger, renews the claim, and
    commits the state, so the next agent anywhere continues from `git pull`."""
    run = store.get_run(args.run_id)
    try:
        handoff.refresh_from_run(run.metadata['repo'], store, args.run_id, skill, result, error)
    except (OSError, ValueError) as exc:
        _warn('handoff not refreshed: ' + str(exc))
    status = 'failed' if error else (result or {}).get('status', 'done').lower()
    _settle(args, store, f'record {skill or "task"} {status} at {run.stage}')


def _cmd_call_tool(args, store, orch):
    run = store.get_run(args.run_id)
    if run is None:
        raise ValueError('Unknown run')
    tools = build_default_tools(run.metadata['repo'], orch.allowed_commands)
    return Orchestrator(store, KIT, tools).call_tool(args.run_id, args.task_id, args.name, json.loads(args.args), args.idempotency_key)


def _cmd_task_finish(args, store, orch):
    submitted = json.loads(args.file.read_text(encoding='utf-8'))
    run = store.get_run(args.run_id)
    skill = ((run.metadata.get('active_task') or {}).get('skill', '')) if run else ''
    output = orch.finish_task(args.run_id, args.task_id, submitted)
    markers.clear(ACTIVE_TASK_POINTER, args.store_dir, args.run_id, args.task_id)
    _end_task(args, store, skill, result=output)
    return output


def _cmd_task_fail(args, store, orch):
    run = store.get_run(args.run_id)
    skill = ((run.metadata.get('active_task') or {}).get('skill', '')) if run else ''
    orch.fail_task(args.run_id, args.task_id, args.error)
    markers.clear(ACTIVE_TASK_POINTER, args.store_dir, args.run_id, args.task_id)
    _end_task(args, store, skill, error=args.error)
    return {'task_id': args.task_id, 'failed': True}


def _cmd_guard(args, store, orch):
    return orch.guard(args.run_id, args.task_id, args.tool, args.command, json.loads(args.input))


def _cmd_close_session(args, store, orch):
    run_id = args.run
    if run_id is None and ACTIVE_TASK_POINTER.exists():
        run_id = json.loads(ACTIVE_TASK_POINTER.read_text(encoding='utf-8')).get('run_id')
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


def _message(args):
    return commits.render_message(
        type=args.type, scope=args.scope, subject=args.subject, body=args.body,
        trigger=args.trigger, work_item=args.work_item, task=args.task, run=args.run,
        breaking=args.breaking, extra_trailers=args.trailer)


def _cmd_commit(args, store, orch):
    """Validate the message first, then stage + commit + record, so a rejected
    message can never become a commit (the old `commit-message | git commit -F -`
    pipe committed whatever reached stdin)."""
    message = _message(args)
    repo = _run_repo(store, args.run) if args.run else args.repo
    info = commits.commit(repo, message, args.path)
    if args.run:
        store.audit(args.run, 'COMMIT_RECORDED', info, now())
        info = {**info, 'recorded_in_run': args.run}
        # The audit event itself rides the next state commit.
    return info


def _cmd_impact(args, store, orch):
    edges = json.loads(args.edges.read_text(encoding='utf-8'))
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
    _settle(args, store, f'cancel {args.run_id}', release=True)
    return output


def _cmd_transition(args, store, orch):
    run = orch.transition(args.run_id, args.stage)
    if run.status == 'COMPLETED':
        _settle(args, store, f'complete {args.run_id}', release=True)
    return run


def _cmd_claims(args, store, orch):
    return _claims(args).all()


def _cmd_claim(args, store, orch):
    return _claims(args).claim(args.run_id, agent=handoff.current_agent(REPO_ROOT),
                               takeover=args.takeover, reason=args.reason)


def _cmd_release(args, store, orch):
    return _claims(args).release(args.run_id) or {'released': False, 'reason': 'this clone holds no claim on ' + args.run_id}


def _active_run_id():
    try:
        return json.loads(ACTIVE_TASK_POINTER.read_text(encoding='utf-8')).get('run_id')
    except (OSError, ValueError):
        return None


def _cmd_handoff(args, store, orch):
    """Switch machines: refresh the handoff note, free this clone's claim (an active
    task stays recorded for the next machine to adopt), commit everything -- work in
    progress included -- and push the current branch."""
    run_id = args.run or _active_run_id()
    claims = _claims(args)
    if run_id:
        run = store.get_run(run_id)
        if run is None:
            raise ValueError('Unknown run ' + run_id)
        task = run.metadata.get('active_task') or {}
        handoff.refresh_from_run(run.metadata['repo'], store, run_id, task.get('skill', ''),
                                 {'status': run.status, 'evidence': [], 'blocking_issues': [],
                                  'recommended_next_step': f'On the next machine: `git pull`, then '
                                                           f'`agentic_runtime.cli resume {run_id}`'})
    released = [c['run_id'] for c in claims.all() if c['mine'] and claims.release(c['run_id'])]
    if run_id:
        # This clone stops working the task; the ledger keeps it active for the next
        # machine to adopt. A pointer left here would pass the guard for work that is
        # no longer this clone's, then break once the task finishes elsewhere.
        markers.clear(ACTIVE_TASK_POINTER, args.store_dir, run_id)
    push = state_git.config(KIT).get('handoff_push', True) and not args.no_push
    subject = f'hand off {run_id}' if run_id else 'hand off work in progress'
    report = state_git.handoff(REPO_ROOT, subject, run_id or '', push=push)
    return {'run_id': run_id, 'released_claims': released, **report,
            'next': f'On the other machine: `agentic_runtime.cli resume {run_id}`' if run_id else 'On the other machine: `git pull`'}


def _cmd_resume(args, store, orch):
    """Continue here a run another machine or platform was on: fast-forward the
    branch (its state and work in progress arrive with it), take the claim, and
    adopt the run's active task."""
    pulled = {'pulled': False, 'reason': '--no-pull'} if args.no_pull else state_git.pull(REPO_ROOT)
    handoff.sync_local_handoff(REPO_ROOT)
    run = store.get_run(args.run_id)
    if run is None:
        raise ValueError('Unknown run ' + args.run_id + ' (not in .agent/state after pull)')
    claims = _claims(args)
    claim = claims.claim(args.run_id, agent=handoff.current_agent(REPO_ROOT), takeover=args.takeover, reason=args.reason)
    report = {'run_id': args.run_id, 'stage': run.stage, 'status': run.status, 'pull': pulled, 'claim': claim}
    task = run.metadata.get('active_task')
    if task and not ACTIVE_TASK_POINTER.exists():
        orch.adopt_task(args.run_id, claims.identity())  # restarts the task's time budget
        markers.reserve(ACTIVE_TASK_POINTER, args.store_dir, args.run_id)
        markers.activate(ACTIVE_TASK_POINTER, args.store_dir, args.run_id, task['id'])
        report['adopted_task'] = task
    elif task:
        report['active_task'] = task
    report['state_commit'] = state_git.commit_state(REPO_ROOT, f'resume {args.run_id}', args.run_id, KIT)
    return report


def _cmd_migrate_state(args, store, orch):
    """Move the previous layout (.agent/runtime/, one rewritten JSON per run, and a
    committed HANDOFF.md) to the append-only .agent/state/ layout. Stages the result;
    the operator reviews and commits."""
    from agentic_runtime import migration
    return migration.migrate(REPO_ROOT, store)


def session_notes(repo, fetch=True):
    """What a new session must know beyond the handoff: other clones' claims, commits
    waiting upstream (another machine's work), and state not yet committed here."""
    from agentic_runtime.claims import default_claims
    notes = []
    claims = default_claims(repo) if Path(repo).resolve() != REPO_ROOT.resolve() else default_claims()
    for line in claims.report():
        notes.append('CLAIM ' + line[2:])
    status = state_git.branch_status(repo, fetch=fetch and state_git.config(KIT).get('fetch_on_session_start', True))
    if status and status.get('behind'):
        notes.append(f"UPSTREAM: {status['upstream']} has {status['behind']} commit(s) not here -- "
                     f"`git pull` before continuing (another machine may have handed off).")
    pending = state_git.pending_state(repo)
    if pending:
        notes.append(f'UNCOMMITTED AGENT STATE: {len(pending)} file(s) under .agent/state or .agent/sessions; '
                     f'they reach other machines with your next commit (or `agentic_runtime.cli handoff`).')
    if status and status.get('ahead'):
        notes.append(f"UNPUSHED: {status['ahead']} local commit(s) -- other machines see them after `git push` "
                     f"(or `agentic_runtime.cli handoff`).")
    return notes


def run_summary(run):
    """What an agent needs after a run command -- where it is, what is next, what is
    missing -- without skill pins, hashes, and evidence lists (`--full` has those)."""
    meta = run.metadata
    route = meta.get('route') or []
    nxt = route[route.index(run.stage) + 1] if run.stage in route and route.index(run.stage) + 1 < len(route) else None
    results = meta.get('results', {})
    current = results.get(run.stage) or {}
    summary = {'run_id': run.run_id, 'title': run.title, 'work_type': run.work_type, 'stage': run.stage,
               'status': run.status, 'next_stage': nxt,
               'stage_results': {stage: r.get('status') for stage, r in results.items()},
               'active_task': meta.get('active_task'), 'scope_revision': meta.get('scope_revision', 0),
               'context_files': len((meta.get('context') or {}).get('files', {}))}
    if current.get('blocking_issues'):
        summary['blocking_issues'] = current['blocking_issues']
    if current.get('recommended_next_step'):
        summary['recommended_next_step'] = current['recommended_next_step']
    return summary


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
    decision = json.loads(args.file.read_text(encoding='utf-8'))
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
    'commit': _cmd_commit, 'migrate-pins': _cmd_migrate_pins,
    'claims': _cmd_claims, 'claim': _cmd_claim, 'release': _cmd_release,
    'handoff': _cmd_handoff, 'resume': _cmd_resume, 'migrate-state': _cmd_migrate_state,
}

# Commands that change a run another clone may hold: refused while it does.
RUN_CHANGES = {'transition', 'approve', 'context', 'reopen', 'adjust-budget', 'migrate-pins', 'result',
               'record-commit', 'cancel', 'recover', 'task-finish', 'task-fail', 'call-tool'}


def main(argv=None):
    parser = argparse.ArgumentParser(description='Local governed workflow runtime (trusted operator)')
    parser.add_argument('--store-dir', type=Path, default=RUNS_DIR, dest='store_dir')
    parser.add_argument('--full', action='store_true',
                        help='Print complete records (run metadata, skill pins, task context). Default output is a '
                             'compact summary to keep agent context small.')
    sub = parser.add_subparsers(dest='cmd', required=True)
    full_flag = argparse.ArgumentParser(add_help=False)
    full_flag.add_argument('--full', action='store_true', default=argparse.SUPPRESS,
                           help='Print the complete record instead of the compact summary')
    add_parser = sub.add_parser
    def _add(name, **kwargs):
        # `pickup` has its own --full (print the files verbatim); every other command
        # accepts the global flag after the subcommand too (`show RUN --full`).
        if name != 'pickup':
            kwargs['parents'] = kwargs.get('parents', []) + [full_flag]
        return add_parser(name, **kwargs)
    sub.add_parser = _add
    sub.add_parser('init')
    sub.add_parser('list')
    doctor = sub.add_parser('doctor', help='Check installed modes, tools, storage, and hooks')
    doctor.add_argument('--repo', type=Path, default=AGENTIC.parent)
    context_check = sub.add_parser('context-check', help='Report context-index entries marked reusable whose evidence is missing or changed')
    context_check.add_argument('--repo', type=Path, default=REPO_ROOT)
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
    approval.add_argument('--by', help='Human approver; defaults to the git-configured identity, and the operator own name/email or "user" normalize to it')
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
    budget.add_argument('--by', help='Authorizing operator (default: git identity)')
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
    pickup.add_argument('--no-fetch', action='store_true', dest='no_fetch', help='Do not git fetch to report commits waiting upstream')
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
    commit_cmd = sub.add_parser('commit', help='Validate the message, stage --path files, git commit (hooks run), and record it in --run')
    for command in (commit_message, commit_cmd):
        command.add_argument('--type', choices=commits.COMMIT_TYPES, required=True)
        command.add_argument('--scope', default='', help='Module/feature, e.g. auth')
        command.add_argument('--subject', required=True, help='Imperative, no trailing period')
        command.add_argument('--body', default='', help='Why the change was made')
        command.add_argument('--trigger', choices=commits.TRIGGERS, required=True)
        command.add_argument('--work-item', default='', dest='work_item', help='e.g. FEAT-12, CR-3, BUG-7')
        command.add_argument('--task', default='', help='Task id the commit closes')
        command.add_argument('--run', default='', help='Governed run id, when one is active')
        command.add_argument('--breaking', action='store_true')
        command.add_argument('--trailer', action='append', default=[],
                             help='Extra "Key: value" trailer in the same block, e.g. platform attribution (repeatable)')
    commit_cmd.add_argument('--path', action='append', default=[], help='File to stage (repeatable); default: commit what is already staged')
    commit_cmd.add_argument('--repo', type=Path, default=REPO_ROOT)
    migrate = sub.add_parser('migrate-pins', help='Re-pin a run recorded under the pre-portable hash; refuses if any skill/config content changed')
    migrate.add_argument('run_id')
    migrate.add_argument('--by', help='Operator (default: git identity)')
    migrate.add_argument('--reason', required=True)
    sub.add_parser('claims', help='List which clone holds which run (.agent/state/claims)')
    claim_cmd = sub.add_parser('claim', help="Acquire or refresh this clone's claim on a run")
    resume_cmd = sub.add_parser('resume', help='Continue a run another machine/platform was on: git pull --ff-only, claim, adopt its task')
    for command in (claim_cmd, resume_cmd):
        command.add_argument('run_id')
        command.add_argument('--takeover', action='store_true', help="Take another clone's unexpired claim (recorded)")
        command.add_argument('--reason', default='', help='Required for any takeover')
    resume_cmd.add_argument('--no-pull', action='store_true', help='Do not run git pull --ff-only first')
    handoff_cmd = sub.add_parser('handoff', help='Before switching machines: commit all work and state, free the claim, push the branch')
    handoff_cmd.add_argument('--run', default=None, help='Run being handed off (default: the active task\'s run)')
    handoff_cmd.add_argument('--no-push', action='store_true', help='Commit only; push yourself')
    sub.add_parser('migrate-state', help='Convert the previous .agent/runtime/ layout to .agent/state/ and stage it for review')
    sub.add_parser('release', help="Release this clone's claim on a run").add_argument('run_id')
    record_commit = sub.add_parser('record-commit', help="Append a commit (with its trigger/traceability trailers) to a run's audit log")
    record_commit.add_argument('run_id')
    record_commit.add_argument('--rev', default='HEAD')
    args = parser.parse_args(argv)
    try:
        if args.cmd == 'production-check':
            from agentic_runtime.production import check_readiness
            report = check_readiness(json.loads(args.file.read_text(encoding='utf-8')), args.file.resolve().parent)
            print(json.dumps(report, indent=2))
            return 0 if report['status'] == 'EVIDENCE_COMPLETE' else 1
        if args.cmd == 'doctor':
            from agentic_runtime.doctor import diagnose
            report = diagnose(args.repo)
            print(json.dumps(report, indent=2))
            return 0 if report['ok'] else 1
        if args.cmd == 'context-check':
            from agentic_runtime.context_index import check
            report = check(args.repo)
            print(json.dumps(report, indent=2))
            return 0 if report['ok'] else 1
        if args.cmd == 'install-hooks':
            from agentic_runtime.installation import install_claude_hooks
            print(json.dumps(install_claude_hooks(args.repo, KIT / 'config/hooks.json'), indent=2))
            return 0
        if args.cmd == 'pickup':
            # Hookless platforms get the same view SessionStart gives Claude Code.
            for line in session_notes(args.repo, fetch=not args.no_fetch):
                print(line)
            if not args.full:
                pointer = args.repo / ACTIVE_TASK_POINTER_REL
                active_run = json.loads(pointer.read_text(encoding='utf-8')).get('run_id') if pointer.is_file() else None
                print(handoff.pickup_summary(args.repo, active_run_id=active_run) or 'No .agent/HANDOFF.md yet.')
                return 0
            note = handoff.read_handoff(args.repo)
            session = handoff.read_latest_session(args.repo)
            print(note or 'No .agent/HANDOFF.md yet.')
            if session:
                print('\n' + session)
            return 0
        if args.cmd == 'commit-message':
            sys.stdout.write(_message(args))
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
        if args.cmd in RUN_CHANGES:
            held = _claims(args).holder_other(args.run_id)
            if held:
                raise ClaimHeld(args.run_id, held)
        output = COMMANDS[args.cmd](args, store, orch)
        if args.cmd == 'close-session':
            state_git.commit_state(args.repo, 'record session', args.run or '', KIT)
        if hasattr(output, 'to_dict'):
            output = output.to_dict() if args.full else run_summary(output)
        print(json.dumps(output, indent=2 if args.full else None, separators=None if args.full else (',', ':')))
        return 0
    except (ValueError, OSError, RuntimeError, TimeoutError, subprocess.SubprocessError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
