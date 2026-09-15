from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
from unittest.mock import patch

from support import HarnessCase, ready
from agentic_runtime.context import snapshot_state
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
        (self.root / 'scope.md').write_text('Changed outside task')
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
        outside.write_text('PRIVATE_SENTINEL')
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
        count = self.store.conn.execute('SELECT count(*) FROM audit_events').fetchone()[0]
        with patch.object(self.store, 'checkpoint', side_effect=sqlite3.OperationalError('fixture disk failure')):
            with self.assertRaises(sqlite3.OperationalError):
                self.orch.start_task(self.run_id, 'prompt-intake-adapter')
        self.assertEqual(self.store.get_run(self.run_id).to_dict(), before)
        self.assertEqual(self.store.conn.execute('SELECT count(*) FROM audit_events').fetchone()[0], count)
        self.assertEqual(self.store.query_timing(self.run_id), [])

    def test_config_and_skill_pins_reject_changes(self):
        self.start()
        path = self.kit / 'skills/prompt-intake-adapter/SKILL.md'
        path.write_text(path.read_text() + '\nChanged fixture\n')
        with self.assertRaisesRegex(ValueError, 'Pinned'):
            self.result('prompt-intake-adapter')
        path = self.kit / 'config/permissions.json'
        path.write_text(path.read_text() + '\n')
        with self.assertRaisesRegex(ValueError, 'Configuration changed'):
            self.result('prompt-intake-adapter')

    def test_uat_requires_explicit_current_approval(self):
        policy_path = self.kit / 'config/platform.json'
        policy = json.loads(policy_path.read_text())
        policy['require_uat_approval'] = True
        policy_path.write_text(json.dumps(policy))
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
