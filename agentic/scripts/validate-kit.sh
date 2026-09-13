#!/usr/bin/env sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
export PYTHONDONTWRITEBYTECODE=1
python3 "$ROOT/agentic/scripts/validate_structure.py"
python3 -m unittest discover -s "$ROOT/agentic/runtime/tests" -v
python3 "$ROOT/agentic/evals/run_evals.py"
python3 "$ROOT/agentic/examples/runtime-demo.py"
echo "Kit validation passed"
