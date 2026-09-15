#!/usr/bin/env sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../../.." && pwd)
export PYTHONDONTWRITEBYTECODE=1
python3 "$ROOT/agentic/kit/scripts/validate_structure.py"
python3 "$ROOT/agentic/kit/examples/runtime-demo.py"
python3 -m unittest discover -s "$ROOT/agentic/kit/runtime/tests" -v
echo "Kit validation passed"
