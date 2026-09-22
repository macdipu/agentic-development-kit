---
name: srs-generator
description: Create a traceable software requirements specification from approved requirements and constraints.
---

# Srs Generator

Use the shared [handoff contract](../RESULT-CONTRACT.md).

## Inputs

Verified requirement list, UI/flow references, constraints, and explicit source approvals where required.

## Procedure

1. Organize functional/nonfunctional requirements, interfaces, data rules, roles, flows, and error behavior under stable IDs.
2. Trace each specification item to its source and acceptance criteria; retain unresolved decisions explicitly.
3. Check terminology and cross-references, remove duplication, and update only affected sections of an existing SRS.

## Deliverable

SRS artifact, source/acceptance traceability, changed sections, and unresolved specification questions. Write or update the artifact at `agentic/data/project-context/features/<work-item-id>/SRS.md` (template: `agentic/kit/templates/srs.md`).

If `agentic/data/project-context/SRD.md` does not exist yet, also draft it from the same verified, whole-project-scoped requirements (same template), at `status: DRAFT`, and add a `project_docs.SRD` entry to `context-index.yaml` (see `project-context/README.md`). Never mark it `APPROVED` — that field is set only by a human reviewer. Report the draft as an open question for human approval in the envelope; do not block this work item's own SRS on that approval.

## Readiness boundary

Return PARTIAL or BLOCKED when missing source requirements prevent a complete specification; generated prose is not approval.
