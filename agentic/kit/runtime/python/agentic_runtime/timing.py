from contextlib import contextmanager
from datetime import datetime, timezone

TERMINAL_EVENTS = {"COMPLETED", "FAILED", "CANCELLED", "INTERRUPTED"}

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


def durations(events):
    """Pair each STARTED timing event with its terminal event and compute elapsed ms. Query-side counterpart to `timed`/store.timing()."""
    started, result = {}, []
    for event in events:
        key = (event["run_id"], event["task"])
        if event["event"] == "STARTED":
            started[key] = event["ts"]
        elif event["event"] in TERMINAL_EVENTS and key in started:
            start_ts = datetime.fromisoformat(started.pop(key))
            end_ts = datetime.fromisoformat(event["ts"])
            result.append({
                "run_id": event["run_id"], "task": event["task"], "event": event["event"],
                "started_at": start_ts.isoformat(), "ended_at": event["ts"],
                "duration_ms": (end_ts - start_ts).total_seconds() * 1000,
                "post_hoc": bool((event.get("metadata") or {}).get("post_hoc")),
            })
    result.extend({"run_id": run_id, "task": task, "event": "PENDING", "started_at": ts, "ended_at": None, "duration_ms": None}
                  for (run_id, task), ts in started.items())
    return result
