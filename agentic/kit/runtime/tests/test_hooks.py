import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

from support import HarnessCase
from agentic_runtime import markers
from agentic_runtime.doctor import probe_hooks


class HookTests(HarnessCase):
    def hook(self, name, payload=None):
        result = subprocess.run([sys.executable, str(self.kit / 'runtime/hooks' / name)],
                                input=json.dumps(payload or {}), text=True, capture_output=True,
                                env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'), timeout=15, encoding='utf-8', errors='replace')
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_installed_hook_probe(self):
        probe_hooks(self.kit)

    def test_corrupt_marker_denies_tools_and_reports_unknown_session(self):
        marker = self.root / '.agent/local/active-task.json'
        marker.write_text('{invalid', encoding='utf-8', newline='\n')
        verdict = self.hook('pretooluse_gate.py', {'tool_name': 'Write'})
        self.assertEqual(verdict['hookSpecificOutput']['permissionDecision'], 'deny')
        self.assertIn('UNKNOWN', self.hook('session_start_check.py')['hookSpecificOutput']['additionalContext'])

    def test_session_start_condenses_handoff_and_flags_other_run(self):
        from agentic_runtime import handoff
        self.start()
        old_run = self.run_id
        handoff.close_session(self.root, agent='claude', task='old', completed='c', status='CANCELLED',
                              store=self.store, run_id=old_run)
        self.orch.cancel(old_run)
        self.start()
        context = self.hook('session_start_check.py')['hookSpecificOutput']['additionalContext']
        self.assertIn('MIDFLIGHT RUN', context)
        self.assertIn(f'STALE HANDOFF: this note describes run {old_run}, but the midflight run is {self.run_id}', context)
        self.assertNotIn('### Audit', context)
        self.assertNotIn('LATEST SESSION', context)

    def test_committed_runtime_resumes_from_another_checkout_path(self):
        self.start()
        task, _ = self.orch.start_task(self.run_id, 'prompt-intake-adapter')
        marker = self.root / '.agent/local/active-task.json'
        markers.activate(marker, self.store.store_dir, self.run_id, task['id'])
        self.assertEqual(json.loads(marker.read_text(encoding='utf-8'))['store_dir'], '../state/runs')
        first = sorted((self.store.store_dir / self.run_id / 'events').glob('*.json'))[0]
        run_op = json.loads(first.read_text(encoding='utf-8'))['ops'][0]
        self.assertEqual(run_op['meta']['repo'], '../../..')

        other = self.root.parent / (self.root.name + '-other-machine')
        shutil.copytree(self.root, other)
        self.addCleanup(shutil.rmtree, other, True)
        from agentic_runtime.hooks_support import load_active_task
        pointer, store, run = load_active_task(other / '.agent/local/active-task.json')
        self.assertEqual(pointer['task_id'], task['id'])
        self.assertEqual(Path(run.metadata['repo']), other.resolve())
        self.assertEqual(run.metadata['active_task']['id'], task['id'])

    def test_native_writes_into_runtime_ledger_are_denied(self):
        from agentic_runtime.tools import validate_write
        for path in ('.agent/state/runs/R/events/forged.json', '.agent/state/claims/R/x.json',
                     '.agent/local/active-task.json'):
            with self.subTest(path=path), self.assertRaisesRegex(PermissionError, 'runtime ledger'):
                validate_write(self.root, path)
        validate_write(self.root, '.agent/HANDOFF.md')

    def test_checkpoints_store_only_changed_metadata(self):
        self.context()
        checkpoints = self.store.ledger(self.run_id)['checkpoints']
        self.assertIn('skill_pins', checkpoints[0]['payload'])
        self.assertTrue(all('skill_pins' not in c['payload'] for c in checkpoints[1:]))
        self.assertTrue(any('results' in c['payload'] for c in checkpoints[1:]))
        state = {}
        for checkpoint in checkpoints:
            delta = checkpoint['payload']
            state = {k: v for k, v in {**state, **delta}.items() if k not in delta.get('_removed', []) and k != '_removed'}
        self.assertIn('active_task', state)
        self.assertEqual(state, self.store.ledger(self.run_id)['run']['metadata'] | {'repo': state['repo']})

    def test_marker_cannot_be_overwritten_or_cleared_by_another_run(self):
        marker = self.root / '.agent/local/active-task.json'
        markers.reserve(marker, self.store.store_dir, 'first')
        with self.assertRaises(FileExistsError):
            markers.reserve(marker, self.store.store_dir, 'second')
        markers.activate(marker, self.store.store_dir, 'first', 'task')
        markers.clear(marker, self.store.store_dir, 'second')
        markers.clear(marker, self.store.store_dir, 'first', 'other-task')
        self.assertTrue(marker.exists())
        markers.clear(marker, self.store.store_dir, 'first', 'task')
        self.assertFalse(marker.exists())

    def test_hook_internal_error_denies_instead_of_allowing(self):
        marker = self.root / '.agent/local/active-task.json'
        marker.write_text(json.dumps({'store_dir': str(self.root / 'missing-store'), 'run_id': 'none', 'task_id': 'none'}), encoding='utf-8', newline='\n')
        verdict = self.hook('pretooluse_gate.py', {'tool_name': 'Bash', 'tool_input': {'command': 'git diff'}})
        self.assertEqual(verdict['hookSpecificOutput']['permissionDecision'], 'deny')
        self.assertFalse((self.root / 'missing-store').exists())

    def test_cli_task_lifecycle_uses_shared_marker_and_records_timing(self):
        def cli(*args):
            result = subprocess.run([sys.executable, str(self.kit / 'runtime/python/agentic_runtime/cli.py'), *args],
                                    cwd=self.root, capture_output=True, text=True,
                                    env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'), timeout=15, encoding='utf-8', errors='replace')
            self.assertEqual(result.returncode, 0, result.stderr)
            return json.loads(result.stdout)
        run = cli('start', '--project', 'fixture', '--type', 'discovery', '--title', 'CLI integration')
        task = cli('task-start', run['run_id'], '--skill', 'prompt-intake-adapter')
        marker = self.root / '.agent/local/active-task.json'
        self.assertEqual(json.loads(marker.read_text(encoding='utf-8'))['task_id'], task['task_id'])
        cli('task-fail', run['run_id'], task['task_id'], '--error', 'Fixture interrupted')
        self.assertFalse(marker.exists())
        events = cli('timing', run['run_id'])
        self.assertEqual(events[0]['event'], 'FAILED')


class UngovernedWriteTests(HarnessCase):
    hook = HookTests.hook

    def decision(self, path, tool='Write'):
        out = self.hook('pretooluse_gate.py', {'tool_name': tool, 'tool_input': {'file_path': str(path)}})
        return out['hookSpecificOutput'].get('permissionDecision', 'defer')

    def test_no_open_run_defers_to_host_permissions(self):
        self.assertEqual(self.decision(self.root / 'src/app.py'), 'defer')
        bash = self.hook('pretooluse_gate.py', {'tool_name': 'Bash', 'tool_input': {'command': 'rm -rf x'}})
        self.assertNotIn('permissionDecision', bash['hookSpecificOutput'])

    def test_open_run_without_task_denies_code_but_not_documents(self):
        self.start()
        self.assertEqual(self.decision(self.root / 'src/app.py'), 'deny')
        self.assertEqual(self.decision(self.root / 'src/app.py', 'Edit'), 'deny')
        self.assertEqual(self.decision(self.root / 'agentic/data/project-context/features/X/WORK-ITEM.md'), 'defer')
        self.assertEqual(self.decision(self.root / '.agent/HANDOFF.md'), 'defer')
        self.assertEqual(self.decision(self.root.parent / 'outside-scratch.txt'), 'defer')
        denied = self.hook('pretooluse_gate.py', {'tool_name': 'Write', 'tool_input': {'file_path': str(self.root / 'src/app.py')}})
        self.assertIn(f'task-start {self.run_id}', denied['hookSpecificOutput']['permissionDecisionReason'])

    def test_ledger_is_write_protected_even_without_a_run(self):
        self.assertEqual(self.decision(self.root / '.agent/state/runs/R/events/forged.json'), 'deny')

    def test_finished_run_no_longer_blocks(self):
        self.start()
        self.orch.cancel(self.run_id)
        self.assertEqual(self.decision(self.root / 'src/app.py'), 'defer')

    def test_opt_out_setting(self):
        self.start()
        path = self.kit / 'config/platform.json'
        data = json.loads(path.read_text(encoding='utf-8'))
        data['require_task_for_code_writes'] = False
        path.write_text(json.dumps(data), encoding='utf-8')
        self.assertEqual(self.decision(self.root / 'src/app.py'), 'defer')
