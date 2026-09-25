---
name: prompt-intake-adapter
description: Convert a developer prompt describing a feature, CR, bug, hotfix, or technical change into a canonical work item without inventing missing requirements.
---

# Prompt Intake Adapter

Use the shared [handoff contract](../RESULT-CONTRACT.md).

## Inputs

Developer request, referenced artifacts, and existing work-item IDs.

## Procedure

1. Extract the requested outcome, current behavior, scope, exclusions, constraints, and acceptance criteria; retain the original request as a reference.
2. Separate explicit requirements from assumptions and unresolved questions. Reuse an existing work item when the request is steering it.
3. Classify input completeness and propose a work type. Do not assign business priorities or invent acceptance criteria to fill gaps.

## Deliverable

Canonical work-item draft with source_request, objective, scope, exclusions, constraints, acceptance_criteria, references, and open_questions, written at `agentic/data/project-context/features/<work-item-id>/WORK-ITEM.md` (reuse an existing id when the request steers existing work; follow `agentic/kit/templates/feature.md`, `cr.md`, or `task.md` by work type). Return the id in `outputs.work_item_id`; later skills write beside it.

## Readiness boundary

Block downstream implementation when the desired behavior or acceptance criteria cannot be determined; intake may return PARTIAL with a usable draft.
