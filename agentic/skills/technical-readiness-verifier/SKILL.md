---
name: technical-readiness-verifier
description: Determine whether work is technically ready, conditionally ready, or blocked.
---

# Technical Readiness Verifier

Use the shared [handoff contract](../RESULT-CONTRACT.md).

## Inputs

Requirements/acceptance criteria, architecture/specification, impact/risk register, and required decisions.

## Procedure

1. Check that behavior, component boundaries, contracts, data changes, dependencies, and test strategy are sufficient for implementation.
2. Verify significant decisions have the evidence/approval required by project policy; distinguish a review verdict from human approval.
3. Classify each remaining question as blocking or nonblocking with a reason and owner when known.

## Deliverable

outputs.verdict of TECHNICAL_READY, CONDITIONALLY_READY, or BLOCKED; checklist evidence, conditions, and next actions.

## Readiness boundary

Use envelope READY only for TECHNICAL_READY. Use PARTIAL for conditional readiness and BLOCKED for unresolved implementation-critical questions.
