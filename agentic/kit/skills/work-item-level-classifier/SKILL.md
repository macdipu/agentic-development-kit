---
name: work-item-level-classifier
description: Classify incoming or analyzed software work into the minimum useful planning hierarchy choices including EPIC_STORY_TASK, STORY_TASK, TASK_ONLY, or EXECUTE_EXISTING_TASK. Use after requirements or change impact are understood and before sprint handling or task decomposition, for features, change requests, bugs, hotfixes, and technical changes.
---

# Work Item Level Classifier

## Goal

Choose the smallest work hierarchy that preserves delivery clarity, traceability, ownership, testing, and dependency management.

## Classifications

- `EPIC_STORY_TASK`: large or multi-flow work containing multiple independently testable outcomes, teams, or substantial dependency chains. sprint-planner then writes `EPIC.md` + `stories/STORY-XXX.md`; see its skill doc's `## Artifacts`.
- `STORY_TASK`: bounded capability with one or a few coherent user/business outcomes. sprint-planner writes `stories/STORY-XXX.md` only (no `EPIC.md`).
- `TASK_ONLY`: small localized implementation or technical change that does not need a user story layer. No epic/story file is written.
- `EXECUTE_EXISTING_TASK`: an already approved and sufficiently specified task exists; do not recreate planning artifacts.

## Decision factors

Evaluate scope, number of user outcomes, modules, teams, dependencies, risk, architecture impact, security/regulatory impact, testing breadth, and existing planning artifacts.

Do not classify by request type alone. A feature can be small. A CR can be large.

## Output

Return:
- classification
- rationale
- affected modules
- dependencies
- required planning depth
- whether sprint handling must be evaluated
- blockers/open questions

Return the result to the Workflow Orchestrator.

## Runtime handoff

Use the shared [handoff contract](../RESULT-CONTRACT.md) when submitting results to the reference runtime. Put the specialized fields and verdict described above inside `outputs`; retain evidence and blockers in the envelope.
