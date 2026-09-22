---
name: sprint-planner
description: Plan sprint delivery for software work when planning is actually required, regardless of whether the work is a Feature, CR, bug, hotfix, or technical change. Use after work-level classification when the orchestrator selects FULL_SPRINT_PLANNING or ADD_TO_EXISTING_SPRINT and delivery sequencing, dependencies, ownership, capacity, or UAT targeting must be coordinated.
---

# Sprint Planner

## Goal

Create the minimum useful sprint plan without forcing planning ceremony for already-planned or trivial work.

## Preconditions

Receive:
- normalized work item
- project/module context
- technical readiness state where required
- work-item-level classification
- current sprint/backlog state if available
- dependencies and risks

## Plan

Determine:
- affected module(s)
- Epic selection/creation if needed
- Stories if needed
- task lanes
- dependencies and implementation order
- parallelizable work
- ownership or agent lanes
- effort/uncertainty input
- current sprint vs backlog placement recommendation
- UAT target need

## Do not

- run merely because the work is a Feature or CR
- recreate an existing approved task plan
- infer sprint commitment or human approval
- invent capacity or dates when data is unavailable

## Artifacts

When the work-item-level classification is `EPIC_STORY_TASK`, write the epic at
`agentic/data/project-context/features/<work-item-id>/EPIC.md` (template:
`agentic/kit/templates/epic.md`) and each story at
`agentic/data/project-context/features/<work-item-id>/stories/STORY-XXX.md`
(template: `agentic/kit/templates/story.md`), linked from the epic's `## Stories`
section. When the classification is `STORY_TASK`, write only the story file(s)
(no `EPIC.md`) with `## Parent Epic` set to `NONE`. When it is `TASK_ONLY`, write
neither — task-breakdown-agent's task files stand alone. Do not create an epic or
story file merely because this skill ran; only when the classification calls for
that hierarchy depth. task-breakdown-agent still owns writing
`tasks/TASK-XXX.md`; reference the relevant `STORY-XXX` id in a task's scope/
references when a parent story exists, rather than nesting task files under
`stories/`.

Return the plan to the orchestrator and planning authority.

## Runtime handoff

Use the shared [handoff contract](../RESULT-CONTRACT.md) when submitting results to the reference runtime. Put the specialized fields and verdict described above inside `outputs`; retain evidence and blockers in the envelope.
