import contextlib
import io
import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

KIT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(KIT / 'runtime/python'))
from agentic_runtime.cli import main as cli_main
from agentic_runtime.context import context_state, snapshot, snapshot_state
from agentic_runtime.contracts import validate_result
from agentic_runtime.orchestrator import Orchestrator, now
from agentic_runtime.policy import workflow_route
from agentic_runtime.registry import ToolRegistry
from agentic_runtime.store import RuntimeStore


def ready(status='READY'):
    return {'status': status, 'evidence': ['requirements.md#verified'], 'blocking_issues': [], 'open_questions': [], 'recommended_next_step': 'Continue after required gates', 'outputs': {}}


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.kit = self.root / 'agentic'
        shutil.copytree(KIT / 'config', self.kit / 'config')
        shutil.copytree(KIT / 'skills', self.kit / 'skills')
        self.source = self.root / 'requirements.md'
        self.source.write_text('Confirmed scope')
        self.store = RuntimeStore(str(self.root / 'state.sqlite3'))
        self.addCleanup(self.store.conn.close)
        self.tools = ToolRegistry()
        self.orch = Orchestrator(self.store, self.kit, self.tools)

    def start(self, work_type='device_preview', dry_run=False):
        return self.orch.start('test', work_type, 'Test work', dry_run, self.root)

    def submit(self, run, skill='agentic-sdlc-orchestrator', result=None):
        return self.orch.execute(run.run_id, skill, lambda context, call: ready() if result is None else result)

    def context_ready(self, work_type='device_preview', dry_run=False):
        run = self.start(work_type, dry_run)
        self.submit(run, 'prompt-intake-adapter')
        self.orch.transition(run.run_id, 'CONTEXT')
        self.orch.record_context(run.run_id, ['requirements.md'])
        self.submit(run, 'baseline-verifier')
        return run

    def technical_ready(self):
        run = self.context_ready('technical_change')
        for stage, skill in [('IMPACT', 'change-impact-analyzer'), ('TECHNICAL', 'technical-readiness-verifier')]:
            self.orch.transition(run.run_id, stage)
            self.submit(run, skill)
        return run

    def test_unknown_stage_and_skipped_prerequisites_rejected(self):
        run = self.start()
        for stage in ['IMPLEMENTATON', 'RELEASE', 'COMPLETED']:
            with self.assertRaises(ValueError):
                self.orch.transition(run.run_id, stage)
        self.assertEqual(self.store.get_run(run.run_id).stage, 'INTAKE')
        with self.assertRaises(ValueError):
            self.orch.transition(run.run_id, 'CONTEXT')
        with self.assertRaisesRegex(ValueError, 'Complete intake'):
            self.orch.reopen(run.run_id, 'Attempt to skip intake')

    def test_preview_end_to_end_and_terminal_state(self):
        run = self.context_ready()
        self.orch.transition(run.run_id, 'PREVIEW')
        self.submit(run, 'device-preview-agent', ready('PREVIEW_READY'))
        completed = self.orch.transition(run.run_id, 'COMPLETED')
        self.assertEqual(completed.status, 'COMPLETED')
        with self.assertRaises(ValueError):
            self.submit(run)

    def test_preview_cannot_complete_without_visual_verdict(self):
        run = self.context_ready()
        self.orch.transition(run.run_id, 'PREVIEW')
        self.submit(run, 'device-preview-agent')
        with self.assertRaisesRegex(ValueError, 'visual verification'):
            self.orch.transition(run.run_id, 'COMPLETED')

    def test_stale_preview_cannot_complete(self):
        run = self.context_ready()
        self.orch.transition(run.run_id, 'PREVIEW')
        self.submit(run, 'device-preview-agent', ready('PREVIEW_READY'))
        self.source.write_text('Changed after preview')
        with self.assertRaisesRegex(ValueError, 'STALE'):
            self.orch.transition(run.run_id, 'COMPLETED')

    def test_approval_requires_ready_evidence_and_reopen_invalidates(self):
        run = self.start('technical_change')
        with self.assertRaises(ValueError):
            self.orch.approve(run.run_id, 'release', 'test-fixture')
        run = self.technical_ready()
        with self.assertRaises(ValueError):
            self.orch.transition(run.run_id, 'IMPLEMENTATION')
        self.orch.approve(run.run_id, 'technical', 'test-fixture')
        self.orch.transition(run.run_id, 'IMPLEMENTATION')
        self.orch.reopen(run.run_id, 'Changed acceptance criteria')
        self.assertFalse(self.store.has_approval(run.run_id, 'technical'))
        self.assertEqual(self.store.get_run(run.run_id).metadata['results'].keys(), {'INTAKE'})

    def test_resubmitted_technical_evidence_revokes_approval(self):
        run = self.technical_ready()
        self.orch.approve(run.run_id, 'technical', 'test-fixture')
        self.submit(run, 'technical-readiness-verifier')
        self.assertFalse(self.store.has_approval(run.run_id, 'technical'))

    def test_release_workflow_requires_both_gates(self):
        run = self.technical_ready()
        self.orch.approve(run.run_id, 'technical', 'test-fixture')
        for stage, skill in [('IMPLEMENTATION', 'implementation-agent'), ('REVIEW', 'code-review-agent'), ('QA', 'automated-qa-agent')]:
            self.orch.transition(run.run_id, stage)
            self.submit(run, skill)
        with self.assertRaises(ValueError):
            self.orch.transition(run.run_id, 'RELEASE')
        self.orch.approve(run.run_id, 'release', 'test-fixture')
        self.orch.transition(run.run_id, 'RELEASE')
        self.submit(run, 'release-readiness-agent')
        self.assertEqual(self.orch.transition(run.run_id, 'COMPLETED').status, 'COMPLETED')

    def test_optional_uat_gate_is_enforced(self):
        path = self.kit / 'config/platform.json'
        policy = json.loads(path.read_text())
        policy['require_uat_approval'] = True
        path.write_text(json.dumps(policy))
        self.orch = Orchestrator(self.store, self.kit)
        run = self.technical_ready()
        self.orch.approve(run.run_id, 'technical', 'test-fixture')
        for stage, skill in [('IMPLEMENTATION','implementation-agent'), ('REVIEW','code-review-agent'), ('QA','automated-qa-agent'), ('UAT','agentic-sdlc-orchestrator')]:
            self.orch.transition(run.run_id, stage)
            self.submit(run, skill)
        self.orch.approve(run.run_id, 'release', 'test-fixture')
        with self.assertRaisesRegex(ValueError, 'UAT approval'):
            self.orch.transition(run.run_id, 'RELEASE')
        self.orch.approve(run.run_id, 'uat', 'test-fixture')
        self.assertEqual(self.orch.transition(run.run_id, 'RELEASE').stage, 'RELEASE')

    def test_approval_rejection_during_execution_prevents_acceptance(self):
        run = self.technical_ready()
        self.orch.approve(run.run_id, 'technical', 'test-fixture')
        self.orch.transition(run.run_id, 'IMPLEMENTATION')
        def revoked(context, call):
            self.orch.approve(run.run_id, 'technical', 'test-fixture', decision='REJECTED')
            return ready()
        with self.assertRaises(PermissionError):
            self.orch.execute(run.run_id, 'implementation-agent', revoked)
        self.assertNotIn('IMPLEMENTATION', self.store.get_run(run.run_id).metadata['results'])

    def test_checkpoint_failure_rolls_back_state_and_audit(self):
        run = self.start()
        self.submit(run)
        before = self.store.conn.execute('SELECT COUNT(*) FROM checkpoints').fetchone()[0]
        audits = self.store.conn.execute('SELECT COUNT(*) FROM audit_events').fetchone()[0]
        with patch.object(self.store, 'checkpoint', side_effect=sqlite3.OperationalError('injected')):
            with self.assertRaises(sqlite3.OperationalError):
                self.orch.transition(run.run_id, 'CONTEXT')
        self.assertEqual(self.store.get_run(run.run_id).stage, 'INTAKE')
        self.assertEqual(self.store.conn.execute('SELECT COUNT(*) FROM checkpoints').fetchone()[0], before)
        self.assertEqual(self.store.conn.execute('SELECT COUNT(*) FROM audit_events').fetchone()[0], audits)

    def test_context_dirty_changes_missing_files_and_unknown_revision(self):
        run = self.context_ready()
        self.source.write_text('Changed')
        with self.assertRaisesRegex(ValueError, 'STALE'):
            self.orch.transition(run.run_id, 'PREVIEW')
        self.assertEqual(context_state('UNKNOWN', 'UNKNOWN'), 'MISSING')
        state = snapshot(self.root, ['requirements.md'])
        self.source.unlink()
        self.assertEqual(snapshot_state(self.root, state), 'STALE')

    def test_unrelated_changes_do_not_invalidate_context(self):
        run = self.context_ready()
        (self.root / 'unrelated.txt').write_text('Unrelated work')
        self.assertEqual(self.orch.transition(run.run_id, 'PREVIEW').stage, 'PREVIEW')

    def test_context_paths_cannot_escape_project(self):
        run = self.start()
        with self.assertRaises(ValueError):
            self.orch.record_context(run.run_id, ['../missing.md'])
        link = self.root / 'outside.md'
        link.symlink_to(Path(__file__).resolve())
        with self.assertRaises(ValueError):
            self.orch.record_context(run.run_id, ['outside.md'])

    def test_changed_review_scope_cannot_be_silently_refreshed(self):
        run = self.technical_ready()
        self.source.write_text('Different acceptance criteria')
        with self.assertRaisesRegex(ValueError, 'reopen'):
            self.orch.record_context(run.run_id, ['requirements.md'])

    def test_implementation_updates_context_for_following_review(self):
        run = self.technical_ready()
        self.orch.approve(run.run_id, 'technical', 'test-fixture')
        self.orch.transition(run.run_id, 'IMPLEMENTATION')
        def implement(context, call):
            self.source.write_text('Updated implementation evidence')
            return ready()
        self.orch.execute(run.run_id, 'implementation-agent', implement)
        self.assertEqual(self.orch.transition(run.run_id, 'REVIEW').stage, 'REVIEW')

    def test_stage_eligibility_and_content_pin(self):
        run = self.start()
        with self.assertRaisesRegex(ValueError, 'eligible'):
            self.submit(run, 'implementation-agent')
        path = self.kit / 'skills/prompt-intake-adapter/SKILL.md'
        path.write_text(path.read_text() + '\nChanged instructions\n')
        with self.assertRaisesRegex(ValueError, 'Pinned'):
            self.submit(run, 'prompt-intake-adapter')

    def test_reference_changes_are_pinned(self):
        run = self.context_ready()
        self.orch.transition(run.run_id, 'PREVIEW')
        path = self.kit / 'skills/device-preview-agent/references/android.md'
        path.write_text(path.read_text() + '\nChanged commands\n')
        with self.assertRaisesRegex(ValueError, 'Pinned'):
            self.submit(run, 'device-preview-agent')

    def test_config_change_is_not_silently_adopted(self):
        run = self.start()
        path = self.kit / 'config/platform.json'
        path.write_text(path.read_text() + '\n')
        with self.assertRaisesRegex(ValueError, 'Configuration changed'):
            self.submit(run)
        with self.assertRaisesRegex(ValueError, 'reload'):
            self.start()

    def test_retry_budget_and_failure_telemetry(self):
        run = self.start()
        def fail(context, call):
            raise RuntimeError('token=do-not-persist')
        for _ in range(3):
            with self.assertRaises(RuntimeError):
                self.orch.execute(run.run_id, 'prompt-intake-adapter', fail)
        with self.assertRaisesRegex(ValueError, 'Retry budget'):
            self.orch.execute(run.run_id, 'prompt-intake-adapter', fail)
        events = self.store.conn.execute('SELECT * FROM timing_events').fetchall()
        self.assertEqual(len(events), 6)
        self.assertNotIn('do-not-persist', str([dict(row) for row in events]))

    def test_cancel_during_adapter_blocks_result(self):
        run = self.start()
        def cancelled(context, call):
            self.orch.cancel(run.run_id)
            return ready()
        with self.assertRaisesRegex(ValueError, 'terminal'):
            self.orch.execute(run.run_id, 'prompt-intake-adapter', cancelled)
        stored = self.store.get_run(run.run_id)
        self.assertEqual(stored.status, 'CANCELLED')
        self.assertNotIn('INTAKE', stored.metadata['results'])

    def test_concurrent_attempt_is_rejected_and_recovery_does_not_replay(self):
        run = self.start()
        def outer(context, call):
            with self.assertRaisesRegex(ValueError, 'already active'):
                self.submit(run, 'prompt-intake-adapter')
            return ready()
        self.orch.execute(run.run_id, 'prompt-intake-adapter', outer)
        stored = self.store.get_run(run.run_id)
        stored.metadata['active_task'] = {'id':'interrupted', 'started_at':now(), 'skill':'prompt-intake-adapter', 'tool_calls':0}
        self.store.save_run(stored)
        self.orch.recover(run.run_id, 'Fixture worker exited')
        self.assertEqual(self.store.get_run(run.run_id).status, 'BLOCKED')
        self.assertIsNone(self.store.get_run(run.run_id).metadata['active_task'])

    def test_task_timeout_rejects_late_result(self):
        run = self.start()
        def slow(context, call):
            stored = self.store.get_run(run.run_id)
            stored.metadata['active_task']['started_at'] = '2000-01-01T00:00:00+00:00'
            self.store.save_run(stored)
            return ready()
        with self.assertRaises(TimeoutError):
            self.orch.execute(run.run_id, 'prompt-intake-adapter', slow)
        self.assertNotIn('INTAKE', self.store.get_run(run.run_id).metadata['results'])

    def test_capability_denial_and_idempotency(self):
        calls = []
        self.tools.register('write', lambda: calls.append('write'), 'L4', True)
        run = self.start()
        with self.assertRaises(PermissionError):
            self.orch.execute(run.run_id, 'prompt-intake-adapter', lambda context, call: call('write', idempotency_key='one'))
        self.assertEqual(calls, [])
        self.tools.register('artifact', lambda text: calls.append(text) or {'saved':True}, 'L2', True)
        def artifact(context, call):
            first = call('artifact', {'text':'value'}, 'same')
            self.assertEqual(first, call('artifact', {'text':'value'}, 'same'))
            with self.assertRaisesRegex(ValueError, 'different request'):
                call('artifact', {'text':'different'}, 'same')
            return ready()
        self.orch.execute(run.run_id, 'prompt-intake-adapter', artifact)
        self.assertEqual(calls, ['value'])

    def test_dry_run_never_invokes_side_effecting_tool(self):
        calls = []
        self.tools.register('artifact', lambda: calls.append('effect'), 'L2', True)
        run = self.start(dry_run=True)
        def dry(context, call):
            result = call('artifact', idempotency_key='dry')
            self.assertFalse(result['invoked'])
            return ready()
        self.orch.execute(run.run_id, 'prompt-intake-adapter', dry)
        self.assertEqual(calls, [])

    def test_failed_effect_is_not_replayed(self):
        calls = []
        def uncertain():
            calls.append('effect')
            raise RuntimeError('Connection lost after write')
        self.tools.register('uncertain', uncertain, 'L2', True)
        run = self.start()
        def invoke(context, call):
            call('uncertain', idempotency_key='stable')
            return ready()
        with self.assertRaises(RuntimeError):
            self.orch.execute(run.run_id, 'prompt-intake-adapter', invoke)
        with self.assertRaisesRegex(ValueError, 'outcome unknown or failed'):
            self.orch.execute(run.run_id, 'prompt-intake-adapter', invoke)
        self.assertEqual(calls, ['effect'])

    def test_tool_budget_and_redaction(self):
        policy_path = self.kit / 'config/platform.json'
        policy = json.loads(policy_path.read_text()); policy['max_tool_calls_per_task'] = 1
        policy_path.write_text(json.dumps(policy))
        self.orch = Orchestrator(self.store, self.kit, self.tools)
        self.tools.register('read', lambda: {'token':'private', 'safe':'ok'})
        run = self.start()
        def handler(context, call):
            self.assertEqual(call('read')['token'], '[REDACTED]')
            with self.assertRaisesRegex(ValueError, 'Tool call budget'):
                call('read')
            return ready()
        self.orch.execute(run.run_id, 'prompt-intake-adapter', handler)

    def test_contract_rejects_false_readiness(self):
        for invalid in [{'status':'READY'}, {**ready(), 'evidence':[]}, {**ready(), 'blocking_issues':['missing behavior']}, {**ready(), 'status':'UNKNOWN'}]:
            with self.assertRaises(ValueError):
                validate_result(invalid)

    def test_planning_routes_and_unknown_work_type(self):
        self.assertNotIn('PLANNING', workflow_route('new_feature'))
        self.assertIn('PLANNING', workflow_route('new_feature', 'FULL_SPRINT_PLANNING'))
        self.assertNotIn('IMPLEMENTATION', workflow_route('bug', 'BACKLOG_ONLY'))
        self.assertNotIn('TECHNICAL', workflow_route('existing_task'))
        with self.assertRaises(ValueError):
            self.start('anything')

    def test_legacy_approval_does_not_authorize_governed_run(self):
        run = self.technical_ready()
        self.store.approval(run.run_id, 'technical', 'legacy-fixture', 'APPROVED', '', now())
        self.assertFalse(self.store.has_approval(run.run_id, 'technical'))

    def test_cli_returns_nonzero_for_blocked_transition(self):
        # Use actual kit configuration; the CLI accepts an isolated DB path.
        store = RuntimeStore(str(self.root / 'cli.sqlite3'))
        self.addCleanup(store.conn.close)
        run = Orchestrator(store, KIT).start('test','device_preview','CLI fixture')
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(cli_main(['--db', store.db_path, 'transition', run.run_id, 'RELEASE']), 1)

    def test_eval_runner_rejects_wrong_unknown_and_empty_cases(self):
        cases = self.root / 'cases'
        cases.mkdir()
        def evaluate():
            return subprocess.run([sys.executable, '-B', str(KIT / 'evals/run_evals.py'), '--cases', str(cases)], capture_output=True, text=True)
        self.assertEqual(evaluate().returncode, 1)
        path = cases / 'wrong.json'
        path.write_text(json.dumps({'name':'Deliberately wrong', 'kind':'policy', 'input':{'stage':'IMPLEMENTATION'}, 'expected':{'allowed':True}}))
        wrong = evaluate()
        self.assertEqual(wrong.returncode, 1)
        self.assertIn('got', wrong.stdout)
        path.write_text(json.dumps({'name':'Unknown', 'kind':'unknown', 'input':{}, 'expected':{}}))
        self.assertEqual(evaluate().returncode, 1)

    def test_runtime_demo_completes_without_effects(self):
        result = subprocess.run([sys.executable, '-B', str(KIT / 'examples/runtime-demo.py')], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output['status'], 'COMPLETED')
        self.assertEqual(output['external_effects'], 0)


if __name__ == '__main__':
    unittest.main()
