#!/usr/bin/env sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../../.." && pwd)
export PYTHONDONTWRITEBYTECODE=1
PY=${PYTHON:-python3}
"$PY" "$ROOT/agentic/kit/scripts/validate_structure.py"
"$PY" "$ROOT/agentic/kit/examples/runtime-demo.py"
"$PY" -m unittest discover -s "$ROOT/agentic/kit/runtime/tests" -v
echo "Kit validation passed"
