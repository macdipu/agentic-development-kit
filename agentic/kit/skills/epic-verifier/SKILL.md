---
name: epic-verifier
description: Verify that an epic fully covers approved scope, acceptance criteria, UI, technical impacts, QA, security, and dependencies.
---

# Epic Verifier

Use the shared [handoff contract](../RESULT-CONTRACT.md).

## Inputs

Proposed epic/stories/tasks, requirement coverage, dependencies, and selected planning
depth. Read the artifacts sprint-planner and task-breakdown-agent already wrote:
`agentic/data/project-context/features/<work-item-id>/EPIC.md`,
`.../stories/STORY-XXX.md`, and `.../tasks/TASK-XXX.md`. This skill verifies those
files; it does not generate or replace them.

## Procedure

1. Confirm an epic is warranted by the work-level classification; do not create one for task-only work.
2. Map requirements and acceptance criteria to stories/tasks across relevant implementation, data, integration, QA, and operational work.
3. Check missing/duplicate scope, dependency ordering, ownership assumptions, and integration acceptance.

## Deliverable

Coverage matrix, scope/dependency gaps, readiness verdict, and recommended plan corrections.

## Readiness boundary

Block commitment when required scope has no delivery/test coverage or an unresolved dependency prevents execution.
