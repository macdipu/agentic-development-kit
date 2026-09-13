import hashlib
from pathlib import Path

def file_hash(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def snapshot(repo, paths):
    root = Path(repo).resolve()
    if not paths:
        raise ValueError("Supply explicit context/source files for the affected scope")
    hashes = {}
    for name in paths:
        path = (root / name).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError("Context path must be an existing file inside the project: " + str(name))
        hashes[str(path.relative_to(root))] = file_hash(str(path))
    return {"files": hashes}


def snapshot_state(repo, recorded):
    if not isinstance(recorded, dict) or not recorded.get("files"):
        return "MISSING"
    try:
        current = snapshot(repo, list(recorded["files"]))
    except (ValueError, OSError):
        return "STALE"
    return "AVAILABLE" if recorded["files"] == current["files"] else "STALE"
