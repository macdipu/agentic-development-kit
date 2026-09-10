---
name: test-baseline-agent
description: Map current behavior/modules to test evidence and identify coverage gaps, flaky/broken tests, and regression risk.
---

# Test Baseline Agent

Use the shared [handoff contract](../RESULT-CONTRACT.md).

## Inputs

Affected modules/behavior, current tests, CI commands, and permitted execution environment.

## Procedure

1. Map behavior and risk to existing unit, integration, contract, UI, and regression checks.
2. Run a scoped baseline where appropriate and separate pre-existing failures from untested paths; record environment and revision.
3. Identify missing coverage, flaky checks, fixture/dependency gaps, and a minimum regression set for the requested change.

## Deliverable

Baseline check results, coverage map, pre-existing failures, gaps, and recommended regression commands.

## Readiness boundary

Return PARTIAL when required dependencies prevent baseline execution; do not attribute existing failures to a change without evidence.
