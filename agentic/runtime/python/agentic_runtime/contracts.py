RESULT_STATUSES = {"READY", "PARTIAL", "BLOCKED", "PREVIEW_READY"}
SUCCESS_STATUSES = {"READY", "PREVIEW_READY"}


def validate_result(result):
    if not isinstance(result, dict):
        raise ValueError("Result must be an object")
    required = {"status", "evidence", "blocking_issues", "open_questions", "recommended_next_step", "outputs"}
    if set(result) != required:
        raise ValueError("Result must contain exactly the documented handoff fields")
    if not isinstance(result["status"], str) or result["status"] not in RESULT_STATUSES:
        raise ValueError("Unknown result status")
    for name in ("evidence", "blocking_issues", "open_questions"):
        if not isinstance(result[name], list) or any(not isinstance(item, str) or not item.strip() for item in result[name]):
            raise ValueError(name + " must be an array of nonempty strings")
    if not isinstance(result["outputs"], dict):
        raise ValueError("outputs must be an object")
    if not isinstance(result["recommended_next_step"], str) or not result["recommended_next_step"].strip():
        raise ValueError("recommended_next_step must be nonempty")
    if result["status"] in SUCCESS_STATUSES and (not result["evidence"] or result["blocking_issues"]):
        raise ValueError("Ready results require evidence and no blocking issues")
    if result["status"] == "BLOCKED" and not result["blocking_issues"]:
        raise ValueError("Blocked results require a blocking issue")
    return result
