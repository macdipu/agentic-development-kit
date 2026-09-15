import importlib.util
from support import KIT, HarnessCase


class DeliveryTests(HarnessCase):
    def test_legacy_fixture_baseline_fix_review_qa_and_readiness(self):
        spec = importlib.util.spec_from_file_location('legacy_delivery', KIT / 'examples/legacy-delivery.py')
        example = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(example)
        report = example.demonstrate()
        self.assertEqual(report['status'], 'COMPLETED')
        self.assertTrue(report['real_checks'])
        self.assertFalse(report['deployment'])
        self.assertEqual(len(report['timing']), 6)
