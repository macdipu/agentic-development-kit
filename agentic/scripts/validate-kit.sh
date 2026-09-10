#!/usr/bin/env sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
[ -f "$ROOT/AGENTS.md" ] || { echo "Missing AGENTS.md"; exit 1; }
[ -f "$ROOT/CLAUDE.md" ] || { echo "Missing CLAUDE.md"; exit 1; }
[ -d "$ROOT/agentic/skills" ] || { echo "Missing skills"; exit 1; }
find "$ROOT/agentic/skills" -mindepth 1 -maxdepth 1 -type d | while read -r d; do
  [ -f "$d/SKILL.md" ] || { echo "Missing SKILL.md in $d"; exit 1; }
done
python3 -m py_compile "$ROOT"/agentic/runtime/python/agentic_runtime/*.py
echo "Kit validation passed"
