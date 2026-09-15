import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

from support import KIT
from agentic_runtime.production import check_readiness, required_controls


class ProductionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='production-contract-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.now = datetime.now(timezone.utc)
        self.file = self.root / 'evidence.md'
        self.file.write_text('Synthetic external-control test report')

    def document(self, stage='OBSERVE'):
        document = {'schema_version': 1, 'stage': stage, 'environment': 'fixture',
                    'owner': 'fixture operator', 'change_sha256': 'a' * 64,
                    'operations': ['inspect-fixture'], 'controls': {},
                    'limits': {'max_actions': 1, 'max_seconds': 30, 'max_affected_resources': 1}}
        for control in required_controls(stage):
            document['controls'][control] = {
                'status': 'VERIFIED', 'reviewer': 'synthetic reviewer reference',
                'verified_at': (self.now - timedelta(hours=1)).isoformat(),
                'expires_at': (self.now + timedelta(hours=1)).isoformat(),
                'path': self.file.name, 'sha256': hashlib.sha256(self.file.read_bytes()).hexdigest(),
                'environment': document['environment'], 'change_sha256': document['change_sha256'],
                'operations': list(document['operations']),
            }
        return document

    def test_complete_evidence_never_grants_execution(self):
        for stage in ('OBSERVE', 'PREPARE', 'APPROVED_EXECUTION', 'BOUNDED_AUTONOMY'):
            report = check_readiness(self.document(stage), self.root, self.now)
            self.assertEqual(report['status'], 'EVIDENCE_COMPLETE', report)
            self.assertFalse(report['deployment_authorized'])

    def test_missing_expired_or_changed_evidence_blocks(self):
        for field, value in [('status', 'PENDING'), ('path', 'missing.md'),
                             ('expires_at', (self.now - timedelta(seconds=1)).isoformat()),
                             ('environment', 'different-env'), ('change_sha256', 'b' * 64),
                             ('operations', ['deploy']), ('sha256', 'b' * 64)]:
            doc = self.document()
            doc['controls']['audit'][field] = value
            self.assertEqual(check_readiness(doc, self.root, self.now)['status'], 'BLOCKED', field)

    def test_changed_artifact_invalidates_all_control_bindings(self):
        doc = self.document('APPROVED_EXECUTION')
        doc['change_sha256'] = 'c' * 64
        report = check_readiness(doc, self.root, self.now)
        self.assertEqual(len(report['blocking_issues']), len(required_controls('APPROVED_EXECUTION')))

    def test_autonomy_requires_limits_and_specific_operations(self):
        doc = self.document('BOUNDED_AUTONOMY')
        doc['limits']['max_actions'] = 0
        doc['operations'] = ['*']
        self.assertEqual(check_readiness(doc, self.root, self.now)['status'], 'BLOCKED')
