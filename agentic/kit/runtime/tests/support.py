import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

KIT = Path(__file__).resolve().parents[2]
ROOT = KIT.parent.parent
sys.path.insert(0, str(KIT / 'runtime/python'))
from agentic_runtime.orchestrator import Orchestrator
from agentic_runtime.store import RuntimeStore
from agentic_runtime.tools import build_default_tools


def ready(evidence='scope.md', **outputs):
    return {'status': 'READY', 'evidence': [evidence], 'blocking_issues': [],
            'open_questions': [], 'recommended_next_step': 'Continue fixture', 'outputs': outputs}


class HarnessCase(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='agentic-test-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.kit = self.root / 'agentic/kit'
        for name in ('config', 'skills', 'runtime'):
            shutil.copytree(KIT / name, self.kit / name, ignore=shutil.ignore_patterns('__pycache__', 'tests'))
        (self.root / 'scope.md').write_text('Fixture scope\n')
        self.store = RuntimeStore(str(self.root / 'agentic/data/runtime/state/runs'))
        self.tools = build_default_tools(self.root, [{'argv': [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests'], 'permission': 'run_check'}])
        self.orch = Orchestrator(self.store, self.kit, self.tools)

    def start(self, kind='discovery', dry_run=False):
        run = self.orch.start('fixture', kind, 'Regression fixture', dry_run=dry_run, repo=self.root)
        self.run_id = run.run_id
        return run

    def result(self, skill):
        return self.orch.execute(self.run_id, skill, lambda c, t: ready())

    def context(self, kind='discovery', dry_run=False):
        self.start(kind, dry_run)
        self.result('prompt-intake-adapter')
        self.orch.transition(self.run_id, 'CONTEXT')
        self.orch.record_context(self.run_id, ['scope.md'])
        self.result('baseline-verifier')

    def implementation(self, dry_run=False):
        self.context('existing_task', dry_run)
        self.orch.approve(self.run_id, 'technical', 'synthetic fixture reviewer')
        self.orch.transition(self.run_id, 'IMPLEMENTATION')
