import json, sqlite3
from contextlib import contextmanager
from .security import redact_value
from pathlib import Path
from typing import Dict, List, Optional
from .models import WorkflowRun

SCHEMA = """
CREATE TABLE IF NOT EXISTS workflow_runs (
  run_id TEXT PRIMARY KEY,
  project TEXT NOT NULL,
  work_type TEXT NOT NULL,
  title TEXT NOT NULL,
  stage TEXT NOT NULL,
  status TEXT NOT NULL,
  dry_run INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS checkpoints (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL,
  stage TEXT NOT NULL,
  status TEXT NOT NULL,
  payload_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS approvals (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL,
  gate TEXT NOT NULL,
  approver TEXT NOT NULL,
  decision TEXT NOT NULL,
  comment TEXT,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS timing_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL,
  task TEXT NOT NULL,
  event TEXT NOT NULL,
  ts TEXT NOT NULL,
  metadata_json TEXT NOT NULL DEFAULT '{}'
);
"""

class RuntimeStore:
    def __init__(self, db_path: str):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        columns = {row[1] for row in self.conn.execute("PRAGMA table_info(approvals)")}
        if "scope_revision" not in columns:
            self.conn.execute("ALTER TABLE approvals ADD COLUMN scope_revision INTEGER NOT NULL DEFAULT -1")
        self.conn.executescript("""
        CREATE TABLE IF NOT EXISTS audit_events (
          id INTEGER PRIMARY KEY, run_id TEXT NOT NULL, event TEXT NOT NULL,
          payload_json TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS tool_calls (
          run_id TEXT NOT NULL, call_key TEXT NOT NULL, request_hash TEXT NOT NULL,
          status TEXT NOT NULL, result_json TEXT, PRIMARY KEY(run_id, call_key)
        );
        """)
        self.conn.commit()
        self._transaction_depth = 0

    def save_run(self, run: WorkflowRun):
        self.conn.execute("""
        INSERT INTO workflow_runs(run_id,project,work_type,title,stage,status,dry_run,created_at,updated_at,metadata_json)
        VALUES(?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(run_id) DO UPDATE SET stage=excluded.stage,status=excluded.status,dry_run=excluded.dry_run,updated_at=excluded.updated_at,metadata_json=excluded.metadata_json
        """, (run.run_id,run.project,run.work_type,run.title,run.stage,run.status,int(run.dry_run),run.created_at,run.updated_at,json.dumps(run.metadata)))
        self._commit()

    def get_run(self, run_id: str) -> Optional[WorkflowRun]:
        row = self.conn.execute("SELECT * FROM workflow_runs WHERE run_id=?", (run_id,)).fetchone()
        if not row: return None
        return WorkflowRun(run_id=row['run_id'], project=row['project'], work_type=row['work_type'], title=row['title'], stage=row['stage'], status=row['status'], dry_run=bool(row['dry_run']), created_at=row['created_at'], updated_at=row['updated_at'], metadata=json.loads(row['metadata_json']))

    def list_runs(self) -> List[Dict]:
        rows = self.conn.execute("SELECT * FROM workflow_runs ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]

    def checkpoint(self, run_id, stage, status, payload, ts):
        self.conn.execute("INSERT INTO checkpoints(run_id,stage,status,payload_json,created_at) VALUES(?,?,?,?,?)", (run_id,stage,status,json.dumps(payload),ts)); self._commit()

    def approval(self, run_id, gate, approver, decision, comment, ts, scope_revision=-1):
        if not self.get_run(run_id):
            raise ValueError("Unknown run")
        if gate not in {"technical", "release", "uat"} or decision not in {"APPROVED", "REJECTED", "REVOKED"} or not approver.strip():
            raise ValueError("Invalid approval record")
        self.conn.execute("INSERT INTO approvals(run_id,gate,approver,decision,comment,created_at,scope_revision) VALUES(?,?,?,?,?,?,?)", (run_id,gate,approver,decision,comment,ts,scope_revision))
        self._commit()

    def has_approval(self, run_id, gate, scope_revision=None) -> bool:
        if scope_revision is None:
            run = self.get_run(run_id)
            scope_revision = run.metadata.get("scope_revision", 0) if run else 0
        row = self.conn.execute("SELECT decision FROM approvals WHERE run_id=? AND gate=? AND scope_revision=? ORDER BY id DESC LIMIT 1", (run_id,gate,scope_revision)).fetchone()
        return bool(row and row['decision'] == 'APPROVED')

    def timing(self, run_id, task, event, ts, metadata=None):
        self.conn.execute("INSERT INTO timing_events(run_id,task,event,ts,metadata_json) VALUES(?,?,?,?,?)", (run_id,task,event,ts,json.dumps(redact_value(metadata or {})))); self._commit()

    def _commit(self):
        if self._transaction_depth == 0:
            self.conn.commit()

    @contextmanager
    def transaction(self):
        if self._transaction_depth:
            raise RuntimeError("Nested transactions are unsupported")
        self.conn.execute("BEGIN IMMEDIATE")
        self._transaction_depth = 1
        try:
            yield
            self.conn.commit()
        except BaseException:
            self.conn.rollback()
            raise
        finally:
            self._transaction_depth = 0

    def save_checkpoint(self, run, event, payload=None):
        # Call inside transaction() so state, checkpoint, and audit commit together.
        if not self._transaction_depth:
            raise RuntimeError("save_checkpoint requires a transaction")
        self.save_run(run)
        self.checkpoint(run.run_id, run.stage, run.status, run.metadata, run.updated_at)
        self.audit(run.run_id, event, payload or {}, run.updated_at)

    def audit(self, run_id, event, payload, ts):
        self.conn.execute("INSERT INTO audit_events(run_id,event,payload_json,created_at) VALUES(?,?,?,?)", (run_id,event,json.dumps(redact_value(payload)),ts))
        self._commit()
