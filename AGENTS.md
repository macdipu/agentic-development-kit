# Agentic Development Instructions

This file is the canonical repository-level instruction entrypoint for agentic development.

## Core behavior

1. On session start, check for a midflight task before doing anything else (enforced by the `SessionStart` hook, `agentic/kit/runtime/hooks/session_start_check.py`): if `agentic/data/runtime/state/active-task.json` exists, or the run store (`agentic/data/runtime/state/runs/`) has a run with status `RUNNING`/`BLOCKED`, resume it — do not start a new run for that work item. Only start the next work item once nothing is midflight. On a CLI without hook support, run that script yourself as the first action of the session. The same hook also surfaces `.agent/HANDOFF.md` and the latest `.agent/sessions/*.md` entry, if present — cross-agent-platform handoff notes (compatible with `agent-handoff`) left by a prior session on this or another platform; read them as pickup context alongside the midflight check.
2. When compaction is imminent (surfaced by the `PreCompact` hook, `agentic/kit/runtime/hooks/precompact_checkpoint.py`, or on your own judgment if your CLI has no hook support), update every doc this session touched — work-item status, README/AGENTS notes, any tracked plan — before the turn ends, and scope any remaining work down to the smallest subtask that can actually finish rather than starting something large. When a governed task/run is active, the `Stop` hook (`agentic/kit/runtime/hooks/session_stop_handoff.py`) writes `.agent/HANDOFF.md` and a new `.agent/sessions/*.md` record automatically; on a CLI without hook support, run `agentic_runtime.cli close-session --agent <claude|codex> --task "..." --completed "..." --next-action "..."` yourself before ending the session.
3. Treat the current repository as the source project.
4. Use `agentic/data/project-context/` before performing broad discovery.
5. If context is available and sufficiently fresh, reuse it.
6. If context is stale or missing, refresh only the affected module or feature scope.
7. Do not audit the whole repository for every task.
8. Prefer existing implementations, shared components, and established architectural patterns.
9. Never invent missing business rules.
10. Never infer human approval.
11. Route work through the appropriate workflow in `agentic/kit/workflows/`.
12. Use skills under `agentic/kit/skills/` as reusable specialist workflows.
13. Record agent start/end timing and relevant task telemetry through the harness.
14. Preserve traceability from request -> requirements -> design -> tasks -> implementation -> QA -> release.

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
