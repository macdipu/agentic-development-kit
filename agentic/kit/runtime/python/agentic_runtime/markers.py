"""One native coding-agent task per installed kit; explicit crash recovery."""
import json
import os
import tempfile
from pathlib import Path


def _relative_store_dir(path, store_dir):
    # Relative to the pointer's folder, so a pointer committed on one machine resolves on another.
    return os.path.relpath(Path(store_dir).resolve(), Path(path).resolve().parent)


def store_dir_of(path, pointer):
    """Absolute store directory a pointer names (relative entries resolve against the pointer's folder)."""
    return (Path(path).resolve().parent / pointer['store_dir']).resolve()


def reserve(path, store_dir, run_id):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation prevents another CLI task from replacing this marker.
    with path.open('x') as handle:
        json.dump({'store_dir': _relative_store_dir(path, store_dir), 'run_id': run_id,
                   'task_id': None, 'status': 'STARTING'}, handle)


def activate(path, store_dir, run_id, task_id):
    path = Path(path)
    fd, temporary = tempfile.mkstemp(prefix='.active-task-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as handle:
            json.dump({'store_dir': _relative_store_dir(path, store_dir), 'run_id': run_id,
                       'task_id': task_id}, handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def clear(path, store_dir, run_id, task_id=None):
    path = Path(path)
    if not path.exists():
        return
    marker = json.loads(path.read_text())
    if 'store_dir' not in marker or store_dir_of(path, marker) != Path(store_dir).resolve() or marker.get('run_id') != run_id:
        return  # Never clear another run's marker.
    if task_id is not None and marker.get('task_id') != task_id:
        return
    path.unlink()
