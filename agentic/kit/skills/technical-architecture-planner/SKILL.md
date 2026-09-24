---
name: technical-architecture-planner
description: Design or update architecture (HLD) from verified requirements and current project context while preferring existing project patterns.
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

Architecture proposal (HLD), reuse map, alternatives/tradeoffs, affected contracts, risks, and ADR recommendation. Write or update the feature HLD at `agentic/data/project-context/features/<work-item-id>/ARCHITECTURE.md` (template: `agentic/kit/templates/feature-hld.md`). If the project-level HLD at `agentic/data/project-context/ARCHITECTURE.md` does not exist, also draft it at `status: DRAFT` (template: `agentic/kit/templates/project-hld.md`); never mark it `APPROVED` yourself. Add the feature HLD to its `## Feature Architecture Index`.

## Readiness boundary

Block technical readiness when a material interface, data ownership, or security decision remains unresolved.
