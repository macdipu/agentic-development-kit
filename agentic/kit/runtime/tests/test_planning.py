"""Hierarchy and sprint planning are decided by the classifier and produce files."""
from support import HarnessCase, ready

FEATURE = 'agentic/data/project-context/features/FEAT-7'


class PlanningTests(HarnessCase):
    def at_technical(self, planning=None):
        run = self.orch.start('fixture', 'new_feature', 'Planned feature', repo=self.root, planning=planning)
        self.run_id = run.run_id
        self.result('prompt-intake-adapter')
        self.orch.transition(self.run_id, 'CONTEXT')
        self.orch.record_context(self.run_id, ['scope.md'])
        self.result('baseline-verifier')
        self.orch.transition(self.run_id, 'REQUIREMENTS')
        self.result('business-requirement-analyzer')
        self.orch.transition(self.run_id, 'TECHNICAL')
        self.result('technical-readiness-verifier')

    def classify(self, classification, sprint_handling='NO_REPLAN', work_item_id='FEAT-7'):
        return super().classify(classification, sprint_handling, work_item_id)

    def write(self, relative, text='x\n'):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')

    def test_technical_exit_requires_the_classifier(self):
        self.at_technical()
        with self.assertRaisesRegex(ValueError, 'work-item-level-classifier'):
            self.orch.transition(self.run_id, 'IMPLEMENTATION')

    def test_incomplete_verdict_is_rejected_with_the_missing_fields(self):
        self.at_technical()
        self.orch.execute(self.run_id, 'work-item-level-classifier', lambda c, t: ready(classification='STORY_TASK'))
        with self.assertRaisesRegex(ValueError, 'sprint_handling.*work_item_id'):
            self.orch.transition(self.run_id, 'PLANNING')

    def test_task_only_without_sprint_skips_planning(self):
        self.at_technical()
        self.classify('TASK_ONLY')
        self.orch.approve(self.run_id, 'technical', 'reviewer')
        run = self.orch.transition(self.run_id, 'IMPLEMENTATION')
        self.assertNotIn('PLANNING', run.metadata['route'])
        self.assertEqual(run.metadata['hierarchy'], 'TASK_ONLY')

    def test_story_task_inserts_planning_and_requires_story_and_task_files(self):
        self.at_technical()
        self.classify('STORY_TASK')
        with self.assertRaisesRegex(ValueError, 'next stage is PLANNING'):
            self.orch.transition(self.run_id, 'IMPLEMENTATION')
        self.orch.transition(self.run_id, 'PLANNING')
        self.result('sprint-planner')
        self.orch.approve(self.run_id, 'technical', 'reviewer')
        with self.assertRaisesRegex(ValueError, 'stories/STORY-\\*.md.*tasks/TASK-\\*.md'):
            self.orch.transition(self.run_id, 'IMPLEMENTATION')
        self.write(f'{FEATURE}/stories/STORY-001.md')
        self.write(f'{FEATURE}/tasks/TASK-001.md')
        self.orch.transition(self.run_id, 'IMPLEMENTATION')

    def test_epic_needs_epic_file_and_full_sprint_needs_a_sprint_listing_the_item(self):
        self.at_technical()
        self.classify('EPIC_STORY_TASK', 'FULL_SPRINT_PLANNING')
        self.orch.transition(self.run_id, 'PLANNING')
        self.result('sprint-planner')
        self.orch.approve(self.run_id, 'technical', 'reviewer')
        self.write(f'{FEATURE}/stories/STORY-001.md')
        self.write(f'{FEATURE}/tasks/TASK-001.md')
        with self.assertRaisesRegex(ValueError, 'EPIC.md.*SPRINT-\\*.md listing FEAT-7'):
            self.orch.transition(self.run_id, 'IMPLEMENTATION')
        self.write(f'{FEATURE}/EPIC.md')
        self.write('agentic/data/project-context/sprints/SPRINT-012.md', 'Committed: OTHER-1\n')
        with self.assertRaisesRegex(ValueError, 'SPRINT'):
            self.orch.transition(self.run_id, 'IMPLEMENTATION')
        self.write('agentic/data/project-context/sprints/SPRINT-012.md', 'Committed: OTHER-1, FEAT-7\n')
        self.orch.transition(self.run_id, 'IMPLEMENTATION')

    def test_backlog_only_ends_after_planning(self):
        self.at_technical()
        self.classify('TASK_ONLY', 'BACKLOG_ONLY')
        run = self.orch.transition(self.run_id, 'PLANNING')
        self.assertEqual(run.metadata['route'][-2:], ['PLANNING', 'COMPLETED'])

    def test_start_planning_overrides_sprint_handling_only(self):
        self.at_technical(planning='FULL_SPRINT_PLANNING')
        self.classify('TASK_ONLY', 'NO_REPLAN')
        run = self.orch.transition(self.run_id, 'PLANNING')
        self.assertEqual(run.metadata['planning'], 'FULL_SPRINT_PLANNING')
        self.assertEqual(run.metadata['hierarchy'], 'TASK_ONLY')

    def test_reopen_clears_the_decision(self):
        self.at_technical()
        self.classify('TASK_ONLY')
        self.orch.approve(self.run_id, 'technical', 'reviewer')
        self.orch.transition(self.run_id, 'IMPLEMENTATION')
        run = self.orch.reopen(self.run_id, 'scope changed')
        self.assertNotIn('hierarchy', run.metadata)
