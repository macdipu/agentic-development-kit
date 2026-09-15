---
name: adr-generator
description: Create ADRs only for significant architecture decisions, including alternatives, consequences, risks, and status.
---

# Adr Generator

Use the shared [handoff contract](../RESULT-CONTRACT.md).

## Inputs

A significant proposed architecture decision, alternatives, constraints, and relevant existing ADRs.

## Procedure

1. First determine whether a material decision exists; ordinary changes following established patterns may need no ADR.
2. For a material decision, document context, viable alternatives, tradeoffs, selected proposal, consequences, and superseded decisions.
3. Record status as proposed until explicit approval exists; link supporting requirements, design, and decision authority.

## Deliverable

ADR artifact or a supported no-ADR-needed rationale, related decision IDs, and approval status. Write the artifact at `agentic/data/project-context/features/<work-item-id>/adr/ADR-XXX-title.md` (template: `agentic/kit/templates/adr.md`).

## Readiness boundary

Block a definitive decision when its constraints or decision authority are unresolved; do not invent approval or manufacture alternatives.
