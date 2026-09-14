---
name: technical-spec-generator
description: Produce implementation-ready technical specification, LLD, API contracts, database impact, security, error handling, observability, dependencies, and test strategy.
---

# Technical Spec Generator

Use the shared [handoff contract](../RESULT-CONTRACT.md).

## Inputs

Requirements, architecture proposal/decisions, current conventions, APIs/data model, and test strategy.

## Procedure

1. Translate each affected requirement into concrete component changes, interfaces, validation, error handling, and observability.
2. Specify migration/configuration impacts, compatibility, rollback, and test cases only where the change requires them.
3. Link implementation boundaries to existing code and document unresolved technical choices separately from settled requirements.

## Deliverable

Implementation specification/LLD, requirement-to-component mapping, contract/data changes, test plan, and open decisions. Write or update the artifact at `agentic/data/project-context/features/<work-item-id>/TECH-SPEC.md` (template: `agentic/templates/tech-spec.md`).

## Readiness boundary

Block when an implementer would have to invent business rules or a consequential integration contract.
