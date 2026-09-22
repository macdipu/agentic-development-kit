---
name: technical-architecture-planner
description: Design or update architecture from verified requirements and current project context while preferring existing project patterns.
---

# Technical Architecture Planner

Use the shared [handoff contract](../RESULT-CONTRACT.md).

## Inputs

Verified requirements, baseline architecture, change impact, risks, and integration constraints.

## Procedure

1. Identify existing patterns and components that satisfy the requested capability before proposing new boundaries or dependencies.
2. Describe component responsibilities, data/control flow, contracts, failure handling, and security boundaries affected by the work.
3. Evaluate material alternatives and migration/rollback implications; request an ADR only for significant decisions.

## Deliverable

Architecture proposal, reuse map, alternatives/tradeoffs, affected contracts, risks, and ADR recommendation. Write or update the artifact at `agentic/data/project-context/features/<work-item-id>/ARCHITECTURE.md` (template: `agentic/kit/templates/architecture.md`).

If `agentic/data/project-context/ARCHITECTURE.md` does not exist yet, also draft it from the same verified, whole-project-scoped design, at `status: DRAFT`, and add a `project_docs.ARCHITECTURE` entry to `context-index.yaml` (see `project-context/README.md`). Never mark it `APPROVED` — that field is set only by a human reviewer. Report the draft as an open question for human approval in the envelope; do not block this work item's own architecture doc on that approval.

## Readiness boundary

Block technical readiness when a material interface, data ownership, or security decision remains unresolved.
