#!/usr/bin/env python3
"""Deterministic behavioral cases, not model-quality evaluations."""
import argparse
import json
import sys
import tempfile
from pathlib import Path

KIT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KIT / 'runtime/python'))
from agentic_runtime.context import snapshot, snapshot_state
from agentic_runtime.policy import evaluate, workflow_route
from agentic_runtime.registry import SkillRegistry


def evaluate_case(case):
    data = case['input']
    if case['kind'] == 'policy':
        return {'allowed': evaluate(data['stage'], data.get('approvals', {})).allowed}
    if case['kind'] == 'context':
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'module.txt'
            path.write_text('baseline')
            recorded = snapshot(directory, ['module.txt'])
            if data.get('changed'):
                path.write_text('changed')
            if data.get('deleted'):
                path.unlink()
            state = snapshot_state(directory, recorded)
            return {'state': state, 'refresh_scope': state != 'AVAILABLE'}
    if case['kind'] == 'routing':
        route = workflow_route(data['work_type'], data.get('planning', 'NO_REPLAN'))
        stage = route[2]
        eligible = SkillRegistry(KIT / 'skills').eligible(stage)
        return {'next_stage_after_context': stage, 'requested_skill_eligible': data['skill'] in eligible}
    raise ValueError('Unknown eval kind: ' + str(case['kind']))


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--cases', type=Path, default=Path(__file__).parent / 'cases')
    args = parser.parse_args(argv)
    paths = sorted(args.cases.glob('*.json'))
    if not paths:
        print('FAIL: no eval cases found')
        return 1
    failures = 0
    for path in paths:
        try:
            case = json.loads(path.read_text())
            if not isinstance(case, dict) or set(case) != {'name', 'kind', 'input', 'expected'}:
                raise ValueError('Case requires name, kind, input, and expected')
            actual = evaluate_case(case)
            if actual != case['expected']:
                raise ValueError(f"expected {case['expected']!r}, got {actual!r}")
            print('PASS ' + case['name'])
        except (ValueError, KeyError, TypeError, OSError) as exc:
            print(f'FAIL {path.name}: {exc}')
            failures += 1
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
