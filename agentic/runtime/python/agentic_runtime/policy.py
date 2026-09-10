from dataclasses import dataclass
from typing import Dict, List

@dataclass
class PolicyDecision:
    allowed: bool
    reasons: List[str]

REQUIRED_GATES = {
    "IMPLEMENTATION": "technical",
    "RELEASE": "release",
}

def evaluate(stage: str, approvals: Dict[str, bool], direct_production_write: bool=False) -> PolicyDecision:
    reasons = []
    gate = REQUIRED_GATES.get(stage)
    if gate and not approvals.get(gate, False):
        reasons.append(f"Missing required approval gate: {gate}")
    if stage == "PRODUCTION_WRITE" and not direct_production_write:
        reasons.append("Direct production write is disabled")
    return PolicyDecision(allowed=not reasons, reasons=reasons)
