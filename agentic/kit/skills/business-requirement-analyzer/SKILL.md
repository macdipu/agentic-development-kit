---
name: business-requirement-analyzer
description: Extract functional and non-functional requirements, business rules, actors, constraints, acceptance criteria, conflicts, and open questions.
---

# Business Requirement Analyzer

Use the shared [handoff contract](../RESULT-CONTRACT.md).

## Inputs

Canonical work item, stakeholder statements, and relevant baseline requirements.

## Procedure

1. Identify actors, triggers, normal/alternate/error flows, business rules, data constraints, and nonfunctional needs.
2. Assign or reuse requirement IDs and trace each requirement to a source. Make acceptance criteria observable using examples supported by the request.
3. Resolve duplicate requirements and expose contradictions, unspecified thresholds, authorization rules, and out-of-scope behavior.

## Deliverable

Requirement list, actor/flow map, acceptance criteria, source traceability, and unresolved decisions.

## Readiness boundary

Block readiness if conflicting business rules or missing authorization/data rules affect implementation; do not choose a business rule on behalf of stakeholders.
