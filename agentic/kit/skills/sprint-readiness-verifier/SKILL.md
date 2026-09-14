---
name: sprint-readiness-verifier
description: Verify whether software work is ready to be committed to a sprint or should remain in backlog, be expedited, or require more preparation. Use for features, change requests, bugs, hotfixes, and technical changes after technical readiness and planning-level classification when sprint commitment is being considered.
---

# Sprint Readiness Verifier

## Goal

Determine whether work has enough clarity, dependency resolution, ownership, testing scope, and approvals to enter a sprint.

## Verify

- requirements or change delta are understood
- acceptance criteria are sufficient
- technical readiness is satisfied where required
- work hierarchy is appropriate
- dependencies are identified
- blocking external dependencies are visible
- task ownership or execution lanes are known
- test/QA scope is known
- security/regulatory gates are identified
- UAT need and target are identified where applicable
- unresolved questions do not prevent commitment

## Verdicts

- `SPRINT_READY`
- `BACKLOG_ONLY`
- `BLOCKED`
- `EXPEDITED_READY`
- `NO_REPLAN_REQUIRED`

Do not infer sprint assignment or human approval.

## Runtime handoff

Use the shared [handoff contract](../RESULT-CONTRACT.md) when submitting results to the reference runtime. Put the specialized fields and verdict described above inside `outputs`; retain evidence and blockers in the envelope.
