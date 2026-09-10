---
name: automated-qa-agent
description: Evaluate build, lint, static analysis, unit, integration, contract, security, regression, and acceptance evidence.
---

# Automated Qa Agent

Use the shared [handoff contract](../RESULT-CONTRACT.md).

## Inputs

Acceptance criteria, changed scope, test baseline, build/run commands, and existing evidence.

## Procedure

1. Select relevant build/static/unit/integration/contract/regression checks from the change impact; reuse project commands.
2. Run or verify results and record command, environment, revision, exit status, and result artifact. Distinguish failures, skips, flaky reruns, and unavailable checks.
3. Map acceptance criteria to checks and identify what still needs manual QA or UAT. Request device-preview-agent through the orchestrator for mobile launch/layout evidence.

## Deliverable

Check matrix, acceptance coverage, reproducible defects, skipped/unavailable checks, and QA verdict.

## Readiness boundary

Use PARTIAL for required checks that could not run and BLOCKED for confirmed failing acceptance. Preview screenshots do not replace behavioral tests or human QA.
