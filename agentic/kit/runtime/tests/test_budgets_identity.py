import subprocess
from datetime import datetime, timedelta, timezone

from support import HarnessCase, ready
from agentic_runtime import identity


class SkillBudgetTests(HarnessCase):
    def age_active_task(self, seconds):
        run = self.store.get_run(self.run_id)
        run.metadata['active_task']['started_at'] = (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat()
        self.store.save_run(run)

    def test_skill_budget_extends_deadline_for_long_skills_only(self):
        self.implementation()
        task, _ = self.orch.start_task(self.run_id, 'implementation-agent')
        self.age_active_task(1800)  # past the 900s global default, inside implementation's 7200s
        self.orch.call_tool(self.run_id, task['id'], 'read_file', {'path': 'scope.md'})
        self.age_active_task(7300)
        with self.assertRaises(TimeoutError):
            self.orch.call_tool(self.run_id, task['id'], 'read_file', {'path': 'scope.md'})

    def test_global_default_still_applies_to_other_skills(self):
        self.start()
        task, _ = self.orch.start_task(self.run_id, 'prompt-intake-adapter')
        self.age_active_task(1000)
        with self.assertRaises(TimeoutError):
            self.orch.finish_task(self.run_id, task['id'], ready())

    def test_run_override_beats_skill_budget(self):
        self.start()
        run = self.store.get_run(self.run_id)
        self.assertEqual(self.orch._budget(run, 'max_agent_retries', 'implementation-agent'), 4)
        self.orch.adjust_budget(self.run_id, 'operator', 'explicit', max_agent_retries=1)
        run = self.store.get_run(self.run_id)
        self.assertEqual(self.orch._budget(run, 'max_agent_retries', 'implementation-agent'), 1)

    def test_invalid_skill_budget_rejected(self):
        import json
        path = self.kit / 'config/platform.json'
        data = json.loads(path.read_text(encoding='utf-8'))
        data['skill_budgets'] = {'implementation-agent': {'max_task_seconds': 0}}
        path.write_text(json.dumps(data), encoding='utf-8')
        from agentic_runtime.orchestrator import Orchestrator
        with self.assertRaisesRegex(ValueError, 'Invalid skill budget'):
            Orchestrator(self.store, self.kit, self.tools)


class PostHocTests(HarnessCase):
    def spans(self):
        return {s['task']: s for s in self.orch.task_timings(self.run_id)}

    def test_instant_toolless_task_is_flagged_post_hoc(self):
        self.start()
        self.result('prompt-intake-adapter')
        (span,) = self.spans().values()
        self.assertTrue(span['post_hoc'])
        events = [e for e in self.store.ledger(self.run_id)['audit_events'] if e['event'] == 'RESULT_RECORDED']
        self.assertTrue(events[-1]['payload']['post_hoc'])

    def test_task_with_governed_tool_calls_is_not_post_hoc(self):
        self.start()
        self.orch.execute(self.run_id, 'prompt-intake-adapter',
                          lambda c, call: (call('read_file', {'path': 'scope.md'}), ready())[1])
        (span,) = self.spans().values()
        self.assertFalse(span['post_hoc'])


class IdentityTests(HarnessCase):
    def setUp(self):
        super().setUp()
        for args in (['init', '-q'], ['config', 'user.name', 'Dana Ops'], ['config', 'user.email', 'dana@example.com']):
            subprocess.run(['git', *args], cwd=self.root, check=True, capture_output=True)

    def test_own_spellings_normalize_to_git_identity(self):
        for spelling in (None, '', 'Dana Ops', 'dana@example.com', 'DANA OPS', 'user', 'me', 'Dana Ops <dana@example.com>'):
            with self.subTest(spelling=spelling):
                self.assertEqual(identity.approver(self.root, spelling), 'Dana Ops <dana@example.com>')

    def test_other_reviewer_kept_verbatim(self):
        self.assertEqual(identity.approver(self.root, 'Lee Reviewer'), 'Lee Reviewer')
