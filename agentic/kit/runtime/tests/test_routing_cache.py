import tempfile
import unittest
from pathlib import Path

import support  # noqa: F401 -- sets sys.path so agentic_runtime is importable
from agentic_runtime.routing_cache import RoutingCache, cache_key, compute_kit_version


class RoutingCacheTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='route-cache-test-')
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.repo_root = root / 'repo'
        self.kit_dir = self.repo_root / 'agentic/kit'
        (self.kit_dir / 'workflows').mkdir(parents=True)
        (self.kit_dir / 'workflows/brownfield.md').write_text('Brownfield workflow v1\n')
        (self.repo_root / 'AGENTS.md').write_text('Core behavior v1\n')
        self.cache = RoutingCache(root / 'state/route-cache.json')

    def version(self):
        return compute_kit_version(self.repo_root, self.kit_dir)

    def test_cache_key_requires_valid_project_type(self):
        with self.assertRaises(ValueError):
            cache_key('bug', 'not-a-real-type', 'auth')
        self.assertEqual(cache_key('bug', 'brownfield', 'auth'), 'bug:brownfield:auth')

    def test_cache_key_requires_nonempty_fields(self):
        with self.assertRaises(ValueError):
            cache_key('', 'brownfield', 'auth')
        with self.assertRaises(ValueError):
            cache_key('bug', 'brownfield', '  ')

    def test_get_misses_when_absent(self):
        self.assertIsNone(self.cache.get(cache_key('bug', 'brownfield', 'auth'), self.version()))

    def test_put_then_get_hits_with_matching_version(self):
        key = cache_key('bug', 'brownfield', 'auth')
        version = self.version()
        decision = {'route': ['INTAKE', 'CONTEXT'], 'workflow_doc': 'agentic/kit/workflows/brownfield.md'}
        self.cache.put(key, version, decision, '2026-01-01T00:00:00+00:00')
        entry = self.cache.get(key, version)
        self.assertEqual(entry['decision'], decision)
        self.assertEqual(entry['kit_version'], version)

    def test_doc_edit_invalidates_cached_entry(self):
        key = cache_key('bug', 'brownfield', 'auth')
        version = self.version()
        self.cache.put(key, version, {'route': ['INTAKE']}, '2026-01-01T00:00:00+00:00')
        (self.kit_dir / 'workflows/brownfield.md').write_text('Brownfield workflow v2\n')
        self.assertIsNone(self.cache.get(key, self.version()))

    def test_unrelated_key_stays_valid_after_another_key_is_written(self):
        version = self.version()
        self.cache.put(cache_key('bug', 'brownfield', 'auth'), version, {'route': ['INTAKE']}, '2026-01-01T00:00:00+00:00')
        self.cache.put(cache_key('new_feature', 'greenfield', 'billing'), version, {'route': ['REQUIREMENTS']}, '2026-01-01T00:00:00+00:00')
        self.assertIsNotNone(self.cache.get(cache_key('bug', 'brownfield', 'auth'), version))
        self.assertIsNotNone(self.cache.get(cache_key('new_feature', 'greenfield', 'billing'), version))

    def test_clear_wipes_all_entries(self):
        key = cache_key('bug', 'brownfield', 'auth')
        version = self.version()
        self.cache.put(key, version, {'route': ['INTAKE']}, '2026-01-01T00:00:00+00:00')
        self.cache.clear()
        self.assertIsNone(self.cache.get(key, version))

    def test_put_rejects_non_object_decision(self):
        with self.assertRaises(ValueError):
            self.cache.put(cache_key('bug', 'brownfield', 'auth'), self.version(), ['not', 'a', 'dict'], '2026-01-01T00:00:00+00:00')


if __name__ == '__main__':
    unittest.main()
