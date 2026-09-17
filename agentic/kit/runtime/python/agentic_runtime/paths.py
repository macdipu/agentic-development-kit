"""Canonical installed-kit paths, shared by CLI, hooks, and diagnostics."""
from pathlib import Path

KIT = Path(__file__).resolve().parents[3]
AGENTIC = KIT.parent
REPO_ROOT = AGENTIC.parent
STATE_DIR = AGENTIC / 'data/runtime/state'
RUNS_DIR = STATE_DIR / 'runs'
ACTIVE_TASK_POINTER = STATE_DIR / 'active-task.json'
