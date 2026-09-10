---
name: intake-change-classifier
description: Classify incoming software work as new feature, change request, bug, hotfix, technical change, security/regulatory change, or discovery work.
---

# Intake Change Classifier

Use the shared [handoff contract](../RESULT-CONTRACT.md).

## Inputs

Normalized work item, current behavior, and affected context.

## Procedure

1. Compare requested behavior to the baseline: new capability, change to existing capability, defect, emergency repair, technical change, security change, or discovery.
2. State why the classification fits and identify mixed work that needs separate tracking only when it has independent acceptance criteria.
3. Pass impact and urgency evidence to the orchestrator. Do not derive hierarchy, sprint planning, or emergency authority from the work-type label.

## Deliverable

work_type, rationale, affected_scope, urgency_evidence, related_items, and classification uncertainty.

## Readiness boundary

Return PARTIAL when the baseline is insufficient to distinguish a feature change from a defect; request scoped discovery.
