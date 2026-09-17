#!/usr/bin/env python3
"""Isolated synthetic discovery flow; no model, human approval, or device launch."""
import json
import sys
import tempfile
from pathlib import Path

KIT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KIT / 'runtime/python'))
from agentic_runtime.orchestrator import Orchestrator
from agentic_runtime.registry import ToolRegistry
from agentic_runtime.store import RuntimeStore


def main():
    with tempfile.TemporaryDirectory(prefix='agentic-demo-') as directory:
        root = Path(directory)
        (root / 'scope.md').write_text('Synthetic task: demonstrate local workflow transitions.\n')
        store = RuntimeStore(str(root / 'state'))
        tools = ToolRegistry()
        effects = []
        tools.register('demo-artifact', lambda: effects.append('invoked'), 'L2', side_effecting=True)
        orch = Orchestrator(store, KIT, tools)
        run = orch.start('synthetic-demo', 'discovery', 'Validate local workflow wiring', dry_run=True, repo=root)
        def result(context, call_tool):
            return {'status':'READY', 'evidence':['scope.md'], 'blocking_issues':[], 'open_questions':[], 'recommended_next_step':'Continue the synthetic demo', 'outputs':{'synthetic':True}}
        orch.execute(run.run_id, 'prompt-intake-adapter', result)
        orch.transition(run.run_id, 'CONTEXT')
        orch.record_context(run.run_id, ['scope.md'])
        orch.execute(run.run_id, 'baseline-verifier', result)
        orch.transition(run.run_id, 'REVIEW')
        def review(context, call_tool):
            simulated = call_tool('demo-artifact', idempotency_key='one-artifact')
            if simulated['invoked'] or effects:
                raise RuntimeError('Dry-run failed to suppress the demo effect')
            return result(context, call_tool)
        orch.execute(run.run_id, 'code-review-agent', review)
        completed = orch.transition(run.run_id, 'COMPLETED')
        print(json.dumps({'status':completed.status, 'synthetic':True, 'dry_run':completed.dry_run, 'external_effects':len(effects), 'state':'Temporary state removed on exit'}, indent=2))


if __name__ == '__main__':
    main()
