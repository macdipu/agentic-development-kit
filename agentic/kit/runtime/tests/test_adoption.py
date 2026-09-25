import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from support import KIT
from agentic_runtime.doctor import diagnose, probe_hooks
from agentic_runtime.installation import install_claude_hooks, managed_text

spec = importlib.util.spec_from_file_location('kit_installer', KIT / 'scripts/init_project.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class AdoptionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='agentic-adoption-')
        self.addCleanup(self.temporary.cleanup)
        self.host = Path(self.temporary.name).resolve() / 'host'
        self.host.mkdir()

    def install(self, **kwargs):
        return installer.install(self.host, 'fixture-project', 'brownfield',
                                 kwargs.pop('mode', 'instruction-only'), kwargs.pop('agent', 'cli'), **kwargs)

    def test_fresh_instruction_install_and_reinstall(self):
        self.assertTrue(self.install()['ok'])
        self.assertTrue((self.host / 'agentic/SKILL-CATALOG.md').exists())
        self.assertFalse((self.host / '.claude/settings.json').exists())
        instructions = (self.host / 'AGENTS.md').read_text(encoding='utf-8')
        self.assertTrue(self.install()['ok'])
        self.assertEqual((self.host / 'AGENTS.md').read_text(encoding='utf-8'), instructions)
        self.assertFalse((self.host / 'agentic/data/work-items/TASK-KIT-001.md').exists())
        self.assertFalse((self.host / 'agentic/data/project-context/kit-runtime.json').exists())

    def test_install_does_not_double_the_agents_import(self):
        (self.host / 'CLAUDE.md').write_text('Host notes\n@AGENTS.md\n', encoding='utf-8', newline='\n')
        self.assertTrue(self.install()['ok'])
        claude = (self.host / 'CLAUDE.md').read_text(encoding='utf-8')
        self.assertEqual(claude.count('@AGENTS.md'), 1)
        self.assertTrue(claude.startswith('Host notes\n\n<!-- agentic-kit:start -->'))
        self.assertTrue(self.install()['ok'])
        self.assertEqual((self.host / 'CLAUDE.md').read_text(encoding='utf-8'), claude)

    def test_harness_install_preserves_host_rules_and_hooks(self):
        (self.host / 'AGENTS.md').write_text('Host business rules\n', encoding='utf-8', newline='\n')
        (self.host / 'README.md').write_text('Host README\n', encoding='utf-8', newline='\n')
        (self.host / '.claude').mkdir()
        custom = {'permissions': {'deny': ['Bash(rm:*)']}, 'hooks': {'SessionStart': [{'hooks': [{'type': 'command', 'command': 'host-hook'}]}]}}
        (self.host / '.claude/settings.json').write_text(json.dumps(custom), encoding='utf-8', newline='\n')
        report = self.install(mode='local-harness', agent='claude')
        self.assertTrue(report['ok'])
        self.assertTrue((self.host / 'AGENTS.md').read_text(encoding='utf-8').startswith('Host business rules\n'))
        self.assertEqual((self.host / 'README.md').read_text(encoding='utf-8'), 'Host README\n')
        settings = json.loads((self.host / '.claude/settings.json').read_text(encoding='utf-8'))
        self.assertEqual(settings['permissions'], custom['permissions'])
        self.assertIn(custom['hooks']['SessionStart'][0], settings['hooks']['SessionStart'])
        self.assertTrue(self.install(mode=None, agent=None)['ok'])
        self.assertEqual(json.loads((self.host / '.claude/settings.json').read_text(encoding='utf-8')), settings)

    def test_upgrade_preserves_configuration_and_context(self):
        self.install()
        config = self.host / 'agentic/kit/config/allowed-commands.json'
        config.write_text(json.dumps({'commands': ['git status']}), encoding='utf-8', newline='\n')
        context = self.host / 'agentic/data/project-context/project.yaml'
        context.write_text('project: existing-business\n', encoding='utf-8', newline='\n')
        report = self.install(upgrade=True)
        self.assertTrue(report['ok'])
        self.assertTrue(Path(report['backup']).exists())
        self.assertEqual(json.loads(config.read_text(encoding='utf-8'))['commands'], ['git status'])
        self.assertEqual(context.read_text(encoding='utf-8'), 'project: existing-business\n')

    def test_malformed_settings_leave_host_untouched(self):
        (self.host / '.claude').mkdir()
        (self.host / '.claude/settings.json').write_text('{broken', encoding='utf-8', newline='\n')
        (self.host / 'AGENTS.md').write_text('original', encoding='utf-8', newline='\n')
        with self.assertRaises(ValueError):
            self.install(mode='local-harness', agent='claude')
        self.assertEqual((self.host / 'AGENTS.md').read_text(encoding='utf-8'), 'original')
        self.assertFalse((self.host / 'agentic/kit').exists())

    def test_failed_commit_restores_original_files(self):
        (self.host / 'AGENTS.md').write_text('original', encoding='utf-8', newline='\n')
        replace = os.replace
        def interrupted(source, destination):
            if Path(destination) == self.host / 'CLAUDE.md':
                raise OSError('fixture interrupted installation')
            return replace(source, destination)
        with patch.object(installer.os, 'replace', side_effect=interrupted):
            with self.assertRaises(OSError):
                self.install()
        self.assertEqual((self.host / 'AGENTS.md').read_text(encoding='utf-8'), 'original')
        self.assertFalse((self.host / 'agentic/kit').exists())
        self.assertTrue(self.install()['ok'])

    def test_install_hooks_merges_into_existing_settings(self):
        template = KIT / 'config/hooks.json'
        (self.host / '.claude').mkdir()
        custom = {'permissions': {'deny': ['Bash(rm:*)']}, 'hooks': {'SessionStart': [{'hooks': [{'type': 'command', 'command': 'host-hook'}]}]}}
        (self.host / '.claude/settings.json').write_text(json.dumps(custom), encoding='utf-8', newline='\n')
        self.assertTrue(install_claude_hooks(self.host, template)['changed'])
        settings = json.loads((self.host / '.claude/settings.json').read_text(encoding='utf-8'))
        self.assertEqual(settings['permissions'], custom['permissions'])
        self.assertIn(custom['hooks']['SessionStart'][0], settings['hooks']['SessionStart'])
        for event, entries in json.loads(template.read_text(encoding='utf-8'))['hooks'].items():
            for entry in entries:
                self.assertIn(entry, settings['hooks'][event])
        self.assertFalse(install_claude_hooks(self.host, template)['changed'])

    def test_doctor_detects_disabled_or_wrong_hooks(self):
        self.install(mode='local-harness', agent='claude')
        settings = self.host / '.claude/settings.json'
        content = json.loads(settings.read_text(encoding='utf-8'))
        content['disableAllHooks'] = True
        settings.write_text(json.dumps(content), encoding='utf-8', newline='\n')
        self.assertFalse(diagnose(self.host)['ok'])

    def test_framework_detection_generates_existing_script_commands(self):
        (self.host / 'package.json').write_text(json.dumps({'scripts': {'test': 'node test.js'}}), encoding='utf-8', newline='\n')
        self.install()
        rules = json.loads((self.host / 'agentic/kit/config/allowed-commands.json').read_text(encoding='utf-8'))['commands']
        self.assertIn({'argv': ['npm', 'run', 'test'], 'permission': 'run_check'}, rules)
        self.assertNotIn({'argv': ['npm', 'run', 'build'], 'permission': 'run_check'}, rules)

    def test_managed_block_preserves_surrounding_text(self):
        text = managed_text('before\n', 'first') + 'after\n'
        updated = managed_text(text, 'second')
        self.assertTrue(updated.startswith('before\n'))
        self.assertTrue(updated.endswith('after\n'))
        self.assertNotIn('first', updated)

    def test_upgrade_refuses_active_run_without_changing_kit(self):
        from agentic_runtime.orchestrator import Orchestrator
        from agentic_runtime.store import RuntimeStore
        self.install(mode='local-harness')
        path = self.host / 'agentic/kit/config/platform.json'
        original = path.read_bytes()
        store = RuntimeStore(str(self.host / '.agent/state/runs'))
        Orchestrator(store, self.host / 'agentic/kit').start('fixture', 'discovery', 'Unfinished work', repo=self.host)
        with self.assertRaisesRegex(ValueError, 'Finish or cancel'):
            self.install(upgrade=True)
        self.assertEqual(path.read_bytes(), original)

    def test_upgrade_refuses_to_discard_host_edits_to_kit_files(self):
        self.install()
        template = self.host / 'agentic/kit/templates/task.md'
        template.write_text(template.read_text(encoding='utf-8') + '## Host-only field\n', encoding='utf-8', newline='\n')
        with self.assertRaisesRegex(ValueError, 'templates/task.md'):
            self.install(upgrade=True)
        self.assertIn('Host-only field', template.read_text(encoding='utf-8'))
        report = self.install(upgrade=True, discard_kit_edits=True)
        self.assertTrue(any('templates/task.md' in note for note in report['notes']))
        self.assertNotIn('Host-only field', template.read_text(encoding='utf-8'))
        self.assertTrue((Path(report['backup']) / 'agentic/kit/templates/task.md').exists())

    def test_upgrade_adds_new_config_keys_without_changing_host_values(self):
        self.install()
        path = self.host / 'agentic/kit/config/platform.json'
        data = json.loads(path.read_text(encoding='utf-8'))
        data['max_task_seconds'] = 1234
        del data['skill_budgets']
        path.write_text(json.dumps(data), encoding='utf-8', newline='\n')
        report = self.install(upgrade=True)
        merged = json.loads(path.read_text(encoding='utf-8'))
        self.assertEqual(merged['max_task_seconds'], 1234)
        self.assertIn('implementation-agent', merged['skill_budgets'])
        self.assertTrue(any('skill_budgets' in note for note in report['notes']))

    def test_fresh_install_commits_state_but_not_machine_local_files(self):
        self.install()
        ignored = (self.host / '.gitignore').read_text(encoding='utf-8').splitlines()
        self.assertIn('/.agent/local/', ignored)
        self.assertIn('/.agent/HANDOFF.md', ignored)
        self.assertNotIn('/.agent/', ignored)  # .agent/state and .agent/sessions are committed

    def test_upgrade_refreshes_kit_docs(self):
        self.install()
        readme = self.host / 'agentic/README.md'
        readme.write_text('stale kit readme\n', encoding='utf-8', newline='\n')
        self.install()
        self.assertEqual(readme.read_text(encoding='utf-8'), 'stale kit readme\n')
        self.install(upgrade=True)
        self.assertEqual(readme.read_text(encoding='utf-8'), (KIT.parent / 'README.md').read_text(encoding='utf-8'))

    def test_host_doc_links_resolve_against_host_during_staged_validation(self):
        self.install()
        (self.host / 'docs').mkdir()
        (self.host / 'docs/ARCH.md').write_text('arch\n', encoding='utf-8', newline='\n')
        agents = self.host / 'AGENTS.md'
        agents.write_text(agents.read_text(encoding='utf-8') + '\nSee [arch](docs/ARCH.md).\n', encoding='utf-8', newline='\n')
        self.assertTrue(self.install()['ok'])
        agents.write_text(agents.read_text(encoding='utf-8') + '\nSee [gone](docs/MISSING.md).\n', encoding='utf-8', newline='\n')
        with self.assertRaisesRegex(ValueError, 'Broken local link'):
            self.install()

    def test_literal_source_path_is_validated_before_install_commit(self):
        self.install()
        source = self.host / 'agentic/kit/skills/srs-generator/SKILL.md'
        source.write_text(source.read_text(encoding='utf-8') + '\nTemplate: `agentic/kit/templates/missing-fixture.md`\n', encoding='utf-8', newline='\n')
        before = (self.host / 'AGENTS.md').read_text(encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'Broken literal kit path'):
            self.install()
        self.assertEqual((self.host / 'AGENTS.md').read_text(encoding='utf-8'), before)


class MonorepoDetectionTests(unittest.TestCase):
    def test_subprojects_get_directory_scoped_commands(self):
        from agentic_runtime.doctor import detect_project
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'backend/svc').mkdir(parents=True)
            (root / 'backend/pom.xml').write_text('<project/>', encoding='utf-8')
            (root / 'backend/svc/pom.xml').write_text('<project/>', encoding='utf-8')
            (root / 'web/node_modules/dep').mkdir(parents=True)
            (root / 'web/package.json').write_text(json.dumps({'scripts': {'test': 'x', 'build': 'y'}}), encoding='utf-8')
            (root / 'web/node_modules/dep/package.json').write_text('{}', encoding='utf-8')
            (root / 'app').mkdir()
            (root / 'app/pubspec.yaml').write_text('flutter:\n', encoding='utf-8')
            (root / 'scripts').mkdir()
            (root / 'scripts/verify-app.sh').write_text('', encoding='utf-8')
            (root / 'scripts/deploy.sh').write_text('', encoding='utf-8')
            found = detect_project(root)
            argvs = [c['argv'] for c in found['commands']]
            self.assertIn(['mvn', '-B', '-f', 'backend/pom.xml', 'verify'], argvs)
            self.assertNotIn(['mvn', '-B', '-f', 'backend/svc/pom.xml', 'verify'], argvs)
            self.assertIn(['npm', '--prefix', 'web', 'run', 'test'], argvs)
            self.assertNotIn(['sh', 'scripts/verify-app.sh'], argvs)  # suggested, never auto-allowlisted
            self.assertTrue(any('scripts/verify-app.sh' in u for u in found['unknowns']))
            self.assertFalse(any('deploy.sh' in u for u in found['unknowns']))
            self.assertEqual(sorted(found['frameworks']), ['flutter:app', 'maven:backend', 'node:web'])
            self.assertTrue(any('wrapper' in u and 'app' in u for u in found['unknowns']))
