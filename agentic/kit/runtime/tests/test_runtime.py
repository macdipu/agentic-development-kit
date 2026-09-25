from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from unittest.mock import patch

from support import HarnessCase, ready
from agentic_runtime.context import snapshot_state
from agentic_runtime.policy import auto_approve_eligible
from agentic_runtime.registry import ToolRegistry
from agentic_runtime.tools import bash_allowed


class RuntimeTests(HarnessCase):
    def test_order_and_evidence_are_required(self):
        self.start()
        for stage in ('CONTEXT', 'QA', 'COMPLETED'):
            with self.assertRaises(ValueError):
                self.orch.transition(self.run_id, stage)
        with self.assertRaises(ValueError):
            self.orch.execute(self.run_id, 'prompt-intake-adapter', lambda c, t: ready(''))
        self.assertEqual(self.store.get_run(self.run_id).status, 'BLOCKED')

    def test_rejection_and_revocation_prevent_implementation(self):
        self.context('existing_task')
        self.orch.approve(self.run_id, 'technical', 'fixture', 'REJECTED')
        with self.assertRaises(ValueError):
            self.orch.transition(self.run_id, 'IMPLEMENTATION')
        self.orch.approve(self.run_id, 'technical', 'fixture')
        self.result('baseline-verifier')
        self.assertFalse(self.store.has_approval(self.run_id, 'technical'))

    def test_stale_and_deleted_context_rejected(self):
        self.context()
        (self.root / 'scope.md').write_text('Changed outside task', encoding='utf-8', newline='\n')
        with self.assertRaisesRegex(ValueError, 'STALE'):
            self.orch.transition(self.run_id, 'REVIEW')
        (self.root / 'scope.md').unlink()
        with self.assertRaisesRegex(ValueError, 'STALE'):
            self.orch.transition(self.run_id, 'REVIEW')

    def test_scope_reopen_invalidates_approvals(self):
        self.implementation()
        self.orch.reopen(self.run_id, 'Changed requirement')
        self.assertFalse(self.store.has_approval(self.run_id, 'technical'))
        self.assertEqual(set(self.store.get_run(self.run_id).metadata['results']), {'INTAKE'})

    def test_scoped_context_refresh_avoids_reopen_at_technical_stage(self):
        self.context('bug')
        self.orch.transition(self.run_id, 'IMPACT')
        self.result('agentic-sdlc-orchestrator')
        self.orch.transition(self.run_id, 'TECHNICAL')
        self.result('agentic-sdlc-orchestrator')
        self.orch.approve(self.run_id, 'technical', 'fixture')
        (self.root / 'scope.md').write_text('Updated fixture scope\n', encoding='utf-8', newline='\n')
        self.orch.record_context(self.run_id, ['scope.md'])
        run = self.store.get_run(self.run_id)
        self.assertNotIn('TECHNICAL', run.metadata['results'])
        self.assertFalse(self.store.has_approval(self.run_id, 'technical'))
        self.assertEqual(run.status, 'RUNNING')

    def test_context_refresh_without_precedent_still_requires_reopen(self):
        self.context('new_feature')
        self.orch.transition(self.run_id, 'REQUIREMENTS')
        self.result('agentic-sdlc-orchestrator')
        (self.root / 'scope.md').write_text('Changed again\n', encoding='utf-8', newline='\n')
        with self.assertRaisesRegex(ValueError, 'reopen the run'):
            self.orch.record_context(self.run_id, ['scope.md'])

    def _auto_candidate(self, *scope, classification='TASK_ONLY', verdict='TECHNICAL_READY', verifier='technical-readiness-verifier'):
        self.start('existing_task')
        self.result('prompt-intake-adapter')
        self.orch.transition(self.run_id, 'CONTEXT')
        self.orch.record_context(self.run_id, list(scope or ['scope.md']))
        self.orch.execute(self.run_id, 'work-item-level-classifier', lambda c, t: ready(
            classification=classification, sprint_handling='NO_REPLAN', work_item_id='FIX-1'))
        self.orch.execute(self.run_id, verifier, lambda c, t: ready(verdict=verdict))

    def test_auto_approve_accepts_task_only_single_file_technical_ready(self):
        self._auto_candidate()
        self.orch.auto_approve(self.run_id, 'technical', 'single-file task-only fix; verifier says ready')
        self.assertTrue(self.store.has_approval(self.run_id, 'technical'))
        approvals = self.store._view(self.run_id)['approvals']
        self.assertEqual(approvals[-1]['approver'], 'runtime:auto')
        self.orch.transition(self.run_id, 'IMPLEMENTATION')

    def test_auto_approve_survives_later_result_at_same_stage(self):
        # Both verdicts are recorded at CONTEXT; the second result must not erase the first.
        self._auto_candidate()
        run = self.store.get_run(self.run_id)
        self.assertEqual(set(run.metadata['skill_results']['CONTEXT']),
                         {'work-item-level-classifier', 'technical-readiness-verifier'})
        self.assertEqual(run.metadata['results']['CONTEXT']['skill'], 'technical-readiness-verifier')
        self.orch.auto_approve(self.run_id, 'technical', 'reason')

    def test_auto_approve_rejects_missing_task_only_classification(self):
        self._auto_candidate(classification='STORY_TASK')
        with self.assertRaisesRegex(ValueError, 'Not eligible for auto-approval'):
            self.orch.auto_approve(self.run_id, 'technical', 'reason')

    def test_auto_approve_rejects_verdict_from_another_skill(self):
        self._auto_candidate(verifier='baseline-verifier')
        with self.assertRaisesRegex(ValueError, 'Not eligible for auto-approval'):
            self.orch.auto_approve(self.run_id, 'technical', 'reason')

    def test_auto_approve_rejects_multi_file_scope(self):
        (self.root / 'scope2.md').write_text('Second fixture scope\n', encoding='utf-8', newline='\n')
        self._auto_candidate('scope.md', 'scope2.md')
        with self.assertRaisesRegex(ValueError, 'Not eligible for auto-approval'):
            self.orch.auto_approve(self.run_id, 'technical', 'reason')

    def test_auto_approve_gate_is_never_applicable_to_release_or_uat(self):
        evidence = {'QA': {'work-item-level-classifier': {'status': 'READY', 'outputs': {'classification': 'TASK_ONLY'}},
                           'technical-readiness-verifier': {'status': 'READY', 'outputs': {'verdict': 'TECHNICAL_READY'}}}}
        self.assertTrue(auto_approve_eligible('technical', evidence, {'a': 'hash'}))
        self.assertFalse(auto_approve_eligible('release', evidence, {'a': 'hash'}))
        self.assertFalse(auto_approve_eligible('uat', evidence, {'a': 'hash'}))

    def test_permission_matrix_supports_work_without_source_write_escalation(self):
        self.start()
        task, _ = self.orch.start_task(self.run_id, 'prompt-intake-adapter')
        call = lambda name, args: self.orch.call_tool(self.run_id, task['id'], name, args, name)
        call('write_artifact', {'path': 'agentic/data/artifacts/intake.md', 'content': 'Draft'})
        for name, args in [('write_file', {'path': 'source.py', 'content': 'bad'}),
                           ('write_artifact', {'path': 'source.py', 'content': 'bad'}),
                           ('run_command', {'command': 'git status'})]:
            with self.assertRaises((PermissionError, ValueError)):
                call(name, args)
        self.assertFalse((self.root / 'source.py').exists())

    def test_search_does_not_read_external_symlinks(self):
        outside = self.root.parent / (self.root.name + '-outside.txt')
        outside.write_text('PRIVATE_SENTINEL', encoding='utf-8', newline='\n')
        self.addCleanup(lambda: outside.unlink(missing_ok=True))
        (self.root / 'external.txt').symlink_to(outside)
        self.start()
        task, _ = self.orch.start_task(self.run_id, 'prompt-intake-adapter')
        result = self.orch.call_tool(self.run_id, task['id'], 'search_text', {'pattern': 'PRIVATE_SENTINEL'})
        self.assertEqual(result['matches'], [])
        with self.assertRaises(ValueError):
            self.orch.call_tool(self.run_id, task['id'], 'read_file', {'path': 'external.txt'})

    def test_full_argv_required(self):
        rules = ['git diff', {'argv': ['flutter', 'run', '-d', 'fixture', '--detach'], 'permission': 'preview'}]
        self.assertTrue(bash_allowed('git diff', rules))
        for command in ('git diff --output=outside', 'git diff; true', 'git diff\ntrue', 'git diff | true'):
            self.assertFalse(bash_allowed(command, rules))
        self.assertTrue(bash_allowed('flutter run -d fixture --detach', rules))
        self.assertFalse(bash_allowed('flutter run -d another --detach', rules))

    def test_retry_deadline_and_tool_budget(self):
        self.start()
        for _ in range(3):
            with self.assertRaisesRegex(RuntimeError, 'fixture failure'):
                self.orch.execute(self.run_id, 'prompt-intake-adapter', lambda c, t: (_ for _ in ()).throw(RuntimeError('fixture failure')))
        with self.assertRaisesRegex(ValueError, 'Retry budget'):
            self.result('prompt-intake-adapter')
        self.start()
        task, _ = self.orch.start_task(self.run_id, 'prompt-intake-adapter')
        run = self.store.get_run(self.run_id)
        run.metadata['active_task']['tool_calls'] = 50
        self.store.save_run(run)
        with self.assertRaisesRegex(ValueError, 'budget'):
            self.orch.call_tool(self.run_id, task['id'], 'read_file', {'path': 'scope.md'})
        run.metadata['active_task']['started_at'] = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        self.store.save_run(run)
        with self.assertRaises(TimeoutError):
            self.orch.finish_task(self.run_id, task['id'], ready())

    def test_cancellation_rejects_late_result(self):
        self.start()
        task, _ = self.orch.start_task(self.run_id, 'prompt-intake-adapter')
        self.orch.cancel(self.run_id)
        with self.assertRaises(ValueError):
            self.orch.finish_task(self.run_id, task['id'], ready())
        self.orch.fail_task(self.run_id, task['id'], 'late failure')
        self.assertEqual(self.store.get_run(self.run_id).status, 'CANCELLED')

    def test_budget_adjustment_retains_attempts_and_enforces_new_limits(self):
        self.start()
        for _ in range(3):
            self.result('prompt-intake-adapter')
        with self.assertRaisesRegex(ValueError, 'Retry budget'):
            self.result('prompt-intake-adapter')
        self.orch.adjust_budget(self.run_id, 'fixture-operator', 'Explicit fixture authorization', 3, 1800)
        task, _ = self.orch.start_task(self.run_id, 'prompt-intake-adapter')
        run = self.store.get_run(self.run_id)
        self.assertEqual(run.metadata['attempts']['0:INTAKE:prompt-intake-adapter'], 4)
        run.metadata['active_task']['started_at'] = (datetime.now(timezone.utc) - timedelta(seconds=1000)).isoformat()
        self.store.save_run(run)
        self.orch.finish_task(self.run_id, task['id'], ready())
        with self.assertRaisesRegex(ValueError, 'Retry budget'):
            self.result('prompt-intake-adapter')
        records = self.store._view(self.run_id)
        self.assertIn('BUDGET_ADJUSTED', json.dumps(records['audit_events']))
        self.start()
        self.assertNotIn('budget_overrides', self.store.get_run(self.run_id).metadata)

    def test_budget_adjustment_validation_and_approval_preservation(self):
        self.implementation()
        before = self.store.get_run(self.run_id).to_dict()
        for values in ({}, {'max_task_seconds': 0}, {'max_agent_retries': -1}, {'max_task_seconds': True}):
            with self.assertRaises(ValueError):
                self.orch.adjust_budget(self.run_id, 'fixture', 'Authorized', **values)
        with self.assertRaises(ValueError):
            self.orch.adjust_budget(self.run_id, '', 'Authorized', max_task_seconds=1800)
        with self.assertRaises(ValueError):
            self.orch.adjust_budget(self.run_id, 'fixture', ' ', max_task_seconds=1800)
        self.assertEqual(before, self.store.get_run(self.run_id).to_dict())
        self.orch.adjust_budget(self.run_id, 'fixture', 'Authorized', max_task_seconds=1800)
        self.assertTrue(self.store.has_approval(self.run_id, 'technical'))
        self.assertFalse(self.store.has_approval(self.run_id, 'release'))
        task, _ = self.orch.start_task(self.run_id, 'implementation-agent')
        with self.assertRaisesRegex(ValueError, 'active task'):
            self.orch.adjust_budget(self.run_id, 'fixture', 'Authorized', max_task_seconds=3600)
        run = self.store.get_run(self.run_id)
        run.metadata['active_task']['started_at'] = (datetime.now(timezone.utc) - timedelta(seconds=1801)).isoformat()
        self.store.save_run(run)
        with self.assertRaises(TimeoutError):
            self.orch.finish_task(self.run_id, task['id'], ready())
        self.orch.cancel(self.run_id)
        with self.assertRaisesRegex(ValueError, 'terminal'):
            self.orch.adjust_budget(self.run_id, 'fixture', 'Authorized', max_task_seconds=3600)

    def test_recovery_preserves_attempt_and_unknown_tool_outcome(self):
        self.start()
        task, _ = self.orch.start_task(self.run_id, 'prompt-intake-adapter')
        self.orch.recover(self.run_id, 'Fixture worker stopped')
        next_task, _ = self.orch.start_task(self.run_id, 'prompt-intake-adapter')
        self.assertNotEqual(task['id'], next_task['id'])
        self.assertEqual(self.store.get_run(self.run_id).metadata['attempts']['0:INTAKE:prompt-intake-adapter'], 2)

    def test_idempotency_and_failed_effect_replay(self):
        calls = []
        self.tools.register('effect', lambda value: calls.append(value) or {'value': value}, 'L2', True)
        self.start()
        task, _ = self.orch.start_task(self.run_id, 'prompt-intake-adapter')
        for _ in range(2):
            self.orch.call_tool(self.run_id, task['id'], 'effect', {'value': 1}, 'stable')
        self.assertEqual(calls, [1])
        with self.assertRaises(ValueError):
            self.orch.call_tool(self.run_id, task['id'], 'effect', {'value': 2}, 'stable')
        self.tools.register('failure', lambda: (_ for _ in ()).throw(RuntimeError('external failure')), 'L2', True)
        with self.assertRaises(RuntimeError):
            self.orch.call_tool(self.run_id, task['id'], 'failure', {}, 'failed')
        with self.assertRaisesRegex(ValueError, 'reconcile'):
            self.orch.call_tool(self.run_id, task['id'], 'failure', {}, 'failed')

    def test_dry_run_suppresses_gateway_and_denies_native_effects(self):
        self.implementation(dry_run=True)
        task, _ = self.orch.start_task(self.run_id, 'implementation-agent')
        result = self.orch.call_tool(self.run_id, task['id'], 'write_file', {'path': 'new.py', 'content': 'test'}, 'write')
        self.assertFalse(result['invoked'])
        self.assertFalse((self.root / 'new.py').exists())
        with self.assertRaisesRegex(PermissionError, 'dry-run'):
            self.orch.guard(self.run_id, task['id'], 'Write', tool_input={'file_path': str(self.root / 'new.py')})

    def test_checkpoint_failure_rolls_back_run_audit_and_timing(self):
        self.start()
        before = self.store.get_run(self.run_id).to_dict()
        count = len(self.store._view(self.run_id).get('audit_events', []))
        # The transaction's single event write fails: nothing of it may persist.
        with patch.object(self.store, '_write_event', side_effect=OSError('fixture disk failure')):
            with self.assertRaises(OSError):
                self.orch.start_task(self.run_id, 'prompt-intake-adapter')
        self.assertEqual(self.store.get_run(self.run_id).to_dict(), before)
        self.assertEqual(len(self.store._view(self.run_id).get('audit_events', [])), count)
        self.assertEqual(self.store.query_timing(self.run_id), [])

    def test_config_and_skill_pins_reject_changes(self):
        self.start()
        path = self.kit / 'skills/prompt-intake-adapter/SKILL.md'
        path.write_text(path.read_text(encoding='utf-8') + '\nChanged fixture\n', encoding='utf-8', newline='\n')
        with self.assertRaisesRegex(ValueError, 'Pinned'):
            self.result('prompt-intake-adapter')
        path = self.kit / 'config/permissions.json'
        path.write_text(path.read_text(encoding='utf-8') + '\n', encoding='utf-8', newline='\n')
        with self.assertRaisesRegex(ValueError, 'Configuration changed'):
            self.result('prompt-intake-adapter')

    def test_uat_requires_explicit_current_approval(self):
        policy_path = self.kit / 'config/platform.json'
        policy = json.loads(policy_path.read_text(encoding='utf-8'))
        policy['require_uat_approval'] = True
        policy_path.write_text(json.dumps(policy), encoding='utf-8', newline='\n')
        self.orch = type(self.orch)(self.store, self.kit, self.tools)
        self.implementation()
        self.result('implementation-agent')
        self.orch.transition(self.run_id, 'REVIEW')
        self.result('code-review-agent')
        self.orch.transition(self.run_id, 'QA')
        self.result('automated-qa-agent')
        self.orch.transition(self.run_id, 'UAT')
        self.result('agentic-sdlc-orchestrator')
        self.orch.approve(self.run_id, 'release', 'synthetic reviewer')
        with self.assertRaisesRegex(ValueError, 'UAT'):
            self.orch.transition(self.run_id, 'RELEASE')
        self.orch.approve(self.run_id, 'uat', 'synthetic reviewer')
        self.orch.transition(self.run_id, 'RELEASE')
        self.result('release-readiness-agent')
        self.orch.approve(self.run_id, 'release', 'synthetic reviewer', 'REVOKED')
        with self.assertRaisesRegex(ValueError, 'release'):
            self.orch.transition(self.run_id, 'COMPLETED')


class CompactionTests(HarnessCase):
    def test_terminal_run_keeps_audit_but_drops_resume_only_state(self):
        self.context()
        task, _ = self.orch.start_task(self.run_id, 'baseline-verifier')
        self.orch.call_tool(self.run_id, task['id'], 'read_file', {'path': 'scope.md'})
        self.orch.finish_task(self.run_id, task['id'], ready())
        before = self.store.ledger(self.run_id)
        self.assertGreater(len(before['checkpoints']), 2)
        self.orch.cancel(self.run_id)
        after = self.store.ledger(self.run_id)
        self.assertEqual(len(after['checkpoints']), 2)
        self.assertEqual(after['compacted_checkpoints'], len(before['checkpoints']) + 1 - 2)
        self.assertGreaterEqual(len(after['audit_events']), len(before['audit_events']))
        self.assertTrue(all('result' not in c for c in after['tool_calls'].values()))
        self.assertTrue(all('request_hash' in c for c in after['tool_calls'].values()))
