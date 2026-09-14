---
name: agentic-sdlc-orchestrator
description: Coordinate Agentic SDLC workflows for greenfield and brownfield projects. Use to normalize work, load context, classify work and planning level, decide whether sprint planning is required, select specialist skills, enforce workflow state and approvals, and route Features, CRs, bugs, hotfixes, technical changes, and existing tasks through the minimum necessary lifecycle.
---

# Agentic SDLC Orchestrator

## Core routing order

1. Identify prompt-first or document-first intake.
2. Normalize to a canonical work item.
3. Load project context before broad discovery.
4. Classify work type.
5. Run requirement or change-impact analysis as appropriate.
6. Establish technical readiness when required.
7. Run `work-item-level-classifier`.
8. Decide sprint handling:
   - FULL_SPRINT_PLANNING
   - ADD_TO_EXISTING_SPRINT
   - BACKLOG_ONLY
   - EXPEDITED
   - NO_REPLAN
9. Invoke `sprint-planner` only when needed.
10. Verify sprint readiness when sprint commitment is considered.
11. Create/use the minimum useful Epic/Story/Task hierarchy.
12. Route implementation, review, QA, UAT, and release readiness.
13. Persist validated context/artifact deltas and timing telemetry.

Do not infer human approval. Do not force an Epic, Story, or Sprint Planning stage when the existing work item and delivery state make it unnecessary.

For emulator, simulator, or connected-device preview requests, select `device-preview-agent` using [mobile preview routing](../../workflows/routing.md#mobile-device-preview). Reuse this skill during implementation or QA when on-device visual evidence is needed.

## Runtime handoff

Use the shared [handoff contract](../RESULT-CONTRACT.md) when submitting results to the reference runtime. Put the specialized fields and verdict described above inside `outputs`; retain evidence and blockers in the envelope.
