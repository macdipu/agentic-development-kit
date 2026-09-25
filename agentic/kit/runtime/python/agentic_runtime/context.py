import hashlib
from pathlib import Path


def normalized_bytes(data: bytes) -> bytes:
    """Text content with CRLF folded to LF, so a Windows (autocrlf) checkout and a
    macOS/Linux checkout of the same commit hash identically. Binary content (any
    NUL byte) is hashed as-is."""
    return data if b"\0" in data else data.replace(b"\r\n", b"\n")


def file_hash(path: str) -> str:
    return hashlib.sha256(normalized_bytes(Path(path).read_bytes())).hexdigest()


def posix_key(name) -> str:
    """Repo-relative path in '/' form: stored keys must match on every OS."""
    return str(name).replace("\\", "/")


def snapshot(repo, paths):
    root = Path(repo).resolve()
    if not paths:
        raise ValueError("Supply explicit context/source files for the affected scope")
    hashes = {}
    for name in paths:
        path = (root / posix_key(name)).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError("Context path must be an existing file inside the project: " + str(name))
        hashes[path.relative_to(root).as_posix()] = file_hash(str(path))
    return {"files": hashes}


def snapshot_state(repo, recorded):
    if not isinstance(recorded, dict) or not recorded.get("files"):
        return "MISSING"
    files = {posix_key(name): digest for name, digest in recorded["files"].items()}
    try:
        current = snapshot(repo, list(files))
    except (ValueError, OSError):
        return "STALE"
    return "AVAILABLE" if files == current["files"] else "STALE"
