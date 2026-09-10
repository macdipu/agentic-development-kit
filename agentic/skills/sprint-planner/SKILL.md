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

Return the plan to the orchestrator and planning authority.
