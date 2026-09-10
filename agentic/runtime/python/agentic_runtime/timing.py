from contextlib import contextmanager
from datetime import datetime, timezone

def now(): return datetime.now(timezone.utc).isoformat()

@contextmanager
def timed(store, run_id, task):
    start = now(); store.timing(run_id, task, "STARTED", start)
    try:
        yield
        store.timing(run_id, task, "COMPLETED", now())
    except Exception as e:
        store.timing(run_id, task, "FAILED", now(), {"error": str(e)})
        raise
