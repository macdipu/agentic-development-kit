"""Routing-decision cache.

A fresh session re-reads AGENTS.md's matched `workflows/*.md`, a persona
`AGENT.md`, and the relevant `SKILL.md` files in full every time, even for a
work item whose (work_type, project_type, module) triple was already routed
in a prior session -- none of that content changes per-run. This cache lets a
session skip that re-read on a hit and reuse the previously recorded routing
decision (route, matched docs) instead.

Local-only, gitignored, one JSON file (agentic/data/runtime/state/route-cache.json),
written atomically (temp + os.replace) under a single exclusive-create lock --
same convention as RuntimeStore, just one file instead of one per run.

Invalidation is a single aggregate content hash (`kit_version`) over every
routing-relevant doc: the repo's AGENTS.md, every `kit/workflows/*.md`, every
persona `AGENT.md`, and every `SKILL.md`. Editing any one of them changes the
hash and invalidates every cached entry at once -- no per-file tracking, no
manual invalidation step, no risk of serving a decision made under stale docs.
"""
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Optional

LOCK_TIMEOUT_SECONDS = 10.0
PROJECT_TYPES = ("greenfield", "brownfield")


def cache_key(work_type: str, project_type: str, module: str) -> str:
    if project_type not in PROJECT_TYPES:
        raise ValueError(f"project_type must be one of {PROJECT_TYPES}, got {project_type!r}")
    if not work_type.strip() or not module.strip():
        raise ValueError("work_type and module are required")
    return f"{work_type}:{project_type}:{module}"


def compute_kit_version(repo_root, kit_dir) -> str:
    """Aggregate sha256 over every routing-relevant meta-doc's path + bytes."""
    repo_root, kit_dir = Path(repo_root), Path(kit_dir)
    candidates = [repo_root / "AGENTS.md"]
    for pattern in ("workflows/*.md", "agents/**/AGENT.md", "skills/**/SKILL.md"):
        candidates.extend(kit_dir.glob(pattern))
    digest = hashlib.sha256()
    for path in sorted({p for p in candidates if p.is_file()}):
        try:
            relative = path.relative_to(repo_root)
        except ValueError:
            relative = path
        digest.update(str(relative).encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


class RoutingCache:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _lock_path(self) -> Path:
        return self.path.with_suffix(".lock")

    def _acquire(self):
        deadline = time.monotonic() + LOCK_TIMEOUT_SECONDS
        while True:
            try:
                os.close(os.open(str(self._lock_path()), os.O_CREAT | os.O_EXCL | os.O_WRONLY))
                return
            except FileExistsError:
                if time.monotonic() >= deadline:
                    raise TimeoutError("Could not acquire route-cache lock")
                time.sleep(0.05)

    def _release(self):
        try:
            self._lock_path().unlink()
        except FileNotFoundError:
            pass

    def _load(self) -> dict:
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text())

    def _save(self, data: dict):
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2, sort_keys=True))
        os.replace(tmp, self.path)

    def get(self, key: str, kit_version: str) -> Optional[dict]:
        entry = self._load().get(key)
        if not entry or entry.get("kit_version") != kit_version:
            return None
        return entry

    def put(self, key: str, kit_version: str, decision: dict, ts: str) -> dict:
        if not isinstance(decision, dict):
            raise ValueError("decision must be a JSON object")
        entry = {"kit_version": kit_version, "cached_at": ts, "decision": decision}
        self._acquire()
        try:
            data = self._load()
            data[key] = entry
            self._save(data)
        finally:
            self._release()
        return entry

    def clear(self):
        self._acquire()
        try:
            self._save({})
        finally:
            self._release()
