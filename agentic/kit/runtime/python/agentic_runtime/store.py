import copy
import json
import os
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

from .context import posix_key
from .models import WorkflowRun
from .security import redact_value

LOCK_TIMEOUT_SECONDS = 10.0
_STAMP = '%Y%m%dT%H%M%S%fZ'


def _posix_context(metadata: dict) -> dict:
    """Runs recorded on Windows before paths were normalized keyed context files with '\\'."""
    files = (metadata.get("context") or {}).get("files")
    if not files or not any("\\" in name for name in files):
        return metadata
    context = {**metadata["context"], "files": {posix_key(name): digest for name, digest in files.items()}}
    return {**metadata, "context": context}


def empty_state() -> dict:
    return {"run": None, "checkpoints": [], "approvals": [], "timing_events": [], "audit_events": [], "tool_calls": {}}


def apply_ops(data: dict, ops: List[dict]):
    """Replay one event's operations onto a run's state (also used live)."""
    run_delta = {}
    for op in ops:
        kind = op["op"]
        if kind == "snapshot":
            data.clear()
            data.update(copy.deepcopy(op["state"]))
        elif kind == "run":
            if data.get("run") is None:
                data["run"] = {"metadata": {}}
            data["run"].update(op.get("fields", {}))
            meta = data["run"].setdefault("metadata", {})
            meta.update(copy.deepcopy(op.get("meta", {})))
            for key in op.get("meta_removed", []):
                meta.pop(key, None)
            run_delta = {**op.get("meta", {}), **({"_removed": op["meta_removed"]} if op.get("meta_removed") else {})}
        elif kind == "checkpoint":
            entry = {k: op[k] for k in ("run_id", "stage", "status", "created_at")}
            # A checkpoint beside a run op records that op's metadata delta (not stored twice).
            entry["payload"] = copy.deepcopy(run_delta) if op.get("from_run") else op.get("payload")
            data["checkpoints"].append(entry)
        elif kind in ("approval", "timing", "audit"):
            key = {"approval": "approvals", "timing": "timing_events", "audit": "audit_events"}[kind]
            data[key].append(copy.deepcopy(op["entry"]))
        elif kind == "tool_call":
            data.setdefault("tool_calls", {})[op["key"]] = copy.deepcopy(op["entry"])
        elif kind == "tool_call_update":
            entry = data.setdefault("tool_calls", {}).get(op["key"])
            if entry and (op.get("expected") is None or entry.get("status") == op["expected"]):
                entry["status"] = op["status"]
                if op.get("result") is not None:
                    entry["result"] = copy.deepcopy(op["result"])
        else:
            raise ValueError("Unknown store operation: " + kind)


class RuntimeStore:
    """Governed run state as an append-only event log per run.

    `<store_dir>/<run_id>/events/<stamp>-<id>.json` holds one committed change (a
    transaction's operations); a run's state is the replay of its events in name
    order. Event files are only ever added -- and deleted by compaction of a
    finished run -- never edited, so two machines that both changed state since
    their last `git pull` merge without conflicts. Stamps never go backwards within
    a run (max(now, last + 1us)), so a lagging clock cannot reorder causal history.

    `.lock` (one writer per run on one machine) and `.cache.json` (replay cache)
    live beside `events/` and are never committed. Across machines, a run is held
    by one clone through its claim (claims.py).
    """

    def __init__(self, store_dir: str):
        self.store_dir = Path(store_dir)
        self.store_dir.mkdir(parents=True, exist_ok=True)
        self._tx_depth = 0
        self._tx_data: Dict[str, dict] = {}
        self._tx_ops: Dict[str, List[dict]] = {}

    # -- paths / locking -------------------------------------------------

    def _run_dir(self, run_id: str) -> Path:
        return self.store_dir / run_id

    def _events_dir(self, run_id: str) -> Path:
        return self._run_dir(run_id) / "events"

    def _lock_path(self, run_id: str) -> Path:
        return self._run_dir(run_id) / ".lock"

    def _acquire_lock(self, run_id: str):
        self._run_dir(run_id).mkdir(parents=True, exist_ok=True)
        lock_path = self._lock_path(run_id)
        deadline = time.monotonic() + LOCK_TIMEOUT_SECONDS
        while True:
            try:
                os.close(os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY))
                return
            except FileExistsError:
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"Could not acquire store lock for run {run_id}")
                time.sleep(0.05)

    def _release_lock(self, run_id: str):
        try:
            self._lock_path(run_id).unlink()
        except FileNotFoundError:
            pass

    # On disk `metadata.repo` is relative to store_dir, so a committed store resolves
    # to the right checkout on any machine; in memory it is absolute. Stored paths
    # always use '/', so a run written on Windows resolves on macOS/Linux.
    def _to_disk(self, metadata: dict) -> dict:
        repo = metadata.get("repo")
        if not repo or not Path(repo).is_absolute():
            return metadata
        return {**metadata, "repo": Path(os.path.relpath(Path(repo).resolve(), self.store_dir.resolve())).as_posix()}

    def _from_disk(self, metadata: dict) -> dict:
        metadata = _posix_context(metadata)
        repo = metadata.get("repo")
        if not repo or Path(repo).is_absolute():
            return metadata
        return {**metadata, "repo": str((self.store_dir / posix_key(repo)).resolve())}

    # -- event log ----------------------------------------------------------

    def _event_names(self, run_id: str) -> List[str]:
        directory = self._events_dir(run_id)
        return sorted(p.name for p in directory.glob("*.json")) if directory.is_dir() else []

    def _read_event(self, run_id: str, name: str) -> List[dict]:
        return json.loads((self._events_dir(run_id) / name).read_text(encoding="utf-8"))["ops"]

    def _load(self, run_id: str) -> dict:
        names = self._event_names(run_id)
        if not names:
            return empty_state()
        cache_path = self._run_dir(run_id) / ".cache.json"
        data, applied = empty_state(), []
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            if names[:len(cached["names"])] == cached["names"]:
                data, applied = cached["state"], cached["names"]
        except (OSError, ValueError, KeyError, TypeError):
            pass
        seen = list(applied)
        for name in names[len(applied):]:
            ops = self._read_event(run_id, name)
            apply_ops(data, ops)
            covers = ops[0].get("covers") if ops and ops[0]["op"] == "snapshot" else None
            if covers is not None:
                # A snapshot replaces only the events it was built from. An event merged in
                # from another clone with an older stamp sorts before it but is not covered:
                # replay it on top instead of losing it.
                covered = set(covers)
                for earlier in seen:
                    if earlier not in covered:
                        apply_ops(data, self._read_event(run_id, earlier))
            seen.append(name)
        if len(names) != len(applied):
            self._write_cache(run_id, names, data)
        return data

    def _write_cache(self, run_id, names, data):
        cache_path = self._run_dir(run_id) / ".cache.json"
        try:
            tmp = cache_path.with_name(f".cache.{uuid.uuid4().hex}.tmp")
            tmp.write_text(json.dumps({"names": names, "state": data}), encoding="utf-8", newline="\n")
            os.replace(tmp, cache_path)
        except OSError:
            pass  # a cache, never required

    def _next_name(self, run_id: str) -> str:
        now = datetime.now(timezone.utc)
        names = self._event_names(run_id)
        if names:
            try:
                last = datetime.strptime(names[-1].split("-", 1)[0], _STAMP).replace(tzinfo=timezone.utc)
                now = max(now, last + timedelta(microseconds=1))
            except ValueError:
                pass
        return f"{now.strftime(_STAMP)}-{uuid.uuid4().hex[:8]}.json"

    def _write_event(self, run_id: str, ops: List[dict]):
        if not ops:
            return
        directory = self._events_dir(run_id)
        directory.mkdir(parents=True, exist_ok=True)
        name = self._next_name(run_id)
        tmp = directory / f".{name}.tmp"
        tmp.write_text(json.dumps({"ops": ops}, sort_keys=True, separators=(",", ":")) + "\n",
                       encoding="utf-8", newline="\n")
        os.replace(tmp, directory / name)

    def _mutate(self, run_id: str, ops: List[dict]):
        """Apply operations to a run: buffered in a transaction, else one event now."""
        if self._tx_depth:
            if run_id not in self._tx_data:
                self._acquire_lock(run_id)
                self._tx_data[run_id] = self._load(run_id)
                self._tx_ops[run_id] = []
            apply_ops(self._tx_data[run_id], ops)
            self._tx_ops[run_id].extend(ops)
        else:
            self._acquire_lock(run_id)
            try:
                self._write_event(run_id, ops)
            finally:
                self._release_lock(run_id)

    def _view(self, run_id: str) -> dict:
        if self._tx_depth and run_id in self._tx_data:
            return self._tx_data[run_id]
        return self._load(run_id)

    # -- runs --------------------------------------------------------------

    def _run_op(self, run: WorkflowRun) -> dict:
        existing = self._view(run.run_id).get("run")
        metadata = self._to_disk(run.metadata)
        if not existing:
            fields = {"run_id": run.run_id, "project": run.project, "work_type": run.work_type,
                      "title": run.title, "stage": run.stage, "status": run.status,
                      "dry_run": run.dry_run, "created_at": run.created_at, "updated_at": run.updated_at}
            return {"op": "run", "fields": fields, "meta": metadata}
        fields = {k: v for k, v in {"stage": run.stage, "status": run.status, "dry_run": run.dry_run,
                                     "updated_at": run.updated_at}.items() if existing.get(k) != v}
        previous = existing.get("metadata") or {}
        op = {"op": "run", "fields": fields,
              "meta": {k: v for k, v in metadata.items() if k not in previous or previous[k] != v}}
        removed = sorted(set(previous) - set(metadata))
        if removed:
            op["meta_removed"] = removed
        return op

    def save_run(self, run: WorkflowRun):
        self._mutate(run.run_id, [self._run_op(run)])

    def get_run(self, run_id: str) -> Optional[WorkflowRun]:
        r = self._view(run_id).get("run")
        if not r:
            return None
        # Deep copy: inside a transaction the view is the live buffer, and a nested
        # in-place edit on shared dicts would diff as "unchanged" and never be written.
        return WorkflowRun(run_id=r['run_id'], project=r['project'], work_type=r['work_type'], title=r['title'],
                           stage=r['stage'], status=r['status'], dry_run=bool(r['dry_run']),
                           created_at=r['created_at'], updated_at=r['updated_at'],
                           metadata=self._from_disk(copy.deepcopy(r['metadata'])))

    def ledger(self, run_id: str) -> dict:
        """The run's full record: run, checkpoints, approvals, timing/audit events, tool calls."""
        data = self._view(run_id)
        if data.get("run"):
            data = {**data, "run": {**data["run"], "metadata": self._from_disk(data["run"]["metadata"])}}
        return data

    def run_ids(self) -> List[str]:
        return sorted(p.name for p in self.store_dir.iterdir() if (p / "events").is_dir())

    def list_runs(self) -> List[Dict]:
        results = []
        for run_id in self.run_ids():
            try:
                r = self._load(run_id).get("run")
            except (OSError, ValueError, KeyError, TypeError):
                continue
            if r:
                results.append({**r, "metadata": self._from_disk(r["metadata"])})
        results.sort(key=lambda r: r["created_at"], reverse=True)
        return results

    def import_state(self, run_id: str, state: dict):
        """Write a whole run state as one snapshot event (layout migration)."""
        self._acquire_lock(run_id)
        try:
            self._write_event(run_id, [{"op": "snapshot", "state": state, "covers": self._event_names(run_id)}])
        finally:
            self._release_lock(run_id)

    # -- checkpoints / approvals / timing / audit --------------------------

    def checkpoint(self, run_id, stage, status, payload, ts):
        self._mutate(run_id, [{"op": "checkpoint", "run_id": run_id, "stage": stage, "status": status,
                               "payload": self._to_disk(payload) if isinstance(payload, dict) else payload,
                               "created_at": ts}])

    def approval(self, run_id, gate, approver, decision, comment, ts, scope_revision=-1):
        if not self.get_run(run_id):
            raise ValueError("Unknown run")
        if gate not in {"technical", "release", "uat"} or decision not in {"APPROVED", "REJECTED", "REVOKED"} or not approver.strip():
            raise ValueError("Invalid approval record")
        self._mutate(run_id, [{"op": "approval", "entry": {
            "run_id": run_id, "gate": gate, "approver": approver, "decision": decision,
            "comment": comment, "created_at": ts, "scope_revision": scope_revision}}])

    def has_approval(self, run_id, gate, scope_revision=None) -> bool:
        if scope_revision is None:
            run = self.get_run(run_id)
            scope_revision = run.metadata.get("scope_revision", 0) if run else 0
        matches = [a for a in self._view(run_id).get("approvals", []) if a["gate"] == gate and a["scope_revision"] == scope_revision]
        return bool(matches and matches[-1]["decision"] == "APPROVED")

    def timing(self, run_id, task, event, ts, metadata=None):
        self._mutate(run_id, [{"op": "timing", "entry": {
            "run_id": run_id, "task": task, "event": event, "ts": ts, "metadata": redact_value(metadata or {})}}])

    def query_timing(self, run_id=None, task=None) -> List[Dict]:
        if run_id is not None:
            events = self._view(run_id).get("timing_events", [])
        else:
            events = []
            for other in self.run_ids():
                try:
                    events.extend(self._load(other).get("timing_events", []))
                except (OSError, ValueError):
                    continue
            events.sort(key=lambda e: e["ts"])
        if task is not None:
            events = [e for e in events if e["task"] == task]
        return events

    def audit(self, run_id, event, payload, ts):
        self._mutate(run_id, [{"op": "audit", "entry": {
            "run_id": run_id, "event": event, "payload": redact_value(payload), "created_at": ts}}])

    # -- tool-call idempotency cache ---------------------------------------

    def get_tool_call(self, run_id, call_key) -> Optional[Dict]:
        return self._view(run_id).get("tool_calls", {}).get(call_key)

    def record_tool_call(self, run_id, call_key, request_hash, status):
        self._mutate(run_id, [{"op": "tool_call", "key": call_key,
                               "entry": {"request_hash": request_hash, "status": status, "result": None}}])

    def update_tool_call_status(self, run_id, call_key, status, result=None, expected_status=None):
        self._mutate(run_id, [{"op": "tool_call_update", "key": call_key, "status": status,
                               "result": result, "expected": expected_status}])

    # -- transactions --------------------------------------------------------

    @contextmanager
    def transaction(self):
        """Operations inside commit together as one event file per touched run."""
        if self._tx_depth:
            raise RuntimeError("Nested transactions are unsupported")
        self._tx_depth = 1
        self._tx_data, self._tx_ops = {}, {}
        try:
            yield
        except BaseException:
            raise
        else:
            for run_id, ops in self._tx_ops.items():
                self._write_event(run_id, ops)
        finally:
            for run_id in self._tx_data:
                self._release_lock(run_id)
            self._tx_depth = 0
            self._tx_data, self._tx_ops = {}, {}

    def compact(self, run_id):
        """Shrink a terminal run: one snapshot event replaces its history. Checkpoints
        exist to resume an open run, and tool-call results only back idempotent replay,
        which a terminal run can no longer do. Keeps the first and last checkpoint,
        every approval/timing/audit event, and each tool call's request hash and status."""
        def strip(data):
            data = copy.deepcopy(data)
            checkpoints = data.get("checkpoints", [])
            if len(checkpoints) > 2:
                data["checkpoints"] = [checkpoints[0], checkpoints[-1]]
                data["compacted_checkpoints"] = data.get("compacted_checkpoints", 0) + len(checkpoints) - 2
            for call in data.get("tool_calls", {}).values():
                call.pop("result", None)
            return data
        if self._tx_depth:
            raise RuntimeError("compact runs after the transaction that finished the run")
        self._acquire_lock(run_id)
        try:
            old = self._event_names(run_id)
            self._write_event(run_id, [{"op": "snapshot", "state": strip(self._load(run_id)), "covers": old}])
            for name in old:
                (self._events_dir(run_id) / name).unlink(missing_ok=True)
        finally:
            self._release_lock(run_id)

    def save_checkpoint(self, run, event, payload=None):
        # Call inside transaction() so state, checkpoint, and audit commit together.
        # The checkpoint payload is the run op's metadata delta (the first one is
        # complete), recorded once, not a full metadata copy per guarded tool call.
        if not self._tx_depth:
            raise RuntimeError("save_checkpoint requires a transaction")
        self._mutate(run.run_id, [
            self._run_op(run),
            {"op": "checkpoint", "run_id": run.run_id, "stage": run.stage, "status": run.status,
             "created_at": run.updated_at, "from_run": True},
            {"op": "audit", "entry": {"run_id": run.run_id, "event": event, "payload": redact_value(payload or {}),
                                      "created_at": run.updated_at}},
        ])
