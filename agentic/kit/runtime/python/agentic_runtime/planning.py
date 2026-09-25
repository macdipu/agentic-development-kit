"""Planning is decided by evidence, and its artifacts must exist.

Before, the route was fixed at `start` (default NO_REPLAN), before anyone had
classified the work, so the PLANNING stage -- the only place Epic, Story, and
sprint files are written -- never ran, and no rule required the classification.

Now the run's decision stage (TECHNICAL, or CONTEXT for an existing task) cannot
be left without a `work-item-level-classifier` result naming the hierarchy, the
sprint handling, and the work item id. The runtime rebuilds the rest of the route
from that verdict, and PLANNING cannot be left until the files the verdict calls
for exist.
"""
import re
from pathlib import Path

HIERARCHY = ("EPIC_STORY_TASK", "STORY_TASK", "TASK_ONLY", "EXECUTE_EXISTING_TASK")
SPRINT_HANDLING = ("FULL_SPRINT_PLANNING", "ADD_TO_EXISTING_SPRINT", "BACKLOG_ONLY", "EXPEDITED", "NO_REPLAN")
CLASSIFIER = "work-item-level-classifier"
CONTEXT_ROOT = Path("agentic/data/project-context")
_WORK_ITEM_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def decision_stage(work_type):
    """Stage whose exit fixes the planning route, or None for routes without planning."""
    if work_type in ("device_preview", "discovery"):
        return None
    return "CONTEXT" if work_type == "existing_task" else "TECHNICAL"


def classification(skill_results, stages):
    """The classifier's own latest ready result among `stages` (latest stage wins)."""
    for stage in reversed(stages):
        result = (skill_results or {}).get(stage, {}).get(CLASSIFIER)
        if isinstance(result, dict) and result.get("status") in ("READY", "PREVIEW_READY"):
            return result
    return None


def verdict(result, override=None):
    """(hierarchy, sprint_handling, work_item_id) from a classifier result; raises if incomplete.
    An explicit `start --planning` overrides the sprint handling, never the hierarchy."""
    outputs = (result or {}).get("outputs", {})
    hierarchy = outputs.get("classification")
    handling = override or outputs.get("sprint_handling")
    work_item_id = outputs.get("work_item_id")
    problems = []
    if hierarchy not in HIERARCHY:
        problems.append(f"outputs.classification must be one of {', '.join(HIERARCHY)}")
    if handling not in SPRINT_HANDLING:
        problems.append(f"outputs.sprint_handling must be one of {', '.join(SPRINT_HANDLING)}")
    if not isinstance(work_item_id, str) or not _WORK_ITEM_ID.match(work_item_id):
        problems.append("outputs.work_item_id must name the work item (letters, digits, . _ -), e.g. BOS-010")
    if problems:
        raise ValueError("work-item-level-classifier result is incomplete: " + "; ".join(problems))
    return hierarchy, handling, work_item_id


def needs_planning_stage(hierarchy, handling):
    return handling in ("FULL_SPRINT_PLANNING", "ADD_TO_EXISTING_SPRINT", "BACKLOG_ONLY") \
        or hierarchy in ("EPIC_STORY_TASK", "STORY_TASK")


def missing_artifacts(repo, work_item_id, hierarchy, handling):
    """Files the verdict requires that do not exist yet (paths relative to the repo)."""
    root = Path(repo)
    feature = CONTEXT_ROOT / "features" / work_item_id
    missing = []
    if hierarchy == "EPIC_STORY_TASK" and not (root / feature / "EPIC.md").is_file():
        missing.append(f"{feature.as_posix()}/EPIC.md (template agentic/kit/templates/epic.md)")
    if hierarchy in ("EPIC_STORY_TASK", "STORY_TASK") and not any((root / feature / "stories").glob("STORY-*.md")):
        missing.append(f"{feature.as_posix()}/stories/STORY-*.md (template agentic/kit/templates/story.md)")
    if hierarchy in ("EPIC_STORY_TASK", "STORY_TASK", "TASK_ONLY") and not any((root / feature / "tasks").glob("TASK-*.md")):
        missing.append(f"{feature.as_posix()}/tasks/TASK-*.md (template agentic/kit/templates/task.md)")
    if handling in ("FULL_SPRINT_PLANNING", "ADD_TO_EXISTING_SPRINT"):
        sprints = root / CONTEXT_ROOT / "sprints"
        listed = any(work_item_id in path.read_text(encoding="utf-8", errors="replace")
                     for path in sprints.glob("SPRINT-*.md")) if sprints.is_dir() else False
        if not listed:
            missing.append(f"{(CONTEXT_ROOT / 'sprints').as_posix()}/SPRINT-*.md listing {work_item_id} "
                           f"(template agentic/kit/templates/sprint.md)")
    return missing
