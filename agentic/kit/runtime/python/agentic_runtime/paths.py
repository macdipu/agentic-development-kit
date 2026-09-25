"""Canonical installed-kit paths, shared by CLI, hooks, and diagnostics.

All agent state lives under the repo-root `.agent/` folder:

    .agent/
    ├── HANDOFF.md        local  regenerated from state/handoffs/ (never committed)
    ├── sessions/*.md     committed  one file per session (agent-handoff compatible)
    ├── state/            committed  append-only: files are added, never edited,
    │   ├── runs/<RUN>/events/*.json     so `git pull` merges two machines' work
    │   │   (runs/<RUN>/.lock, .cache.json   without conflicts; lock and replay cache
    │   │    are ignored)
    │   ├── claims/<RUN>/*.json
    │   └── handoffs/*.md
    └── local/            ignored    this machine only: active-task pointer, clone id,
                                     route cache

State travels with the project's normal branch commits and pushes.
"""
from pathlib import Path

KIT = Path(__file__).resolve().parents[3]
AGENTIC = KIT.parent
REPO_ROOT = AGENTIC.parent
AGENT_DIR_REL = Path('.agent')
STATE_DIR_REL = AGENT_DIR_REL / 'state'
LOCAL_DIR_REL = AGENT_DIR_REL / 'local'
RUNS_DIR_REL = STATE_DIR_REL / 'runs'
CLAIMS_DIR_REL = STATE_DIR_REL / 'claims'
HANDOFFS_DIR_REL = STATE_DIR_REL / 'handoffs'
SESSIONS_DIR_REL = AGENT_DIR_REL / 'sessions'
ACTIVE_TASK_POINTER_REL = LOCAL_DIR_REL / 'active-task.json'
# Previous layout: one rewritten JSON per run, committed on branches (see `cli.py migrate-state`).
LEGACY_RUNS_DIR_REL = AGENT_DIR_REL / 'runtime' / 'runs'
STATE_DIR = REPO_ROOT / STATE_DIR_REL
LOCAL_DIR = REPO_ROOT / LOCAL_DIR_REL
RUNS_DIR = REPO_ROOT / RUNS_DIR_REL
CLAIMS_DIR = REPO_ROOT / CLAIMS_DIR_REL
ACTIVE_TASK_POINTER = REPO_ROOT / ACTIVE_TASK_POINTER_REL
ROUTE_CACHE_FILE = LOCAL_DIR / 'route-cache.json'
# Committed paths the runtime writes; native agent writes to them are denied.
PROTECTED_DIRS_REL = (STATE_DIR_REL, LOCAL_DIR_REL)
