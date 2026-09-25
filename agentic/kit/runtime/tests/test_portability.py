import hashlib
import json

from support import HarnessCase, ready
from agentic_runtime.context import file_hash, snapshot, snapshot_state
from agentic_runtime.registry import SkillRegistry
from agentic_runtime.tools import command_rule


class PortabilityTests(HarnessCase):
    """A run written on one OS must resume unchanged on another."""

    def test_crlf_and_lf_checkouts_hash_identically(self):
        lf, crlf = self.root / 'lf.txt', self.root / 'crlf.txt'
        lf.write_bytes(b'one\ntwo\n')
        crlf.write_bytes(b'one\r\ntwo\r\n')
        self.assertEqual(file_hash(str(lf)), file_hash(str(crlf)))
        binary = self.root / 'bin.dat'
        binary.write_bytes(b'\0\r\n')
        self.assertEqual(file_hash(str(binary)), hashlib.sha256(b'\0\r\n').hexdigest())

    def test_skill_revision_ignores_line_endings(self):
        before = SkillRegistry(self.kit / 'skills').discover()['adr-generator']['revision']
        skill = self.kit / 'skills/adr-generator/SKILL.md'
        skill.write_bytes(skill.read_bytes().replace(b'\n', b'\r\n'))
        self.assertEqual(SkillRegistry(self.kit / 'skills').discover()['adr-generator']['revision'], before)

    def test_stored_paths_use_forward_slashes(self):
        (self.root / 'lib').mkdir()
        (self.root / 'lib/a.py').write_text('x\n', encoding='utf-8')
        self.start()
        self.result('prompt-intake-adapter')
        self.orch.transition(self.run_id, 'CONTEXT')
        self.orch.record_context(self.run_id, ['lib/a.py'])
        ops = [op for f in sorted((self.store.store_dir / self.run_id / 'events').glob('*.json'))
               for op in json.loads(f.read_text(encoding='utf-8'))['ops'] if op['op'] == 'run']
        self.assertEqual(ops[0]['meta']['repo'], '../../..')
        contexts = [op['meta']['context'] for op in ops if 'context' in op.get('meta', {})]
        self.assertEqual(list(contexts[-1]['files']), ['lib/a.py'])

    def test_legacy_backslash_context_keys_stay_available(self):
        (self.root / 'lib').mkdir()
        (self.root / 'lib/a.py').write_text('x\n', encoding='utf-8')
        recorded = snapshot(self.root, ['lib/a.py'])
        legacy = {'files': {'lib\\a.py': recorded['files']['lib/a.py']}}
        self.assertEqual(snapshot_state(self.root, legacy), 'AVAILABLE')
        self.start()
        data = self.store._load(self.run_id)
        data['run']['metadata']['context'] = legacy
        data['run']['metadata']['repo'] = '..\\..\\..'
        self.store.import_state(self.run_id, data)
        run = self.store.get_run(self.run_id)
        self.assertEqual(list(run.metadata['context']['files']), ['lib/a.py'])
        self.assertEqual(run.metadata['repo'], str(self.root.resolve()))

    def test_windows_executable_path_matches_its_rule(self):
        exe = 'C:\\Python\\python.exe'
        rules = [{'argv': [exe, '-m', 'unittest'], 'permission': 'run_check'}]
        self.assertEqual(command_rule(exe, ['-m', 'unittest'], rules)[1], 'run_check')

    def test_migrate_pins_accepts_only_unchanged_legacy_content(self):
        self.start()
        skills = SkillRegistry(self.kit / 'skills').discover()
        legacy_pin = next(r for r in skills['adr-generator']['legacy_revisions'] if r != skills['adr-generator']['revision'])
        data = self.store._load(self.run_id)
        data['run']['metadata']['skill_pins']['adr-generator'] = legacy_pin
        self.store.import_state(self.run_id, data)
        run = self.orch.migrate_pins(self.run_id, 'operator', 'Pre-portable pins')
        self.assertEqual(run.metadata['skill_pins']['adr-generator'], skills['adr-generator']['revision'])
        events = [e['event'] for e in self.store.ledger(self.run_id)['audit_events']]
        self.assertIn('PINS_MIGRATED', events)

        data = self.store._load(self.run_id)
        data['run']['metadata']['skill_pins']['adr-generator'] = 'f' * 64
        self.store.import_state(self.run_id, data)
        with self.assertRaisesRegex(ValueError, 'content changed'):
            self.orch.migrate_pins(self.run_id, 'operator', 'Changed content')
