import json
import os
import subprocess
import sys
from unittest.mock import patch

from support import HarnessCase
from agentic_runtime import markers
from agentic_runtime.doctor import probe_hooks


class HookTests(HarnessCase):
    def hook(self, name, payload=None):
        result = subprocess.run([sys.executable, str(self.kit / 'runtime/hooks' / name)],
                                input=json.dumps(payload or {}), text=True, capture_output=True,
                                env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'), timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_installed_hook_probe(self):
        probe_hooks(self.kit)

    def test_corrupt_marker_denies_tools_and_reports_unknown_session(self):
        marker = self.root / 'agentic/data/runtime/state/active-task.json'
        marker.write_text('{invalid')
        verdict = self.hook('pretooluse_gate.py', {'tool_name': 'Write'})
        self.assertEqual(verdict['hookSpecificOutput']['permissionDecision'], 'deny')
        self.assertIn('UNKNOWN', self.hook('session_start_check.py')['hookSpecificOutput']['additionalContext'])

    def test_marker_cannot_be_overwritten_or_cleared_by_another_run(self):
        marker = self.root / 'agentic/data/runtime/state/active-task.json'
        markers.reserve(marker, self.store.db_path, 'first')
        with self.assertRaises(FileExistsError):
            markers.reserve(marker, self.store.db_path, 'second')
        markers.activate(marker, self.store.db_path, 'first', 'task')
        markers.clear(marker, self.store.db_path, 'second')
        markers.clear(marker, self.store.db_path, 'first', 'other-task')
        self.assertTrue(marker.exists())
        markers.clear(marker, self.store.db_path, 'first', 'task')
        self.assertFalse(marker.exists())

    def test_hook_internal_error_denies_instead_of_allowing(self):
        marker = self.root / 'agentic/data/runtime/state/active-task.json'
        marker.write_text(json.dumps({'db': str(self.root / 'missing.db'), 'run_id': 'none', 'task_id': 'none'}))
        verdict = self.hook('pretooluse_gate.py', {'tool_name': 'Bash', 'tool_input': {'command': 'git diff'}})
        self.assertEqual(verdict['hookSpecificOutput']['permissionDecision'], 'deny')
        self.assertFalse((self.root / 'missing.db').exists())

    def test_cli_task_lifecycle_uses_shared_marker_and_records_timing(self):
        def cli(*args):
            result = subprocess.run([sys.executable, str(self.kit / 'runtime/python/agentic_runtime/cli.py'), *args],
                                    cwd=self.root, capture_output=True, text=True,
                                    env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'), timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            return json.loads(result.stdout)
        run = cli('start', '--project', 'fixture', '--type', 'discovery', '--title', 'CLI integration')
        task = cli('task-start', run['run_id'], '--skill', 'prompt-intake-adapter')
        marker = self.root / 'agentic/data/runtime/state/active-task.json'
        self.assertEqual(json.loads(marker.read_text())['task_id'], task['task_id'])
        cli('task-fail', run['run_id'], task['task_id'], '--error', 'Fixture interrupted')
        self.assertFalse(marker.exists())
        events = cli('timing', run['run_id'])
        self.assertEqual(events[0]['event'], 'FAILED')
