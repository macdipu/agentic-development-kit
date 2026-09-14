---
name: brownfield-risk-analyzer
description: Assess legacy areas for coupling, missing tests, unknown ownership, hard-coded rules, unsupported dependencies, security, and operational risk.
---

# Brownfield Risk Analyzer

Use the shared [handoff contract](../RESULT-CONTRACT.md).

## Inputs

Scoped baseline, change impact, test evidence, dependency and operational constraints.

## Procedure

1. Identify coupling, untested paths, unsupported components, data or security boundaries, and deployment fragility relevant to the change.
2. For each risk, record a concrete trigger, affected outcome, likelihood rationale, impact, evidence, and possible mitigation.
3. Prioritize investigation and tests by change exposure; distinguish baseline debt from risks introduced by this work.

## Deliverable

Prioritized risk register, targeted discovery/test actions, residual risks, and recommended gates.

## Readiness boundary

Block readiness for an unresolved risk that prevents safe implementation or verification; avoid unrelated repository-wide hardening.
