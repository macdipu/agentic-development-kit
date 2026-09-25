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


# A narrow, mechanically-checked exception to REQUIRED_GATES -- technical only,
# never release/uat. Every condition is read off evidence a skill has already
# self-reported onto the run; nothing here is inferred (AGENTS.md #10).
AUTO_APPROVE_GATES = {"technical"}


def auto_approve_eligible(gate, skill_results, context_files):
    """True only when all three already hold on recorded, skill-attributed evidence:
      - work-item-level-classifier's own result classified the item TASK_ONLY
      - the reviewed scope is exactly one file (no diff exists yet pre-implementation,
        so file count is the only concrete "how small is this" signal available here)
      - technical-readiness-verifier's own result says TECHNICAL_READY
    `skill_results` maps stage -> skill -> result, so another skill claiming either
    verdict does not count.
    """
    if gate not in AUTO_APPROVE_GATES:
        return False
    if len(context_files or {}) != 1:
        return False
    def outputs_of(skill):
        for by_skill in (skill_results or {}).values():
            result = by_skill.get(skill) if isinstance(by_skill, dict) else None
            if isinstance(result, dict) and result.get("status") in {"READY", "PREVIEW_READY"}:
                yield result.get("outputs", {})
    return (any(o.get("classification") == "TASK_ONLY" for o in outputs_of("work-item-level-classifier"))
            and any(o.get("verdict") == "TECHNICAL_READY" for o in outputs_of("technical-readiness-verifier")))
