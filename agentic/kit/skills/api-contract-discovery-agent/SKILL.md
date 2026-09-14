---
name: api-contract-discovery-agent
description: Recover existing API routes, contracts, auth, validation, consumers, and implementations from code, specs, clients, tests, and runtime evidence.
---

# Api Contract Discovery Agent

Use the shared [handoff contract](../RESULT-CONTRACT.md).

## Inputs

Affected routes/services, API specifications, clients, and contract tests.

## Procedure

1. Find route registration and handlers, then trace request validation, authentication/authorization, response/error shapes, and consumers.
2. Compare implementation, specification, and client expectations; record mismatched fields, status codes, versioning, pagination, and idempotency where applicable.
3. Identify compatibility-sensitive behavior and evidence gaps without making live writes to external services.

## Deliverable

Contract inventory with endpoint/event IDs, producer/consumer references, auth/data rules, discrepancies, and test coverage.

## Readiness boundary

Block a breaking-change recommendation when consumers or authorization semantics are unknown.
