# Sprint Planning and Work-Level Decision

Sprint planning is a conditional stage for all work types. It is not automatically required because a request is a Feature or a CR.

## Universal decision flow

```text
Any Incoming Work
Feature / CR / Bug / Hotfix / Technical Change
        |
        v
Intake + Context
        |
        v
Requirements / Impact Analysis
        |
        v
Technical Readiness (when required)
        |
        v
Work Item Level Classification
        |
        +--> EPIC_STORY_TASK
        +--> STORY_TASK
        +--> TASK_ONLY
        +--> EXECUTE_EXISTING_TASK
        |
        v
Sprint Handling Decision
        |
        +--> FULL_SPRINT_PLANNING
        +--> ADD_TO_EXISTING_SPRINT
        +--> BACKLOG_ONLY
        +--> EXPEDITED
        +--> NO_REPLAN
```

## When full sprint planning is useful

Use full sprint planning when work requires substantial sequencing, multiple teams/modules, coordinated dependencies, capacity decisions, a UAT target, or a large delivery scope.

## When full sprint planning is unnecessary

Do not force full sprint planning when an approved task is already planned, or when a small bounded change can be added to an existing sprint/backlog without meaningful replanning.

## Planning responsibilities

Sprint planning determines:
- affected module(s)
- appropriate Epic/Story/Task hierarchy
- dependencies and ordering
- parallelizable work
- ownership/agent lanes
- effort/uncertainty
- current sprint vs backlog vs expedited handling
- UAT target when relevant

The sprint planner proposes the plan. Human planning authority remains with the responsible TL/Lead/PM according to project policy.

## Artifacts per hierarchy level

Only Task ever had a concrete file contract; this closes that gap for Epic/Story so
sprint-planner's "Epic selection/creation" and "Stories if needed" are not just a
verdict with nothing on disk:

| Classification | Files written | Template |
|---|---|---|
| `EPIC_STORY_TASK` | `features/<id>/EPIC.md` + one `features/<id>/stories/STORY-XXX.md` per story + `features/<id>/tasks/TASK-XXX.md` per task | `templates/epic.md`, `templates/story.md`, `templates/task.md` |
| `STORY_TASK` | `features/<id>/stories/STORY-XXX.md` (Parent Epic: `NONE`) + `features/<id>/tasks/TASK-XXX.md` | `templates/story.md`, `templates/task.md` |
| `TASK_ONLY` | `features/<id>/tasks/TASK-XXX.md` only | `templates/task.md` |
| `EXECUTE_EXISTING_TASK` | none — reuse what already exists | n/a |

sprint-planner writes `EPIC.md`/`STORY-XXX.md`; task-breakdown-agent still writes
`TASK-XXX.md` regardless of level, referencing its parent `STORY-XXX` id when one
exists. epic-verifier and sprint-readiness-verifier read these files; they do not
generate them. A `STORY_TASK`-level item may still record stories informally as table
rows inside `TASKS.md`/`DELIVERY-PLAN.md` instead of a separate `STORY-XXX.md` file
when a single short table communicates the same sequencing more usefully — prefer the
file when a story has its own acceptance criteria, owner, or non-trivial scope worth
tracking independently.
