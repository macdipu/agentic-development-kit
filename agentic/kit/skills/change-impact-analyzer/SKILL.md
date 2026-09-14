---
name: change-impact-analyzer
description: Analyze a change request against the current baseline and identify affected requirements, modules, UI, APIs, database, architecture, code, tests, security, approvals, and workflow gates.
---

# Change Impact Analyzer

Use the shared [handoff contract](../RESULT-CONTRACT.md).

## Inputs

Requested delta, current implementation/context, related requirements, APIs, data, and tests.

## Procedure

1. Describe before/after behavior and identify affected modules, callers, shared components, contracts, migrations, and configuration.
2. Trace direct and relevant transitive dependencies; distinguish confirmed impact from areas needing investigation.
3. Identify artifacts and approvals to reopen, compatibility risks, regression scope, and rollback needs. Preserve unaffected baseline artifacts.

## Deliverable

Delta summary, impact matrix with evidence and confidence, affected artifacts, regression targets, and readiness/planning recommendation.

## Readiness boundary

Block implementation readiness when a potentially breaking contract or migration has unresolved consumers or data semantics.
