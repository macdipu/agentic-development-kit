import hashlib
import inspect
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .context import normalized_bytes, snapshot, snapshot_state
from .contracts import SUCCESS_STATUSES, validate_result
from .models import WorkflowRun
from .policy import auto_approve_eligible, evaluate, workflow_route
from .registry import SkillRegistry, ToolRegistry
from .security import redact_value
from .timing import durations, now
from .tools import NATIVE_TOOL_CAPABILITY, command_rule, validate_write

# Gates whose evidence depends on scope files reviewed at each stage; a scope
# change there makes those gates' evidence suspect without invalidating the
# whole run. Stages absent here have no established precedent for a scoped
# invalidation and still require a full reopen.
_STAGE_GATE_REVOKE = {
    'CONTEXT': ('technical', 'release', 'uat'),
    'TECHNICAL': ('technical', 'release', 'uat'),
    'IMPLEMENTATION': ('release', 'uat'),
    'QA': ('release', 'uat'),
    'UAT': ('uat', 'release'),
}

# Recorded as the approver on an auto-approved gate (see Orchestrator.auto_approve)
# so the audit trail can tell an automated approval from a human's at a glance.
AUTO_APPROVER = 'runtime:auto'


def _gate_prerequisite(gate, work_type):
    return {'technical': 'CONTEXT' if work_type == 'existing_task' else 'TECHNICAL', 'release': 'QA', 'uat': 'UAT'}.get(gate)


class Orchestrator:
    """Local cooperative governance for trusted adapters; not an OS sandbox."""

    def __init__(self, store, kit_dir=None, tools=None):
        self.store = store
        self.kit_dir = Path(kit_dir) if kit_dir else Path(__file__).resolve().parents[3]
        self.registry = SkillRegistry(self.kit_dir / 'skills')
        self.tools = tools or ToolRegistry()
        self.policy = json.loads((self.kit_dir / 'config/platform.json').read_text(encoding='utf-8'))
        self.capabilities = json.loads((self.kit_dir / 'config/capabilities.json').read_text(encoding='utf-8'))['defaults']
        self.permissions = json.loads((self.kit_dir / 'config/permissions.json').read_text(encoding='utf-8'))
        self.allowed_commands = json.loads((self.kit_dir / 'config/allowed-commands.json').read_text(encoding='utf-8'))['commands']
        self.loaded_config_hash = self._config_hash()
        for key in ('max_agent_retries', 'max_task_seconds', 'max_tool_calls_per_task'):
            if type(self.policy.get(key)) is not int or self.policy[key] < (0 if key == 'max_agent_retries' else 1):
                raise ValueError('Invalid runtime budget: ' + key)
        if self.policy.get('direct_production_write') is not False:
            raise ValueError('Production execution is unsupported')
        for key in ('audit_tool_calls', 'record_task_timing', 'require_release_approval'):
            if self.policy.get(key) is not True:
                raise ValueError('Required local control cannot be disabled: ' + key)
        if type(self.policy.get('require_uat_approval')) is not bool:
            raise ValueError('require_uat_approval must be boolean')
        # Keys newer than a host's preserved platform.json fall back to the defaults below.
        budgets = self.policy.setdefault('skill_budgets', {})
        if not isinstance(budgets, dict) or any(not isinstance(v, dict) for v in budgets.values()):
            raise ValueError('skill_budgets must map skill name to an object of limits')
        for skill, limits in budgets.items():
            for key, value in limits.items():
                minimum = 0 if key == 'max_agent_retries' else 1
                if key not in ('max_agent_retries', 'max_task_seconds') or type(value) is not int or value < minimum:
                    raise ValueError(f'Invalid skill budget {skill}.{key}')
        threshold = self.policy.setdefault('post_hoc_threshold_seconds', 10)
        if type(threshold) is not int or threshold < 0:
            raise ValueError('post_hoc_threshold_seconds must be a non-negative integer')
        if type(self.policy.setdefault('require_task_for_code_writes', True)) is not bool:
            raise ValueError('require_task_for_code_writes must be boolean')

    _PINNED_CONFIG = ('platform.json', 'capabilities.json', 'permissions.json', 'skill-registry.json', 'allowed-commands.json')

    def _config_hash(self):
        # LF-normalized so Windows and macOS/Linux checkouts of one config pin identically.
        data = b''.join(normalized_bytes((self.kit_dir / 'config' / name).read_bytes()) for name in self._PINNED_CONFIG)
        return hashlib.sha256(data).hexdigest()

    def _legacy_config_hash(self):
        data = b''.join((self.kit_dir / 'config' / name).read_bytes() for name in self._PINNED_CONFIG)
        return hashlib.sha256(data).hexdigest()

    def migrate_pins(self, run_id, operator, reason):
        """Re-pin a run recorded under the pre-portable hash algorithm (native path
        separator, raw CRLF bytes). Accepted only when every recorded pin equals the
        legacy digest of the *current* content, i.e. no skill or config actually
        changed -- this proves equivalence, it never adopts new content."""
        if not operator.strip() or not reason.strip():
            raise ValueError('Pin migration requires an operator and a reason')
        with self.store.transaction():
            run = self._run(run_id)
            if run.metadata['active_task']:
                raise ValueError('Finish or recover the active task before migrating pins')
            skills = self.registry.discover()
            pins, changed = dict(run.metadata['skill_pins']), []
            for skill, pin in run.metadata['skill_pins'].items():
                item = skills.get(skill)
                if item is None:
                    raise ValueError('Pinned skill no longer exists: ' + skill)
                if pin == item['revision']:
                    continue
                if pin not in item['legacy_revisions']:
                    raise ValueError('Skill content changed since the run started: ' + skill + '; start a new run')
                pins[skill] = item['revision']
                changed.append(skill)
            config_hash = run.metadata['config_hash']
            if config_hash != self._config_hash():
                if config_hash != self._legacy_config_hash():
                    raise ValueError('Configuration changed since the run started; start a new run')
                config_hash = self._config_hash()
                changed.append('config')
            if not changed:
                return run
            run.metadata['skill_pins'], run.metadata['config_hash'] = pins, config_hash
            self._save(run, 'PINS_MIGRATED', {'operator': operator, 'reason': reason, 'migrated': changed})
        return run

    def _run(self, run_id, allow_terminal=False):
        run = self.store.get_run(run_id)
        if not run:
            raise ValueError('Unknown run')
        if run.metadata.get('runtime_version') != 2:
            raise ValueError('Legacy run is read-only; start a new governed run with reviewed evidence')
        if not allow_terminal and run.status in {'CANCELLED', 'COMPLETED'}:
            raise ValueError('Run is terminal')
        return run

    def _current_config(self, run):
        if run.metadata['config_hash'] != self._config_hash():
            raise ValueError('Configuration changed; start a new run to adopt it')

    def _save(self, run, event, payload=None):
        run.updated_at = now()
        self.store.save_checkpoint(run, event, payload)

    def start(self, project, work_type, title, dry_run=False, repo=None, planning='NO_REPLAN'):
        if self.loaded_config_hash != self._config_hash():
            raise ValueError('Configuration changed; reload the orchestrator')
        if not project.strip() or not title.strip():
            raise ValueError('Project and title are required')
        route = workflow_route(work_type, planning, self.policy['require_uat_approval'])
        root = Path(repo or self.kit_dir.parent.parent).resolve()
        if not root.is_dir():
            raise ValueError('Project root must exist')
        ts = now()
        run = WorkflowRun('RUN-' + uuid.uuid4().hex.upper(), project, work_type, title, status='RUNNING', dry_run=dry_run, created_at=ts, updated_at=ts)
        run.metadata = {'runtime_version': 2, 'repo': str(root), 'route': route, 'planning': planning, 'scope_revision': 0,
                        'config_hash': self._config_hash(), 'skill_pins': {k: v['revision'] for k, v in self.registry.discover().items()},
                        'results': {}, 'attempts': {}, 'active_task': None}
        with self.store.transaction():
            self._save(run, 'RUN_STARTED')
        return run

    def eligible_skills(self, run_id):
        run = self._run(run_id)
        self._current_config(run)
        return self.registry.eligible(run.stage)

    def record_context(self, run_id, paths):
        with self.store.transaction():
            run = self._run(run_id)
            if run.metadata['active_task']:
                raise ValueError('Cannot refresh context during an active task')
            recorded = snapshot(run.metadata['repo'], paths)
            previous = run.metadata.get('context')
            changed = bool(previous) and previous['files'] != recorded['files']
            if changed and run.stage not in {'INTAKE', *_STAGE_GATE_REVOKE}:
                raise ValueError('Scope files changed after review; reopen the run to invalidate downstream evidence')
            if changed and run.stage in _STAGE_GATE_REVOKE:
                run.metadata['results'].pop(run.stage, None)
                run.metadata.get('skill_results', {}).pop(run.stage, None)
                self._revoke(run, _STAGE_GATE_REVOKE[run.stage])
            run.metadata['context'] = recorded
            self._save(run, 'CONTEXT_REFRESHED', {'paths': paths})
        return run

    def _fresh(self, run):
        state = snapshot_state(run.metadata['repo'], run.metadata.get('context'))
        if state != 'AVAILABLE':
            raise ValueError('Context is ' + state + '; review and refresh the affected scope')

    def transition(self, run_id, next_stage):
        with self.store.transaction():
            run = self._run(run_id)
            self._current_config(run)
            if run.metadata['active_task']:
                raise ValueError('Task is still active')
            route = run.metadata['route']
            index = route.index(run.stage)
            if index + 1 >= len(route) or next_stage != route[index + 1]:
                raise ValueError('Invalid transition; next stage is ' + (route[index + 1] if index + 1 < len(route) else 'none'))
            result = run.metadata['results'].get(run.stage, {})
            if result.get('status') not in SUCCESS_STATUSES:
                raise ValueError('Current stage needs a ready result with evidence')
            if next_stage != 'CONTEXT':
                self._fresh(run)
            if run.stage == 'PREVIEW' and result.get('status') != 'PREVIEW_READY':
                raise ValueError('Preview completion requires visual verification with PREVIEW_READY')
            approvals = {gate: self.store.has_approval(run_id, gate) for gate in ('technical', 'release', 'uat')}
            decision = evaluate(next_stage, approvals)
            if not decision.allowed:
                raise ValueError('; '.join(decision.reasons))
            if run.stage == 'UAT' and not approvals['uat']:
                raise ValueError('Missing UAT approval')
            if run.stage == 'RELEASE' and not approvals['release']:
                raise ValueError('Missing release approval')
            run.stage = next_stage
            run.status = 'COMPLETED' if next_stage == 'COMPLETED' else 'RUNNING'
            self._save(run, 'STAGE_CHANGED')
        if run.status == 'COMPLETED':
            self.store.compact(run_id)
        return run

    def approve(self, run_id, gate, approver, decision='APPROVED', comment=''):
        with self.store.transaction():
            run = self._run(run_id)
            self._current_config(run)
            if run.metadata['active_task'] and decision == 'APPROVED':
                raise ValueError('Cannot approve while a task is active')
            prerequisite = _gate_prerequisite(gate, run.work_type)
            if prerequisite not in run.metadata['route']:
                raise ValueError('Gate is not applicable to this workflow')
            if decision == 'APPROVED':
                if run.metadata['results'].get(prerequisite, {}).get('status') not in SUCCESS_STATUSES:
                    raise ValueError('Approval needs ready evidence for ' + prerequisite)
                self._fresh(run)
            self.store.approval(run_id, gate, approver, decision, comment, now(), run.metadata['scope_revision'])
            self._save(run, 'APPROVAL_RECORDED', {'gate': gate, 'decision': decision, 'by': approver})
        return run

    def auto_approve(self, run_id, gate, reason):
        """A narrow, mechanically-checked exception to the human approval gate --
        technical only, never release/uat -- for evidence a skill has already
        self-reported onto the run (see policy.auto_approve_eligible). Recorded
        under the fixed AUTO_APPROVER approver so the audit trail stays
        distinguishable from a human's approval at a glance; never infers or
        fabricates human sign-off (AGENTS.md #10)."""
        if not reason.strip():
            raise ValueError('Auto-approval requires a reason')
        with self.store.transaction():
            run = self._run(run_id)
            self._current_config(run)
            if run.metadata['active_task']:
                raise ValueError('Cannot approve while a task is active')
            prerequisite = _gate_prerequisite(gate, run.work_type)
            if prerequisite not in run.metadata['route']:
                raise ValueError('Gate is not applicable to this workflow')
            if run.metadata['results'].get(prerequisite, {}).get('status') not in SUCCESS_STATUSES:
                raise ValueError('Approval needs ready evidence for ' + prerequisite)
            self._fresh(run)
            context_files = run.metadata.get('context', {}).get('files', {})
            if not auto_approve_eligible(gate, run.metadata.get('skill_results', {}), context_files):
                raise ValueError('Not eligible for auto-approval: requires a TASK_ONLY classification recorded by '
                                  'work-item-level-classifier, a single-file scope, and a TECHNICAL_READY verdict '
                                  'recorded by technical-readiness-verifier')
            self.store.approval(run_id, gate, AUTO_APPROVER, 'APPROVED', reason, now(), run.metadata['scope_revision'])
            self._save(run, 'AUTO_APPROVAL_RECORDED', {'gate': gate, 'reason': reason})
        return run

    def reopen(self, run_id, reason):
        if not reason.strip():
            raise ValueError('Reopen requires a scope/rework reason')
        with self.store.transaction():
            run = self._run(run_id)
            if run.metadata['results'].get('INTAKE', {}).get('status') not in SUCCESS_STATUSES:
                raise ValueError('Complete intake before reopening scope')
            if run.metadata['active_task']:
                raise ValueError('Task is still active')
            # Retain intake, invalidate downstream evidence and all prior approvals.
            run.metadata['scope_revision'] += 1
            run.metadata['results'] = {k: v for k, v in run.metadata['results'].items() if k == 'INTAKE'}
            run.metadata['skill_results'] = {k: v for k, v in run.metadata.get('skill_results', {}).items() if k == 'INTAKE'}
            run.metadata.pop('context', None)
            run.stage, run.status = 'CONTEXT', 'RUNNING'
            self._save(run, 'SCOPE_REOPENED', {'reason': reason})
        return run

    def cancel(self, run_id):
        with self.store.transaction():
            run = self._run(run_id)
            run.status = 'CANCELLED'
            task = run.metadata['active_task']
            if task:
                self.store.timing(run_id, task['id'], 'CANCELLED', now())
            run.metadata['active_task'] = None
            self._save(run, 'RUN_CANCELLED')
        self.store.compact(run_id)
        return run

    def task_timings(self, run_id, task=None):
        """Query recorded timing events for a run (or one task) and compute elapsed durations."""
        self._run(run_id, allow_terminal=True)
        return durations(self.store.query_timing(run_id, task))

    def recover(self, run_id, reason):
        """Operator acknowledges an interrupted adapter; never replay side effects."""
        if not reason.strip():
            raise ValueError('Recovery requires an interruption explanation')
        with self.store.transaction():
            run = self._run(run_id)
            task = run.metadata['active_task']
            if not task:
                raise ValueError('No interrupted task to recover')
            run.metadata['active_task'] = None
            run.status = 'BLOCKED'
            self.store.timing(run_id, task['id'], 'INTERRUPTED', now(), {'reason': reason})
            self._save(run, 'TASK_RECOVERED', {'reason': reason})
        return run

    def adjust_budget(self, run_id, operator, reason, max_agent_retries=None, max_task_seconds=None):
        """Record an explicitly authorized, run-local budget adjustment.

        Like approve(), this is a trusted-operator API, not authentication.
        Attempts, task history, scope and approval gates are never reset.
        """
        if not operator.strip() or not reason.strip():
            raise ValueError('Budget adjustment requires an operator and authorization reason')
        changes = {k: v for k, v in {
            'max_agent_retries': max_agent_retries, 'max_task_seconds': max_task_seconds,
        }.items() if v is not None}
        if not changes:
            raise ValueError('Specify at least one budget limit')
        for key, value in changes.items():
            if type(value) is not int or value < (0 if key == 'max_agent_retries' else 1):
                raise ValueError('Invalid runtime budget: ' + key)
        with self.store.transaction():
            run = self._run(run_id)
            self._current_config(run)
            if run.metadata['active_task']:
                raise ValueError('Finish or recover the active task before adjusting its budget')
            previous = {k: self._budget(run, k) for k in changes}
            run.metadata.setdefault('budget_overrides', {}).update(changes)
            self._save(run, 'BUDGET_ADJUSTED', {
                'operator': operator, 'reason': reason, 'previous': previous, 'limits': changes,
            })
        return run

    def _budget(self, run, key, skill=None):
        """Run override (operator-authorized) > per-skill default > global default."""
        overrides = run.metadata.get('budget_overrides', {})
        if key in overrides:
            return overrides[key]
        return self.policy['skill_budgets'].get(skill, {}).get(key, self.policy[key])

    def _active(self, run_id, task_id):
        run = self._run(run_id)
        self._current_config(run)
        task = run.metadata['active_task']
        if not task or task['id'] != task_id:
            raise ValueError('Task is no longer active')
        item = self.registry.discover().get(task['skill'])
        if not item or item['revision'] != run.metadata['skill_pins'].get(task['skill']):
            raise ValueError('Pinned skill content changed')
        decision = evaluate(run.stage, {gate: self.store.has_approval(run_id, gate) for gate in ('technical', 'release')})
        if not decision.allowed:
            raise PermissionError('; '.join(decision.reasons))
        # A task adopted on another machine is budgeted from its adoption, not from
        # when the first machine started it (the gap was the handoff, not work).
        clock = task.get('adopted_at') or task['started_at']
        elapsed = (datetime.now(timezone.utc) - datetime.fromisoformat(clock)).total_seconds()
        if elapsed >= self._budget(run, 'max_task_seconds', task['skill']):
            raise TimeoutError('Task execution budget exhausted')
        return run, task

    def adopt_task(self, run_id, adopter):
        """Continue a run's active task on this clone (after `handoff`/`resume`): restarts
        its time budget, keeps its attempt count, and records who adopted it."""
        with self.store.transaction():
            run = self._run(run_id)
            task = run.metadata.get('active_task')
            if not task:
                raise ValueError('Run has no active task to adopt')
            task['adopted_at'] = now()
            task.setdefault('adoptions', 0)
            task['adoptions'] += 1
            self._save(run, 'TASK_ADOPTED', {'task': task['id'], 'skill': task['skill'], 'by': adopter})
        return run

    def _revoke(self, run, gates):
        for gate in gates:
            if self.store.has_approval(run.run_id, gate):
                self.store.approval(run.run_id, gate, 'runtime', 'REVOKED', 'Supporting evidence changed', now(), run.metadata['scope_revision'])

    def start_task(self, run_id, skill):
        """Begin a governed task and return (task, context) for a handler or a cross-process CLI adapter."""
        with self.store.transaction():
            run = self._run(run_id)
            self._current_config(run)
            if run.metadata['active_task']:
                raise ValueError('A task is already active; recover only after its worker has stopped')
            item = self.registry.discover().get(skill)
            if not item or run.stage not in item['stages']:
                raise ValueError('Skill is not eligible for this stage')
            if item['revision'] != run.metadata['skill_pins'].get(skill):
                raise ValueError('Pinned skill content changed; start a new run')
            if run.stage not in {'INTAKE', 'CONTEXT'}:
                self._fresh(run)
            decision = evaluate(run.stage, {g: self.store.has_approval(run_id, g) for g in ('technical', 'release')})
            if not decision.allowed:
                raise ValueError('; '.join(decision.reasons))
            key = f"{run.metadata['scope_revision']}:{run.stage}:{skill}"
            attempts = run.metadata['attempts'].get(key, 0)
            if attempts > self._budget(run, 'max_agent_retries', skill):
                raise ValueError('Retry budget exhausted')
            run.metadata['attempts'][key] = attempts + 1
            task = {'id': uuid.uuid4().hex, 'skill': skill, 'started_at': now(), 'tool_calls': 0}
            run.metadata['active_task'] = task
            self._revoke(run, _STAGE_GATE_REVOKE.get(run.stage, ()))
            run.metadata['results'].pop(run.stage, None)
            run.metadata.setdefault('skill_results', {}).get(run.stage, {}).pop(skill, None)
            run.status = 'RUNNING'
            self.store.timing(run_id, task['id'], 'STARTED', task['started_at'], {'skill': skill, 'retry_count': attempts})
            self._save(run, 'TASK_STARTED', {'skill': skill})
        try:
            context = {'run': redact_value(run.to_dict()), 'skill_path': item['path'], 'instructions': Path(item['path']).read_text(encoding='utf-8'), 'context_files': {}}
            for name in run.metadata.get('context', {}).get('files', {}):
                # Recheck containment in case a path was replaced with a symlink.
                snapshot(run.metadata['repo'], [name])
                context['context_files'][name] = redact_value((Path(run.metadata['repo']) / name).read_text(encoding='utf-8'))
        except BaseException as exc:
            self.fail_task(run_id, task['id'], exc)
            raise
        return task, context

    def finish_task(self, run_id, task_id, result):
        """Validate and record a task's handoff envelope, closing the active task."""
        result = redact_value(validate_result(result))
        # Ensure persisted adapter outputs are JSON serializable before acceptance.
        json.dumps(result, allow_nan=False)
        with self.store.transaction():
            current, active = self._active(run_id, task_id)
            skill = active['skill']
            if self.registry.discover()[skill]['revision'] != current.metadata['skill_pins'][skill]:
                raise ValueError('Skill changed during execution')
            current.metadata['active_task'] = None
            # The stage verdict is the latest result; every skill's own result is kept beside it,
            # attributed, so a later skill at the same stage cannot overwrite another's verdict.
            current.metadata['results'][current.stage] = {**result, 'skill': skill}
            current.metadata.setdefault('skill_results', {}).setdefault(current.stage, {})[skill] = result
            if current.stage == 'IMPLEMENTATION':
                # Existing scope files are fingerprinted after this implementation attempt.
                current.metadata['context'] = snapshot(current.metadata['repo'], list(current.metadata['context']['files']))
            current.status = 'RUNNING' if result['status'] in SUCCESS_STATUSES else 'BLOCKED'
            duration = int((datetime.now(timezone.utc) - datetime.fromisoformat(active['started_at'])).total_seconds() * 1000)
            # A task opened and closed within seconds with no governed tool call only
            # records work done elsewhere; its duration is not execution time.
            post_hoc = active['tool_calls'] == 0 and duration < self.policy['post_hoc_threshold_seconds'] * 1000
            self.store.timing(run_id, task_id, 'COMPLETED', now(), {'duration_ms': duration, 'result_status': result['status'],
                                                                   'tool_calls': active['tool_calls'], 'post_hoc': post_hoc})
            self._save(current, 'RESULT_RECORDED', {'skill': skill, 'result': result, 'post_hoc': post_hoc})
        return result

    def fail_task(self, run_id, task_id, error):
        """Record an interrupted or errored task without replaying or accepting its result."""
        with self.store.transaction():
            current = self._run(run_id, allow_terminal=True)
            active = current.metadata['active_task']
            if active and active['id'] == task_id:
                current.metadata['active_task'] = None
                current.status = 'BLOCKED'
                duration = int((datetime.now(timezone.utc) - datetime.fromisoformat(active['started_at'])).total_seconds() * 1000)
                self.store.timing(run_id, task_id, 'FAILED', now(), {'error': str(error), 'duration_ms': duration})
                self._save(current, 'TASK_FAILED', {'error': str(error)})

    def execute(self, run_id, skill, handler):
        """Run a trusted adapter(context, call_tool) and validate its handoff."""
        task, context = self.start_task(run_id, skill)
        try:
            result = handler(context, lambda name, arguments=None, idempotency_key=None: self.call_tool(run_id, task['id'], name, arguments or {}, idempotency_key))
            return self.finish_task(run_id, task['id'], result)
        except BaseException as exc:
            self.fail_task(run_id, task['id'], exc)
            raise

    def guard(self, run_id, task_id, tool_name, command=None, tool_input=None):
        """Permission check for a native coding-agent tool call (e.g. a PreToolUse hook); never executes or replays it."""
        with self.store.transaction():
            run, task = self._active(run_id, task_id)
            if tool_name not in NATIVE_TOOL_CAPABILITY:
                raise PermissionError('Unrecognized native tool: ' + tool_name)
            _, side_effecting = NATIVE_TOOL_CAPABILITY[tool_name]
            permissions = self.permissions.get(task['skill'], [])
            required = 'read'
            if tool_name == 'Bash':
                _, required = command_rule(command, [], self.allowed_commands)
            elif side_effecting:
                path = (tool_input or {}).get('file_path') or (tool_input or {}).get('notebook_path')
                if not path:
                    raise PermissionError('Native writes require an explicit file path')
                required = 'modify_code' if 'modify_code' in permissions else 'write_artifact'
                validate_write(run.metadata['repo'], path, artifact_only=required == 'write_artifact')
            if required not in permissions:
                raise PermissionError('Native tool permission denied: ' + required)
            if side_effecting and run.dry_run:
                raise PermissionError('Native side effects are disabled in dry-run; use the gateway for simulation')
            if task['tool_calls'] >= self.policy['max_tool_calls_per_task']:
                raise ValueError('Tool call budget exhausted')
            task['tool_calls'] += 1
            self.store.audit(run_id, 'NATIVE_TOOL_GUARDED', {'tool': tool_name, 'command': command}, now())
            self._save(run, 'NATIVE_TOOL_GUARDED', {'tool': tool_name})
        return {'allowed': True, 'tool': tool_name}

    def call_tool(self, run_id, task_id, name, arguments, idempotency_key=None):
        try:
            return self._call_tool(run_id, task_id, name, arguments, idempotency_key)
        except BaseException as exc:
            self.store.audit(run_id, 'TOOL_ERROR', {'name': name, 'error': str(exc)}, now())
            raise

    def _call_tool(self, run_id, task_id, name, arguments, idempotency_key=None):
        if not isinstance(arguments, dict) or any(not isinstance(key, str) for key in arguments):
            raise ValueError('Tool arguments must be an object with string keys')
        if idempotency_key is not None and (not isinstance(idempotency_key, str) or not idempotency_key.strip()):
            raise ValueError('Idempotency key must be a nonempty string')
        # Reserve before invoking: a crash leaves an unknown outcome, never an automatic replay.
        with self.store.transaction():
            run, task = self._active(run_id, task_id)
            if not self.tools.allowed(name, self.capabilities.get(task['skill']), self.permissions.get(task['skill'], [])):
                raise PermissionError('Tool capability denied: ' + name)
            tool = self.tools.tools[name]
            try:
                inspect.signature(tool['handler']).bind(**arguments)
            except TypeError as exc:
                params = ', '.join(inspect.signature(tool['handler']).parameters)
                raise ValueError(f'Invalid arguments for tool {name} ({exc}); accepted: {params}') from None
            if task['tool_calls'] >= self.policy['max_tool_calls_per_task']:
                raise ValueError('Tool call budget exhausted')
            if tool['side_effecting'] and not idempotency_key:
                raise ValueError('Side-effecting tools require an idempotency key')
            payload = {'name': name, 'arguments': arguments}
            digest = hashlib.sha256(json.dumps(payload, sort_keys=True, allow_nan=False).encode()).hexdigest()
            call_key = f"{run.metadata['scope_revision']}:{idempotency_key}" if idempotency_key else uuid.uuid4().hex
            if tool['side_effecting'] and run.dry_run:
                task['tool_calls'] += 1
                self._save(run, 'TOOL_DRY_RUN', {'name': name})
                return {'dry_run': True, 'tool': name, 'invoked': False}
            previous = self.store.get_tool_call(run_id, call_key)
            if previous:
                if previous['request_hash'] != digest:
                    raise ValueError('Idempotency key reused for a different request')
                if previous['status'] != 'COMPLETED':
                    raise ValueError('Previous tool outcome unknown or failed; reconcile before a new attempt')
                return previous['result']
            task['tool_calls'] += 1
            self.store.record_tool_call(run_id, call_key, digest, 'STARTED')
            self._save(run, 'TOOL_STARTED', {'name': name, 'call_key': call_key})
        try:
            output = redact_value(tool['handler'](**arguments))
            json.dumps(output, allow_nan=False)
            with self.store.transaction():
                self.store.update_tool_call_status(run_id, call_key, 'COMPLETED', result=output)
                self.store.audit(run_id, 'TOOL_COMPLETED', {'name': name}, now())
            # Cancellation/timeouts cannot undo a completed external effect.
            self._active(run_id, task_id)
            return output
        except BaseException as exc:
            with self.store.transaction():
                self.store.update_tool_call_status(run_id, call_key, 'FAILED', expected_status='STARTED')
                self.store.audit(run_id, 'TOOL_FAILED', {'name': name, 'error': str(exc)}, now())
            raise
