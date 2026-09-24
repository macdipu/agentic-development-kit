import json
import subprocess
import sys
from pathlib import Path

from support import HarnessCase
from agentic_runtime import commits, handoff


class CommitTests(HarnessCase):
    def git(self, *args):
        return subprocess.run(['git', *args], cwd=self.root, check=True, capture_output=True, text=True).stdout

    def init_repo(self):
        self.git('init', '-q')
        self.git('config', 'user.name', 'Fixture Operator')
        self.git('config', 'user.email', 'fixture@example.com')

    def commit(self, name, message):
        (self.root / name).write_text(name)
        self.git('add', name)
        subprocess.run(['git', 'commit', '-q', '-F', '-'], cwd=self.root, input=message, check=True, text=True)

    def cli(self, *args):
        return subprocess.run([sys.executable, str(self.kit / 'runtime/python/agentic_runtime/cli.py'),
                               '--store-dir', str(self.store.store_dir), *args],
                              cwd=self.root, capture_output=True, text=True)

    def test_render_message_orders_trailers_after_body(self):
        message = commits.render_message(type='feat', scope='auth', subject='add refresh', body='Why.',
                                         trigger='task-finish', work_item='FEAT-1', task='T-1', run='r1')
        self.assertEqual(message, 'feat(auth): add refresh\n\nWhy.\n\n'
                                  'Work-Item: FEAT-1\nTask: T-1\nRun: r1\nCommit-Trigger: task-finish\n')

    def test_render_message_rejects_policy_violations(self):
        base = dict(type='fix', subject='ok', trigger='user-request')
        for bad in ({'type': 'feature'}, {'trigger': 'auto'}, {'subject': 'ends.'},
                    {'subject': 'x' * 80}, {'scope': 'Auth'}, {'subject': ' '}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                commits.render_message(**{**base, **bad})

    def test_session_logs_commits_since_previous_session_with_triggers(self):
        self.init_repo()
        self.commit('a.txt', 'chore: seed\n')
        handoff.close_session(self.root, agent='claude', task='t', completed='c', status='RUNNING')
        self.commit('b.txt', commits.render_message(type='feat', subject='add b', trigger='task-finish',
                                                   work_item='FEAT-2', task='T-4'))
        self.commit('c.txt', commits.render_message(type='fix', subject='fix c', trigger='user-request'))
        result = handoff.close_session(self.root, agent='codex', task='t', completed='c', status='COMPLETED')
        session = Path(result['session']).read_text()
        section = session.split('## Commits\n', 1)[1].split('\n\n', 1)[0]
        lines = section.splitlines()
        self.assertEqual(len(lines), 2)
        self.assertIn('fix: fix c [user-request]', lines[0])
        self.assertIn('feat: add b [task-finish | FEAT-2 | T-4]', lines[1])
        self.assertNotIn('seed', section)
        self.assertIn('## Commits', Path(result['handoff']).read_text())

    def test_session_embeds_runtime_summary_of_run(self):
        self.init_repo()
        self.commit('a.txt', 'chore: seed\n')
        self.context('existing_task')
        self.orch.approve(self.run_id, 'technical', 'fixture reviewer', comment='looks good')
        result = handoff.close_session(self.root, agent='claude', task='t', completed='c', status='RUNNING',
                                       store=self.store, run_id=self.run_id)
        for path in (result['session'], result['handoff']):
            runtime = Path(path).read_text().split('## Runtime\n', 1)[1].split('\n## Commits', 1)[0]
            self.assertIn(f'- Run: {self.run_id}', runtime)
            self.assertIn('- CONTEXT: READY', runtime)
            self.assertIn('  - evidence: scope.md', runtime)
            self.assertIn('technical: APPROVED by fixture reviewer (rev 0) -- looks good', runtime)
            self.assertIn('baseline-verifier: COMPLETED', runtime)
            self.assertIn('- 0:CONTEXT:baseline-verifier: 1', runtime)
            self.assertIn('- scope.md: ', runtime)
            self.assertIn('RUN_STARTED', runtime)
            self.assertIn('CONTEXT_REFRESHED {"paths":["scope.md"]}', runtime)

    def test_pickup_summary_drops_ledger_and_duplicate_session(self):
        self.init_repo()
        self.commit('a.txt', 'chore: seed\n')
        self.context('existing_task')
        handoff.close_session(self.root, agent='claude', task='t', completed='c', status='RUNNING',
                              next_action='do next', store=self.store, run_id=self.run_id)
        summary = handoff.pickup_summary(self.root, active_run_id=self.run_id)
        self.assertIn(f'Runtime: Run: {self.run_id} | Stage: CONTEXT', summary)
        self.assertIn('## Next Action\ndo next', summary)
        for dropped in ('### Audit', '### Checkpoints', 'RUN_STARTED', '## Git Snapshot', 'LATEST SESSION', 'STALE'):
            self.assertNotIn(dropped, summary)
        self.assertLess(len(summary), handoff.PICKUP_LIMIT + 200)

    def test_pickup_summary_flags_note_about_another_run(self):
        self.init_repo()
        self.commit('a.txt', 'chore: seed\n')
        self.start()
        handoff.close_session(self.root, agent='codex', task='old', completed='c', status='CANCELLED',
                              store=self.store, run_id=self.run_id)
        summary = handoff.pickup_summary(self.root, active_run_id='RUN-NEWER')
        self.assertTrue(summary.startswith(f'STALE HANDOFF: this note describes run {self.run_id}'))

    def test_pickup_summary_keeps_session_that_differs_from_handoff(self):
        self.init_repo()
        self.commit('a.txt', 'chore: seed\n')
        handoff.close_session(self.root, agent='claude', task='t', completed='c', status='RUNNING')
        handoff.write_session(self.root, agent='codex', operator='o', git_snapshot_text='Branch: main',
                              task='other', completed='x', changed_files=[], tests='', blockers='',
                              decisions='', next_action='n')
        self.assertIn('LATEST SESSION', handoff.pickup_summary(self.root))

    def test_condense_note_ignores_headings_and_run_lines_in_free_text(self):
        note = handoff.render_handoff(
            last_agent='claude', operator='o', status='RUNNING', task='t\n- Run: FAKE',
            completed='a\n## Sub heading\nkept', changed_files=[], tests='', blockers='', decisions='',
            next_action='n', git_snapshot_text='## main', runtime='- Run: RUN-1\n- Stage: X')
        self.assertEqual(handoff.note_run_id(note), 'RUN-1')
        self.assertIn('## Sub heading\nkept', handoff.condense_note(note))

    def test_pickup_cli_is_condensed_unless_full(self):
        self.init_repo()
        self.commit('a.txt', 'chore: seed\n')
        handoff.close_session(self.root, agent='claude', task='t', completed='c', status='RUNNING')
        short = self.cli('pickup', '--repo', str(self.root))
        full = self.cli('pickup', '--repo', str(self.root), '--full')
        self.assertEqual(short.returncode, 0, short.stderr)
        self.assertNotIn('## Git Snapshot', short.stdout)
        self.assertIn('## Git Snapshot', full.stdout)

    def test_same_session_id_rewrites_one_record(self):
        self.init_repo()
        self.commit('a.txt', 'chore: seed\n')
        first = handoff.close_session(self.root, agent='claude', task='t', completed='c', status='RUNNING', session_id='s1')
        self.commit('b.txt', commits.render_message(type='feat', subject='add b', trigger='user-request'))
        again = handoff.close_session(self.root, agent='claude', task='t', completed='c2', status='RUNNING', session_id='s1')
        self.assertEqual(first['session'], again['session'])
        self.assertIn('feat: add b', Path(again['session']).read_text())
        other = handoff.close_session(self.root, agent='claude', task='t', completed='c', status='RUNNING', session_id='s2')
        self.assertNotEqual(other['session'], first['session'])
        self.assertEqual(len(list((self.root / '.agent/sessions').glob('*.md'))), 2)
        self.assertIn('## Commits\n(none)', Path(other['session']).read_text())

    def test_session_without_run_says_so(self):
        self.init_repo()
        self.commit('a.txt', 'chore: seed\n')
        result = handoff.close_session(self.root, agent='claude', task='t', completed='c', status='RUNNING')
        self.assertIn('## Runtime\n(no governed run)', Path(result['session']).read_text())

    def test_untrailered_commit_is_flagged(self):
        self.init_repo()
        self.commit('a.txt', 'wip\n')
        lines = commits.format_commit_lines(commits.commits_since(self.root, None))
        self.assertEqual(lines[0].split(' ', 1)[1], 'wip [no Commit-Trigger]')

    def test_record_commit_audits_trailers_and_refuses_untrailered(self):
        self.init_repo()
        self.start()
        self.commit('a.txt', 'wip\n')
        refused = self.cli('record-commit', self.run_id)
        self.assertEqual(refused.returncode, 1)
        self.assertIn('Commit-Trigger', refused.stderr)
        self.commit('b.txt', commits.render_message(type='feat', subject='add b', trigger='task-finish',
                                                   run=self.run_id))
        recorded = self.cli('record-commit', self.run_id)
        self.assertEqual(recorded.returncode, 0, recorded.stderr)
        self.assertEqual(json.loads(recorded.stdout)['commit_trigger'], 'task-finish')
        events = [e for e in self.store._view(self.run_id)['audit_events'] if e['event'] == 'COMMIT_RECORDED']
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]['payload']['run'], self.run_id)

    def test_commit_message_cli_prints_message(self):
        result = self.cli('commit-message', '--type', 'docs', '--subject', 'add policy', '--trigger', 'user-request')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, 'docs: add policy\n\nCommit-Trigger: user-request\n')
