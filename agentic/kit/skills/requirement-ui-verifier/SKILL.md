---
name: requirement-ui-verifier
description: Verify consistency among requirements, SRS, UI, validation, permissions, errors, and acceptance criteria.
---

# Requirement Ui Verifier

Use the shared [handoff contract](../RESULT-CONTRACT.md).

## Inputs

Requirement/SRS IDs, UI designs or implementation, and relevant state/flow evidence.

## Procedure

1. Map each UI requirement to a screen, state, control, and observable acceptance check.
2. Check validation, permissions, content, error/loading/empty states, navigation, and accessibility requirements supplied by the project.
3. Record mismatches with expected versus observed behavior and evidence; request device preview when layout/runtime evidence is necessary.

## Deliverable

Requirement-to-screen coverage, discrepancies with severity, missing states, and verification verdict.

## Readiness boundary

Block readiness for missing or contradictory required flows; distinguish uninspected UI from confirmed defects.
