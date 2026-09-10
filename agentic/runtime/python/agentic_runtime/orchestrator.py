import uuid
from datetime import datetime, timezone
from .models import WorkflowRun
from .policy import evaluate

def now(): return datetime.now(timezone.utc).isoformat()

class Orchestrator:
    def __init__(self, store): self.store = store
    def start(self, project, work_type, title, dry_run=False):
        ts = now()
        run = WorkflowRun(run_id="RUN-"+uuid.uuid4().hex[:10].upper(), project=project, work_type=work_type, title=title, status="RUNNING", dry_run=dry_run, created_at=ts, updated_at=ts)
        self.store.save_run(run); self.store.checkpoint(run.run_id, run.stage, run.status, {}, ts)
        return run
    def transition(self, run_id, next_stage):
        run = self.store.get_run(run_id)
        if not run: raise ValueError("Unknown run")
        approvals = {"technical": self.store.has_approval(run_id,"technical"), "release": self.store.has_approval(run_id,"release")}
        decision = evaluate(next_stage, approvals)
        if not decision.allowed:
            run.status = "BLOCKED"; run.metadata["policy_reasons"] = decision.reasons
        else:
            run.stage = next_stage; run.status = "RUNNING"
        run.updated_at = now(); self.store.save_run(run); self.store.checkpoint(run.run_id, run.stage, run.status, run.metadata, run.updated_at)
        return run
