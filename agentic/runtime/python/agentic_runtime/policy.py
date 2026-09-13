from dataclasses import dataclass

WORK_TYPES = {"new_feature", "change_request", "bug", "hotfix", "technical_change", "security_change", "discovery", "existing_task", "device_preview"}
PLANNING = {"FULL_SPRINT_PLANNING", "ADD_TO_EXISTING_SPRINT", "BACKLOG_ONLY", "EXPEDITED", "NO_REPLAN"}
STAGES = {"INTAKE", "CONTEXT", "REQUIREMENTS", "IMPACT", "TECHNICAL", "PLANNING", "IMPLEMENTATION", "PREVIEW", "REVIEW", "QA", "UAT", "RELEASE", "COMPLETED"}
REQUIRED_GATES = {"IMPLEMENTATION": "technical", "RELEASE": "release"}


@dataclass
class PolicyDecision:
    allowed: bool
    reasons: list


def workflow_route(work_type, planning="NO_REPLAN", require_uat=False):
    if work_type not in WORK_TYPES or planning not in PLANNING:
        raise ValueError("Unknown work type or sprint handling")
    route = ["INTAKE", "CONTEXT"]
    if work_type == "device_preview":
        return route + ["PREVIEW", "COMPLETED"]
    if work_type == "discovery":
        return route + ["REVIEW", "COMPLETED"]
    if work_type == "new_feature":
        route += ["REQUIREMENTS", "TECHNICAL"]
    elif work_type != "existing_task":
        route += ["IMPACT", "TECHNICAL"]
    if planning in {"FULL_SPRINT_PLANNING", "ADD_TO_EXISTING_SPRINT", "BACKLOG_ONLY"}:
        route += ["PLANNING"]
    if planning == "BACKLOG_ONLY":
        return route + ["COMPLETED"]
    return route + ["IMPLEMENTATION", "REVIEW", "QA"] + (["UAT"] if require_uat else []) + ["RELEASE", "COMPLETED"]


def evaluate(stage, approvals):
    if stage not in STAGES:
        return PolicyDecision(False, ["Unknown or unsupported stage: " + stage])
    gate = REQUIRED_GATES.get(stage)
    reasons = ["Missing required approval gate: " + gate] if gate and not approvals.get(gate, False) else []
    return PolicyDecision(not reasons, reasons)
