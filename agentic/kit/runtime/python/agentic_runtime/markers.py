"""One native coding-agent task per installed kit; explicit crash recovery."""
import json
import os
import tempfile
from pathlib import Path


def reserve(path, db, run_id):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation prevents another CLI task from replacing this marker.
    with path.open('x') as handle:
        json.dump({'db': str(Path(db).resolve()), 'run_id': run_id,
                   'task_id': None, 'status': 'STARTING'}, handle)


def activate(path, db, run_id, task_id):
    path = Path(path)
    fd, temporary = tempfile.mkstemp(prefix='.active-task-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as handle:
            json.dump({'db': str(Path(db).resolve()), 'run_id': run_id,
                       'task_id': task_id}, handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def clear(path, db, run_id, task_id=None):
    path = Path(path)
    if not path.exists():
        return
    marker = json.loads(path.read_text())
    if marker.get('db') != str(Path(db).resolve()) or marker.get('run_id') != run_id:
        return  # Never clear another run's marker.
    if task_id is not None and marker.get('task_id') != task_id:
        return
    path.unlink()
