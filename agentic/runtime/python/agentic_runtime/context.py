import hashlib, subprocess
from pathlib import Path
from typing import Dict, Iterable

def git_revision(repo: str) -> str:
    try:
        return subprocess.check_output(["git", "-C", repo, "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL, timeout=10).strip()
    except (OSError, subprocess.SubprocessError):
        return "UNKNOWN"

def file_hash(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def context_state(recorded_revision: str, current_revision: str) -> str:
    if not recorded_revision or recorded_revision == "UNKNOWN":
        return "MISSING"
    if recorded_revision == current_revision:
        return "AVAILABLE"
    return "STALE"


def snapshot(repo, paths, include_revision=True):
    root = Path(repo).resolve()
    if not paths:
        raise ValueError("Supply explicit context/source files for the affected scope")
    hashes = {}
    for name in paths:
        path = (root / name).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError("Context path must be an existing file inside the project: " + str(name))
        hashes[str(path.relative_to(root))] = file_hash(str(path))
    return {"revision": git_revision(str(root)) if include_revision else None, "files": hashes}


def snapshot_state(repo, recorded):
    if not isinstance(recorded, dict) or not recorded.get("files"):
        return "MISSING"
    try:
        current = snapshot(repo, list(recorded["files"]), include_revision=False)
    except (ValueError, OSError):
        return "STALE"
    return "AVAILABLE" if recorded["files"] == current["files"] else "STALE"
