from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

@dataclass
class WorkflowRun:
    run_id: str
    project: str
    work_type: str
    title: str
    stage: str = "INTAKE"
    status: str = "CREATED"
    dry_run: bool = False
    created_at: str = ""
    updated_at: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
