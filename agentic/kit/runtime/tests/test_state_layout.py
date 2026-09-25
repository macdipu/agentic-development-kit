"""Append-only state: two machines' changes merge through plain git without conflicts."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from support import KIT, HarnessCase, ready
from agentic_runtime.claims import ClaimHeld, Claims
from agentic_runtime.store import RuntimeStore


def git(cwd, *args, check=True):
    result = subprocess.run(['git', *args], cwd=cwd, capture_output=True, text=True, encoding='utf-8', errors='replace')
    if check and result.returncode:
        raise AssertionError(f'git {args}: {result.stderr}')
    return result.stdout


class EventStoreTests(HarnessCase):
    def event_files(self):
        return sorted((self.store.store_dir / self.run_id / 'events').glob('*.json'))

    def test_changes_only_add_files(self):
        self.context()
        before = {p.name: p.read_bytes() for p in self.event_files()}
        self.result('baseline-verifier')
        after = {p.name: p.read_bytes() for p in self.event_files()}
        self.assertTrue(set(before) < set(after))
        self.assertTrue(all(after[name] == data for name, data in before.items()))

    def test_one_transaction_is_one_event(self):
        self.start()
        count = len(self.event_files())
        task, _ = self.orch.start_task(self.run_id, 'prompt-intake-adapter')
        self.assertEqual(len(self.event_files()), count + 1)

    def test_divergent_copies_merge_by_union_of_files(self):
        self.start()
        other_dir = self.root / 'other-machine-runs'
        shutil.copytree(self.store.store_dir, other_dir, ignore=shutil.ignore_patterns('.cache.json', '.lock'))
        other = RuntimeStore(str(other_dir))
        self.store.audit(self.run_id, 'ON_A', {}, '2026-01-01T00:00:00+00:00')
        other.audit(self.run_id, 'ON_B', {}, '2026-01-01T00:00:01+00:00')
        for path in (other_dir / self.run_id / 'events').glob('*.json'):  # "git pull": union of files
            target = self.store.store_dir / self.run_id / 'events' / path.name
            self.assertFalse(target.exists() and target.read_bytes() != path.read_bytes())
            shutil.copy2(path, target)
        events = [e['event'] for e in self.store.ledger(self.run_id)['audit_events']]
        self.assertIn('ON_A', events)
        self.assertIn('ON_B', events)

    def test_event_names_never_go_backwards(self):
        self.start()
        names = [p.name for p in self.event_files()]
        future = '29990101T000000000000Z-ffffffff.json'
        shutil.copy2(self.event_files()[0], self.store.store_dir / self.run_id / 'events' / future)
        (self.store.store_dir / self.run_id / 'events' / future).write_text('{"ops":[]}\n', encoding='utf-8')
        self.store.audit(self.run_id, 'AFTER_SKEW', {}, 'x')
        newest = sorted(p.name for p in self.event_files())[-1]
        self.assertGreater(newest, future)
        self.assertNotIn(newest, names)

    def test_cache_is_used_and_invalidated(self):
        self.context()
        first = self.store.ledger(self.run_id)
        cache = self.store.store_dir / self.run_id / '.cache.json'
        self.assertTrue(cache.exists())
        self.store.audit(self.run_id, 'NEW', {}, 'x')
        self.assertEqual(len(self.store.ledger(self.run_id)['audit_events']), len(first['audit_events']) + 1)
        cache.write_text('{broken', encoding='utf-8')
        self.assertEqual(len(self.store.ledger(self.run_id)['audit_events']), len(first['audit_events']) + 1)

    def test_compaction_replaces_history_with_one_snapshot(self):
        self.context()
        self.orch.cancel(self.run_id)
        files = self.event_files()
        self.assertEqual(len(files), 1)
        self.assertEqual(json.loads(files[0].read_text(encoding='utf-8'))['ops'][0]['op'], 'snapshot')
        self.assertEqual(self.store.get_run(self.run_id).status, 'CANCELLED')


class ClaimTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='agentic-claims-')
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.claims_dir = root / 'claims'
        self.a = Claims(self.claims_dir, root / 'local-a', root)
        self.b = Claims(self.claims_dir, root / 'local-b', root)

    def test_holder_blocks_other_clone_until_release(self):
        self.a.claim('RUN-1', agent='claude')
        self.assertTrue(self.a.current('RUN-1')['mine'])
        with self.assertRaises(ClaimHeld):
            self.b.claim('RUN-1')
        self.assertIsNone(self.b.release('RUN-1'))  # cannot release someone else's claim
        self.a.release('RUN-1')
        self.assertIsNone(self.a.current('RUN-1'))
        self.assertTrue(self.b.claim('RUN-1')['action'] == 'claim')

    def test_takeover_needs_reason_and_records_previous_holder(self):
        self.a.claim('RUN-1')
        with self.assertRaisesRegex(ValueError, 'requires --reason'):
            self.b.claim('RUN-1', takeover=True)
        event = self.b.claim('RUN-1', takeover=True, reason='A is offline')
        self.assertEqual(event['action'], 'takeover')
        self.assertEqual(event['previous']['clone_id'], self.a.clone_id())
        self.assertIsNone(self.a.release('RUN-1'))
        self.assertTrue(self.b.current('RUN-1')['mine'])

    def test_expired_claim_is_not_binding_but_takeover_is_recorded(self):
        Claims(self.claims_dir, self.a.local_dir, self.a.repo, ttl_seconds=-1).claim('RUN-1')
        self.assertIsNone(self.b.holder_other('RUN-1'))
        taken = self.b.claim('RUN-1')  # expiry is the recorded reason
        self.assertTrue(taken['previous_expired'])
        self.assertIn('expired', taken['reason'])

    def test_refresh_does_not_write_a_file_each_time(self):
        self.a.claim('RUN-1')
        self.a.claim('RUN-1')
        self.assertEqual(len(list((self.claims_dir / 'RUN-1').glob('*.json'))), 1)


class TwoMachineGitTests(unittest.TestCase):
    """Machine A and B share a bare remote; state moves only by commit/push/pull."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='agentic-2m-')
        self.addCleanup(self.temporary.cleanup)
        base = Path(self.temporary.name)
        remote = base / 'remote.git'
        git(base, 'init', '-q', '--bare', str(remote))
        seed = base / 'seed'
        git(base, 'init', '-q', str(seed))
        for name in ('config', 'skills', 'runtime'):
            shutil.copytree(KIT / name, seed / 'agentic/kit' / name, ignore=shutil.ignore_patterns('__pycache__', 'tests'))
        from agentic_runtime.migration import IGNORE_LINES
        (seed / '.gitignore').write_text('\n'.join(IGNORE_LINES + ['__pycache__/']) + '\n', encoding='utf-8')
        (seed / 'app.py').write_text('print(1)\n', encoding='utf-8')
        for args in (['config', 'user.name', 'Seed'], ['config', 'user.email', 'seed@example.com'], ['add', '.'],
                     ['commit', '-q', '-m', 'seed'], ['branch', '-M', 'main'], ['remote', 'add', 'origin', str(remote)],
                     ['push', '-q', '-u', 'origin', 'main']):
            git(seed, *args)
        self.a, self.b = base / 'a', base / 'b'
        for clone, name in ((self.a, 'Ann'), (self.b, 'Bob')):
            git(base, 'clone', '-q', str(remote), str(clone))
            git(clone, 'config', 'user.name', name)
            git(clone, 'config', 'user.email', name.lower() + '@example.com')
            git(clone, 'config', 'pull.rebase', 'false')
        self.envelope = base / 'ready.json'
        self.envelope.write_text(json.dumps(ready('app.py')), encoding='utf-8')

    def cli(self, clone, *args, ok=True):
        result = subprocess.run([sys.executable, str(clone / 'agentic/kit/runtime/python/agentic_runtime/cli.py'), *args],
                                cwd=clone, capture_output=True, text=True, encoding='utf-8', errors='replace',
                                env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1', AGENTIC_AGENT='claude'), timeout=120)
        if ok:
            self.assertEqual(result.returncode, 0, result.stderr)
            return json.loads(result.stdout) if result.stdout.strip().startswith(('{', '[')) else result.stdout
        return result

    def test_handoff_mid_task_and_resume_on_other_machine(self):
        run_id = self.cli(self.a, 'start', '--project', 'p', '--type', 'discovery', '--title', 'Shared')['run_id']
        task_id = self.cli(self.a, 'task-start', run_id, '--skill', 'prompt-intake-adapter')['task_id']
        (self.a / 'app.py').write_text('print(2)\n', encoding='utf-8')  # work in progress
        handed = self.cli(self.a, 'handoff')
        self.assertTrue(handed['pushed'])
        self.assertFalse((self.a / '.agent/local/active-task.json').exists())  # A stops working the task
        self.assertIn('app.py', handed['files'])
        self.assertIn('Commit-Trigger: handoff', git(self.a, 'log', '-1', '--format=%B'))

        resumed = self.cli(self.b, 'resume', run_id)
        self.assertTrue(resumed['pull']['pulled'])
        self.assertEqual(resumed['adopted_task']['id'], task_id)
        self.assertEqual((self.b / 'app.py').read_text(encoding='utf-8'), 'print(2)\n')
        self.assertIn(run_id, (self.b / '.agent/HANDOFF.md').read_text(encoding='utf-8'))

        # A still thinks it has the task; once B's claim reaches A, A is refused.
        self.cli(self.b, 'task-finish', run_id, task_id, '--file', str(self.envelope))
        self.assertIn('Commit-Trigger: agent-state', git(self.b, 'log', '-1', '--format=%B'))
        self.assertEqual(git(self.b, 'status', '--porcelain', '--', '.agent/state'), '')
        git(self.b, 'push', '-q')
        git(self.a, 'pull', '-q')
        self.assertEqual(self.cli(self.a, 'show', run_id)['stage_results']['INTAKE'], 'READY')
        self.assertIn('finished at INTAKE', (self.a / '.agent/HANDOFF.md').read_text(encoding='utf-8'))

    def test_claim_travels_and_blocks_the_other_machine(self):
        run_id = self.cli(self.a, 'start', '--project', 'p', '--type', 'discovery', '--title', 'Held')['run_id']
        self.cli(self.a, 'task-start', run_id, '--skill', 'prompt-intake-adapter')
        self.assertIn('Commit-Trigger: agent-state', git(self.a, 'log', '-1', '--format=%B'))  # claim committed
        git(self.a, 'push', '-q')
        git(self.b, 'pull', '-q')
        refused = self.cli(self.b, 'task-start', run_id, '--skill', 'prompt-intake-adapter', ok=False)
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn('claimed by', refused.stderr)
        refused = self.cli(self.b, 'approve', run_id, '--gate', 'technical', ok=False)
        self.assertIn('claimed by', refused.stderr)

    def test_concurrent_state_on_both_machines_merges_cleanly(self):
        run_a = self.cli(self.a, 'start', '--project', 'p', '--type', 'discovery', '--title', 'On A')['run_id']
        git(self.a, 'add', '-A', '.agent')
        git(self.a, 'commit', '-q', '-m', 'a')
        git(self.a, 'push', '-q')
        git(self.b, 'pull', '-q')
        # Both machines change the same run's ledger and add their own run, then both push.
        self.cli(self.a, 'context', run_a, 'app.py', ok=False)  # rejected (INTAKE), still harmless
        self.cli(self.a, 'result', run_a, '--skill', 'prompt-intake-adapter', '--file', str(self.envelope))
        self.cli(self.b, 'start', '--project', 'p', '--type', 'discovery', '--title', 'On B')
        self.cli(self.b, 'close-session', '--agent', 'codex', '--status', 'RUNNING', '--task', 't', '--completed', 'c')
        for clone in (self.a, self.b):
            git(clone, 'add', '-A', '.agent')
            git(clone, 'commit', '-q', '-m', 'state', check=False)
        git(self.a, 'push', '-q')
        merged = subprocess.run(['git', 'pull', '-q', '--no-edit'], cwd=self.b, capture_output=True, text=True)
        self.assertEqual(merged.returncode, 0, merged.stdout + merged.stderr)  # no conflicts
        titles = {r['title'] for r in self.cli(self.b, 'list')}
        self.assertEqual(titles, {'On A', 'On B'})
        self.assertEqual(self.cli(self.b, 'show', run_a)['stage_results']['INTAKE'], 'READY')


class MigrationTests(HarnessCase):
    def test_previous_layout_converts_to_event_store(self):
        legacy = self.root / '.agent/runtime/runs'
        legacy.mkdir(parents=True)
        self.start()
        self.result('prompt-intake-adapter')
        state = self.store._load(self.run_id)
        (legacy / f'{self.run_id}.json').write_text(json.dumps(state), encoding='utf-8')
        (self.root / '.agent/runtime/route-cache.json').write_text('{}', encoding='utf-8')
        (self.root / '.agent/HANDOFF.md').write_text('Last updated: x\nold\n', encoding='utf-8')
        shutil.rmtree(self.store.store_dir)
        from agentic_runtime.migration import migrate
        store = RuntimeStore(str(self.root / '.agent/state/runs'))
        report = migrate(self.root, store)
        self.assertEqual(report['runs'], [self.run_id])
        self.assertEqual(store.get_run(self.run_id).metadata['results']['INTAKE']['status'], 'READY')
        self.assertEqual(store.get_run(self.run_id).metadata['repo'], str(self.root.resolve()))
        self.assertFalse((self.root / '.agent/runtime').exists())
        self.assertTrue((self.root / '.agent/local/route-cache.json').exists())
        self.assertTrue(any((self.root / '.agent/state/handoffs').glob('*.md')))
        self.assertIn('/.agent/local/', (self.root / '.gitignore').read_text(encoding='utf-8'))


class ReviewRegressionTests(HarnessCase):
    def test_compaction_keeps_older_event_merged_from_another_clone(self):
        self.start()
        other_dir = self.root / 'other-runs'
        import shutil as _shutil
        _shutil.copytree(self.store.store_dir, other_dir, ignore=_shutil.ignore_patterns('.cache.json', '.lock'))
        RuntimeStore(str(other_dir)).audit(self.run_id, 'FROM_B', {}, 'x')   # older stamp than what follows
        self.orch.cancel(self.run_id)                                         # compacts here
        for path in (other_dir / self.run_id / 'events').glob('*.json'):      # git pull brings B's file
            target = self.store.store_dir / self.run_id / 'events' / path.name
            if not target.exists() and 'FROM_B' in path.read_text(encoding='utf-8'):
                _shutil.copy2(path, target)
        events = [e['event'] for e in self.store.ledger(self.run_id)['audit_events']]
        self.assertIn('FROM_B', events)
        self.assertEqual(self.store.get_run(self.run_id).status, 'CANCELLED')

    def test_nested_edit_inside_transaction_is_persisted(self):
        self.start()
        task, _ = self.orch.start_task(self.run_id, 'prompt-intake-adapter')
        with self.store.transaction():
            self.store.audit(self.run_id, 'X', {}, 'x')
            run = self.store.get_run(self.run_id)
            run.metadata['active_task']['tool_calls'] += 1
            self.store.save_run(run)
        self.assertEqual(self.store.get_run(self.run_id).metadata['active_task']['tool_calls'], 1)

    def test_adopted_task_gets_a_fresh_time_budget(self):
        from datetime import datetime, timedelta, timezone
        self.start()
        task, _ = self.orch.start_task(self.run_id, 'prompt-intake-adapter')
        run = self.store.get_run(self.run_id)
        run.metadata['active_task']['started_at'] = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()
        self.store.save_run(run)
        self.orch.adopt_task(self.run_id, {'machine': 'b'})
        self.orch.finish_task(self.run_id, task['id'], ready())
        events = [e['event'] for e in self.store.ledger(self.run_id)['audit_events']]
        self.assertIn('TASK_ADOPTED', events)

    def cli(self, *args, ok=True):
        result = subprocess.run([sys.executable, str(self.kit / 'runtime/python/agentic_runtime/cli.py'),
                                 '--store-dir', str(self.store.store_dir), *args], cwd=self.root,
                                capture_output=True, text=True, encoding='utf-8', errors='replace',
                                env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))
        if ok:
            self.assertEqual(result.returncode, 0, result.stderr)
            return json.loads(result.stdout)
        return result

    def test_full_flag_works_after_the_subcommand(self):
        self.start()
        self.assertIn('metadata', self.cli('show', self.run_id, '--full'))
        self.assertIn('metadata', self.cli('--full', 'show', self.run_id))
        self.assertNotIn('metadata', self.cli('show', self.run_id))

    def test_claim_is_kept_across_tasks_until_the_run_ends(self):
        run_id = self.cli('start', '--project', 'p', '--type', 'discovery', '--title', 't')['run_id']
        envelope = self.root / 'ready.json'
        envelope.write_text(json.dumps(ready()), encoding='utf-8')
        task = self.cli('task-start', run_id, '--skill', 'prompt-intake-adapter')['task_id']
        self.cli('task-finish', run_id, task, '--file', str(envelope))
        claims = Claims(self.root / '.agent/state/claims', self.root / '.agent/local', self.root)
        self.assertTrue(claims.current(run_id)['mine'])       # still held between tasks
        self.cli('cancel', run_id)
        self.assertIsNone(claims.current(run_id))             # released when the run ends

    def test_expired_foreign_claim_is_taken_over_at_task_start(self):
        run_id = self.cli('start', '--project', 'p', '--type', 'discovery', '--title', 't')['run_id']
        other = Claims(self.root / '.agent/state/claims', self.root / 'other-local', self.root, ttl_seconds=-1)
        other.claim(run_id)
        self.cli('task-start', run_id, '--skill', 'prompt-intake-adapter')
        claims = Claims(self.root / '.agent/state/claims', self.root / '.agent/local', self.root)
        current = claims.current(run_id)
        self.assertEqual(current['action'], 'takeover')
        self.assertIn('expired', current['reason'])

    def test_failed_reserve_does_not_leak_a_claim(self):
        run_id = self.cli('start', '--project', 'p', '--type', 'discovery', '--title', 't')['run_id']
        (self.root / '.agent/local/active-task.json').write_text('{"store_dir": "x", "run_id": "other"}', encoding='utf-8')
        self.assertNotEqual(self.cli('task-start', run_id, '--skill', 'prompt-intake-adapter', ok=False).returncode, 0)
        claims = Claims(self.root / '.agent/state/claims', self.root / '.agent/local', self.root)
        self.assertIsNone(claims.current(run_id))
