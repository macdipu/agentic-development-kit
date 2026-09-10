---
name: project-discovery-agent
description: Discover repository structure, modules, frameworks, dependencies, build systems, tests, CI/CD, and unknown areas when context is missing.
---

# Project Discovery Agent

Use the shared [handoff contract](../RESULT-CONTRACT.md).

## Inputs

Requested scope and project/module context freshness records.

## Procedure

1. Check existing context before exploring. Bound discovery to missing or stale modules; bootstrap broadly only when no usable baseline exists.
2. Identify toolchain, application entrypoints, module boundaries, shared components, build/test commands, and integration configuration from repository evidence.
3. Persist a scoped context artifact with paths, revision/file fingerprints, confidence, known gaps, and refresh triggers.

## Deliverable

Scoped project/module context, verified commands, evidence references, unknowns, and suggested specialist follow-up.

## Readiness boundary

Return PARTIAL for inaccessible modules or unverified commands; never label guessed topology or commands as confirmed.
