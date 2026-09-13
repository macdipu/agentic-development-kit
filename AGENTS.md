# Agentic Development Instructions

This file is the canonical repository-level instruction entrypoint for agentic development.

## Core behavior

1. On session start, check for a midflight task before doing anything else (enforced by the `SessionStart` hook, `agentic/runtime/hooks/session_start_check.py`): if `agentic/runtime/state/active-task.json` exists, or the run DB has a run with status `RUNNING`/`BLOCKED`, resume it — do not start a new run for that work item. Only start the next work item once nothing is midflight.
2. Treat the current repository as the source project.
3. Use `agentic/project-context/` before performing broad discovery.
4. If context is available and sufficiently fresh, reuse it.
5. If context is stale or missing, refresh only the affected module or feature scope.
6. Do not audit the whole repository for every task.
7. Prefer existing implementations, shared components, and established architectural patterns.
8. Never invent missing business rules.
9. Never infer human approval.
10. Route work through the appropriate workflow in `agentic/workflows/`.
11. Use skills under `agentic/skills/` as reusable specialist workflows.
12. Record agent start/end timing and relevant task telemetry through the harness.
13. Preserve traceability from request -> requirements -> design -> tasks -> implementation -> QA -> release.

## Input modes

The system supports both:

- Prompt-first: a developer describes a feature, CR, bug, or hotfix in a prompt.
- Document-first: a developer points to an existing FEATURE.md, CR.md, BUG.md, or HOTFIX.md.

Both modes must normalize into a canonical work item before downstream execution.

## Project types

- Greenfield: use the full feature lifecycle.
- Brownfield/legacy: use context-first, incremental discovery and baseline recovery only where needed.

## Routing authority

The Workflow Orchestrator is the final authority for selecting the next skill based on:
- work type
- workflow stage
- context availability
- impact
- policy
- approvals

## Universal planning rule

Do not decide hierarchy or Sprint Planning from request type alone. For Features, CRs, bugs, hotfixes, and technical changes, classify the minimum useful work level and then choose sprint handling. Full Sprint Planning is conditional. Existing approved tasks should execute without recreating Feature/Epic/Story artifacts or replanning unless impact changes materially.

## Harness runtime

When the reference runtime is enabled, treat workflow state, approvals, policies, context freshness, capability limits, checkpoints, and task timing as deterministic harness responsibilities. Do not substitute model judgment for these controls.
