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
