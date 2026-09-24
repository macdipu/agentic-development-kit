"""Canonical installed-kit paths, shared by CLI, hooks, and diagnostics.

All agent state lives under the repo-root `.agent/` folder: handoff notes and
session records beside the runtime ledger, all git-tracked so another machine
can resume after `git pull`. Only lock/temp files and logs are gitignored.
"""
from pathlib import Path

KIT = Path(__file__).resolve().parents[3]
AGENTIC = KIT.parent
REPO_ROOT = AGENTIC.parent
AGENT_DIR_REL = Path('.agent')
STATE_DIR_REL = AGENT_DIR_REL / 'runtime'
RUNS_DIR_REL = STATE_DIR_REL / 'runs'
ACTIVE_TASK_POINTER_REL = STATE_DIR_REL / 'active-task.json'
STATE_DIR = REPO_ROOT / STATE_DIR_REL
RUNS_DIR = REPO_ROOT / RUNS_DIR_REL
ACTIVE_TASK_POINTER = REPO_ROOT / ACTIVE_TASK_POINTER_REL
ROUTE_CACHE_FILE = STATE_DIR / 'route-cache.json'
