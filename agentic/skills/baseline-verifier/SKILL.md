---
name: baseline-verifier
description: Verify a recovered brownfield baseline against available evidence and human corrections before marking context usable.
---

# Baseline Verifier

Use the shared [handoff contract](../RESULT-CONTRACT.md).

## Inputs

Recovered requirements/context, evidence references, confidence annotations, and human corrections.

## Procedure

1. Sample each material baseline claim against its source; check that module boundaries, behavior, contracts, and commands agree.
2. Confirm revisions/fingerprints and ensure stale or missing slices are not labeled available.
3. Apply explicit corrections with provenance and distinguish reusable confirmed context from provisional sections.

## Deliverable

Baseline verdict, confirmed scope, rejected/provisional claims, freshness record, and refresh tasks.

## Readiness boundary

Return BLOCKED for contradictions affecting the requested behavior; use PARTIAL when only an independently usable subset is verified.
