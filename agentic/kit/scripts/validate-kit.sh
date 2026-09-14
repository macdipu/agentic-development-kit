#!/usr/bin/env sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
export PYTHONDONTWRITEBYTECODE=1
python3 "$ROOT/agentic/scripts/validate_structure.py"
python3 "$ROOT/agentic/examples/runtime-demo.py"
echo "Kit validation passed"
