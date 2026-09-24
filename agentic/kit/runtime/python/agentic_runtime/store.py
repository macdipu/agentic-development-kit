import json, os, time
from contextlib import contextmanager
from .security import redact_value
from pathlib import Path
from typing import Dict, List, Optional
from .models import WorkflowRun

LOCK_TIMEOUT_SECONDS = 10.0


class RuntimeStore:
    """Governed run state as one JSON file per run under `store_dir`.

    Git-tracked (under .agent/runtime/runs/): each run's runs/checkpoints/approvals/timing/audit/
    tool-call records live in `<store_dir>/<run_id>.json`, written atomically via
    write-temp+os.replace. An exclusive-create lock file guards concurrent
    writers on one machine; it does not coordinate across machines/clones -- finish
    and push on one machine before resuming on another. Lock/temp files stay
    gitignored.

    No in-memory cache: every non-transactional call (`get_run`, `has_approval`,
    `query_timing`) re-reads and re-parses its run's file from disk. Fine at this
    kit's scale; a caller doing many such calls in a tight loop pays a real disk
    round trip each time, unlike a kept-open database connection.
    """

    def __init__(self, store_dir: str):
        self.store_dir = Path(store_dir)
        self.store_dir.mkdir(parents=True, exist_ok=True)
        self._tx_depth = 0
        self._tx_data: Dict[str, dict] = {}

    # -- paths / locking -------------------------------------------------

    def _run_path(self, run_id: str) -> Path:
        return self.store_dir / f"{run_id}.json"

    def _lock_path(self, run_id: str) -> Path:
        return self.store_dir / f"{run_id}.lock"

    def _acquire_lock(self, run_id: str):
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

    # On disk `metadata.repo` is relative to store_dir, so a store committed to git
    # resolves to the right checkout on any machine; in memory it is absolute.
    def _to_disk(self, metadata: dict) -> dict:
        repo = metadata.get("repo")
        if not repo or not Path(repo).is_absolute():
            return metadata
        return {**metadata, "repo": os.path.relpath(Path(repo).resolve(), self.store_dir.resolve())}

    def _from_disk(self, metadata: dict) -> dict:
        repo = metadata.get("repo")
        if not repo or Path(repo).is_absolute():
            return metadata
        return {**metadata, "repo": str((self.store_dir / repo).resolve())}

    def _empty(self) -> dict:
        return {"run": None, "checkpoints": [], "approvals": [], "timing_events": [], "audit_events": [], "tool_calls": {}}

    def _load(self, run_id: str) -> dict:
        path = self._run_path(run_id)
        if not path.exists():
            return self._empty()
        return json.loads(path.read_text())

    def _save(self, run_id: str, data: dict):
        path = self._run_path(run_id)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2))
        os.replace(tmp, path)

    def _mutate(self, run_id: str, fn):
        """Apply fn(data) to a run's state, buffered inside a transaction or committed immediately."""
        if self._tx_depth:
            if run_id not in self._tx_data:
                self._acquire_lock(run_id)
                self._tx_data[run_id] = self._load(run_id)
            fn(self._tx_data[run_id])
        else:
            self._acquire_lock(run_id)
            try:
                data = self._load(run_id)
                fn(data)
                self._save(run_id, data)
            finally:
                self._release_lock(run_id)

    def _view(self, run_id: str) -> dict:
        if self._tx_depth and run_id in self._tx_data:
            return self._tx_data[run_id]
        return self._load(run_id)

    # -- runs --------------------------------------------------------------

    def save_run(self, run: WorkflowRun):
        def _fn(data):
            existing = data.get("run")
            if existing:
                existing.update({
                    "stage": run.stage, "status": run.status, "dry_run": run.dry_run,
                    "updated_at": run.updated_at, "metadata": self._to_disk(run.metadata),
                })
            else:
                data["run"] = {
                    "run_id": run.run_id, "project": run.project, "work_type": run.work_type,
                    "title": run.title, "stage": run.stage, "status": run.status,
                    "dry_run": run.dry_run, "created_at": run.created_at,
                    "updated_at": run.updated_at, "metadata": self._to_disk(run.metadata),
                }
        self._mutate(run.run_id, _fn)

    def get_run(self, run_id: str) -> Optional[WorkflowRun]:
        r = self._view(run_id).get("run")
        if not r:
            return None
        return WorkflowRun(run_id=r['run_id'], project=r['project'], work_type=r['work_type'], title=r['title'],
                           stage=r['stage'], status=r['status'], dry_run=bool(r['dry_run']),
                           created_at=r['created_at'], updated_at=r['updated_at'], metadata=self._from_disk(r['metadata']))

    def ledger(self, run_id: str) -> dict:
        """The run's full record: run, checkpoints, approvals, timing/audit events, tool calls."""
        data = self._view(run_id)
        if data.get("run"):
            data = {**data, "run": {**data["run"], "metadata": self._from_disk(data["run"]["metadata"])}}
        return data

    def list_runs(self) -> List[Dict]:
        results = []
        for path in self.store_dir.glob("*.json"):
            try:
                data = json.loads(path.read_text())
            except (OSError, ValueError):
                continue
            r = data.get("run")
            if r:
                results.append({**r, "metadata": self._from_disk(r["metadata"])})
        results.sort(key=lambda r: r["created_at"], reverse=True)
        return results

    # -- checkpoints / approvals / timing / audit --------------------------

    def checkpoint(self, run_id, stage, status, payload, ts):
        def _fn(data):
            data["checkpoints"].append({"run_id": run_id, "stage": stage, "status": status,
                                        "payload": self._to_disk(payload) if isinstance(payload, dict) else payload,
                                        "created_at": ts})
        self._mutate(run_id, _fn)

    def approval(self, run_id, gate, approver, decision, comment, ts, scope_revision=-1):
        if not self.get_run(run_id):
            raise ValueError("Unknown run")
        if gate not in {"technical", "release", "uat"} or decision not in {"APPROVED", "REJECTED", "REVOKED"} or not approver.strip():
            raise ValueError("Invalid approval record")
        def _fn(data):
            data["approvals"].append({"run_id": run_id, "gate": gate, "approver": approver, "decision": decision,
                                       "comment": comment, "created_at": ts, "scope_revision": scope_revision})
        self._mutate(run_id, _fn)

    def has_approval(self, run_id, gate, scope_revision=None) -> bool:
        if scope_revision is None:
            run = self.get_run(run_id)
            scope_revision = run.metadata.get("scope_revision", 0) if run else 0
        matches = [a for a in self._view(run_id).get("approvals", []) if a["gate"] == gate and a["scope_revision"] == scope_revision]
        return bool(matches and matches[-1]["decision"] == "APPROVED")

    def timing(self, run_id, task, event, ts, metadata=None):
        def _fn(data):
            data["timing_events"].append({"run_id": run_id, "task": task, "event": event, "ts": ts,
                                           "metadata": redact_value(metadata or {})})
        self._mutate(run_id, _fn)

    def query_timing(self, run_id=None, task=None) -> List[Dict]:
        if run_id is not None:
            events = self._view(run_id).get("timing_events", [])
        else:
            # No global insertion order across per-run files; sort merged events by ts instead.
            events = []
            for path in self.store_dir.glob("*.json"):
                try:
                    data = json.loads(path.read_text())
                except (OSError, ValueError):
                    continue
                events.extend(data.get("timing_events", []))
            events.sort(key=lambda e: e["ts"])
        if task is not None:
            events = [e for e in events if e["task"] == task]
        return events

    def audit(self, run_id, event, payload, ts):
        def _fn(data):
            data["audit_events"].append({"run_id": run_id, "event": event, "payload": redact_value(payload), "created_at": ts})
        self._mutate(run_id, _fn)

    # -- tool-call idempotency cache ---------------------------------------

    def get_tool_call(self, run_id, call_key) -> Optional[Dict]:
        return self._view(run_id).get("tool_calls", {}).get(call_key)

    def record_tool_call(self, run_id, call_key, request_hash, status):
        def _fn(data):
            data.setdefault("tool_calls", {})[call_key] = {"request_hash": request_hash, "status": status, "result": None}
        self._mutate(run_id, _fn)

    def update_tool_call_status(self, run_id, call_key, status, result=None, expected_status=None):
        def _fn(data):
            entry = data.setdefault("tool_calls", {}).get(call_key)
            if not entry or (expected_status is not None and entry.get("status") != expected_status):
                return
            entry["status"] = status
            if result is not None:
                entry["result"] = result
        self._mutate(run_id, _fn)

    # -- transactions --------------------------------------------------------

    @contextmanager
    def transaction(self):
        if self._tx_depth:
            raise RuntimeError("Nested transactions are unsupported")
        self._tx_depth = 1
        self._tx_data = {}
        try:
            yield
        except BaseException:
            raise
        else:
            for run_id, data in self._tx_data.items():
                self._save(run_id, data)
        finally:
            for run_id in self._tx_data:
                self._release_lock(run_id)
            self._tx_depth = 0
            self._tx_data = {}

    def save_checkpoint(self, run, event, payload=None):
        # Call inside transaction() so state, checkpoint, and audit commit together.
        if not self._tx_depth:
            raise RuntimeError("save_checkpoint requires a transaction")
        self.save_run(run)
        self.checkpoint(run.run_id, run.stage, run.status, run.metadata, run.updated_at)
        self.audit(run.run_id, event, payload or {}, run.updated_at)
