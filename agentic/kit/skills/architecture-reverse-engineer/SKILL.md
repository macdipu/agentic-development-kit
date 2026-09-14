---
name: architecture-reverse-engineer
description: Recover evidence-backed current architecture from legacy code and artifacts, distinguishing confirmed, inferred, and unknown findings.
---

# Architecture Reverse Engineer

Use the shared [handoff contract](../RESULT-CONTRACT.md).

## Inputs

Affected modules, import/call relationships, existing architecture records, and deployment evidence.

## Procedure

1. Map component boundaries, dependency direction, data ownership, external integrations, and execution paths relevant to the request.
2. Compare documented architecture with implementation and record divergences with source locations.
3. Describe existing patterns available for reuse and coupling constraints without proposing a redesign unless requested.

## Deliverable

As-is component/dependency map, architecture facts, documented divergences, reuse candidates, and confidence per finding.

## Readiness boundary

Use PARTIAL when dynamic wiring or unavailable services prevent confirming a boundary; label inferred relationships.
