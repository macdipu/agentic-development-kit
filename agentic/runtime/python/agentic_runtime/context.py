import hashlib, subprocess
from pathlib import Path
from typing import Dict, Iterable

def git_revision(repo: str) -> str:
    try:
        return subprocess.check_output(["git", "-C", repo, "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        return "UNKNOWN"

def file_hash(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def context_state(recorded_revision: str, current_revision: str) -> str:
    if not recorded_revision:
        return "MISSING"
    if recorded_revision == current_revision:
        return "AVAILABLE"
    return "STALE"
