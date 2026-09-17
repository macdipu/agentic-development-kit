#!/usr/bin/env python3
"""Real checks and file changes in an isolated legacy fixture; synthetic approvals."""
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

KIT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KIT / 'runtime/python'))
from agentic_runtime.orchestrator import Orchestrator
from agentic_runtime.store import RuntimeStore
from agentic_runtime.tools import build_default_tools


def result(evidence, **outputs):
    return {'status': 'READY', 'evidence': [evidence], 'blocking_issues': [],
            'open_questions': [], 'recommended_next_step': 'Continue fixture delivery', 'outputs': outputs}


def demonstrate():
    with tempfile.TemporaryDirectory(prefix='agentic-legacy-') as directory:
        root = Path(directory)
        for name in ('price.py', 'test_price.py'):
            shutil.copy2(KIT / 'examples/legacy-project' / name, root / name)
        rules = [{'argv': [sys.executable, '-B', '-m', 'unittest', 'discover'], 'permission': 'run_check'}]
        tools = build_default_tools(root, rules)
        store = RuntimeStore(str(root / 'state'))
        orch = Orchestrator(store, KIT, tools)
        run = orch.start('legacy-fixture', 'existing_task', 'Charge shipping once per order', repo=root)
        run_id = run.run_id
        orch.execute(run_id, 'prompt-intake-adapter', lambda c, t: result('test_price.py', requirement='One shipping charge per order'))
        orch.transition(run_id, 'CONTEXT')
        orch.record_context(run_id, ['price.py', 'test_price.py'])
        def baseline(context, call):
            check = call('run_command', {'command': sys.executable, 'args': ['-B', '-m', 'unittest', 'discover']}, 'baseline')
            if check['returncode'] == 0:
                raise RuntimeError('Legacy fixture must reproduce its known defect')
            return result('test_price.py', baseline_failure=check['stderr'], existing_behavior='Shipping charged per item')
        orch.execute(run_id, 'test-baseline-agent', baseline)
        orch.approve(run_id, 'technical', 'synthetic fixture reviewer', comment='Test fixture only; not human authorization')
        orch.transition(run_id, 'IMPLEMENTATION')
        def implement(context, call):
            before = call('read_file', {'path': 'price.py'})['content']
            after = before.replace('+ 100 * quantity', '+ 100')
            call('write_file', {'path': 'price.py', 'content': after}, 'fix-shipping')
            check = call('run_command', {'command': sys.executable, 'args': ['-B', '-m', 'unittest', 'discover']}, 'implementation-check')
            if check['returncode']:
                raise RuntimeError(check['stderr'])
            return result('price.py', verification=check)
        orch.execute(run_id, 'implementation-agent', implement)
        orch.transition(run_id, 'REVIEW')
        def review(context, call):
            source = call('read_file', {'path': 'price.py'})['content']
            if 'return unit_cents * quantity + 100\n' not in source:
                raise RuntimeError('Expected bounded change absent')
            return result('price.py', reviewed='Shipping charge is independent of item count')
        orch.execute(run_id, 'code-review-agent', review)
        orch.transition(run_id, 'QA')
        def qa(context, call):
            check = call('run_command', {'command': sys.executable, 'args': ['-B', '-m', 'unittest', 'discover']}, 'qa')
            if check['returncode']:
                raise RuntimeError(check['stderr'])
            return result('test_price.py', verification=check)
        orch.execute(run_id, 'automated-qa-agent', qa)
        orch.approve(run_id, 'release', 'synthetic fixture reviewer', comment='Readiness fixture only; no deployment')
        orch.transition(run_id, 'RELEASE')
        orch.execute(run_id, 'release-readiness-agent', lambda c, t: result('test_price.py', deployment=False))
        completed = orch.transition(run_id, 'COMPLETED')
        return {'status': completed.status, 'fixture': True, 'real_checks': True,
                'baseline': 'FAIL (expected defect)', 'final_checks': 'PASS (2 tests)',
                'approvals': 'synthetic test records', 'deployment': False,
                'timing': orch.task_timings(run_id)}


if __name__ == '__main__':
    print(json.dumps(demonstrate(), indent=2))
