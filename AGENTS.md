# Agentic Development Instructions

This file is the canonical repository-level instruction entrypoint for agentic development.

## Core behavior

1. On session start, check for a midflight task before doing anything else (enforced by the `SessionStart` hook, `agentic/kit/runtime/hooks/session_start_check.py`): if `.agent/runtime/active-task.json` exists, or the run store (`.agent/runtime/runs/`) has a run with status `RUNNING`/`BLOCKED`, resume it — do not start a new run for that work item. Only start the next work item once nothing is midflight. On a CLI without hook support, run that script yourself as the first action of the session. The same hook also surfaces `.agent/HANDOFF.md` and the latest `.agent/sessions/*.md` entry, if present — cross-agent-platform handoff notes (compatible with `agent-handoff`) left by a prior session on this or another platform; read them as pickup context alongside the midflight check. All of `.agent/` -- handoff notes, session records (each with a full `## Runtime` rendering of its run), and the runtime ledger under `.agent/runtime/` -- is git-tracked, so another machine resumes the same run after `git pull` (only lock/temp files and logs are gitignored). Finish and push on one machine before resuming on another; git gives no cross-machine lock.
2. When compaction is imminent (surfaced by the `PreCompact` hook, `agentic/kit/runtime/hooks/precompact_checkpoint.py`, or on your own judgment if your CLI has no hook support), update every doc this session touched — work-item status, README/AGENTS notes, any tracked plan — before the turn ends, and scope any remaining work down to the smallest subtask that can actually finish rather than starting something large. When a governed task/run is active, the `Stop` hook (`agentic/kit/runtime/hooks/session_stop_handoff.py`) writes `.agent/HANDOFF.md` and a new `.agent/sessions/*.md` record automatically; on a CLI without hook support, run `agentic_runtime.cli close-session --agent <claude|codex> --status <RUNNING|BLOCKED|COMPLETED|CANCELLED> --task "..." --completed "..." --next-action "..."` yourself before ending the session.
3. Treat the current repository as the source project.
4. Use `agentic/data/project-context/` before performing broad discovery.
5. If context is available and sufficiently fresh, reuse it.
6. If context is stale or missing, refresh only the affected module or feature scope.
7. Do not audit the whole repository for every task.
8. Prefer existing implementations, shared components, and established architectural patterns.
9. Never invent missing business rules.
10. Never infer human approval. Approval must come from the user explicitly (for example, a clear "yes, approve" in chat). Once given, the agent may record it itself -- `agentic_runtime.cli approve RUN_ID --gate <gate> --by <user> --comment "..."` or `agentic_runtime.cli adjust-budget RUN_ID --by <user> --reason "..."` -- quoting where the approval was given; the user does not need to run these commands by hand. Never run `approve`/`adjust-budget` without that explicit approval. `approve --auto` is limited to technical gates, never release/UAT.
11. Route work through the appropriate workflow in `agentic/kit/workflows/`. Before reading the matched workflow doc, a persona `AGENT.md`, or `SKILL.md` files in full to make that routing decision, check the routing cache: `agentic_runtime.cli route-cache-get --work-type <type> --project-type <greenfield|brownfield> --module <name>`. On a hit (its `kit_version` still matches the current content of every routing doc — any doc edit changes it and invalidates every cached entry at once), reuse the cached route and doc list instead of re-reading those files. On a miss or a stale hit, do the full doc read as usual, then write the decision back with `agentic_runtime.cli route-cache-put --work-type <type> --project-type <...> --module <name> --file <decision.json>` (the JSON file holding at least `route`, `workflow_doc`, `skill_docs`) so the next session for the same (work type, project type, module) skips the re-read. This is separate from `agentic/data/project-context/` (items 4-6): that holds discovered facts about the target codebase; this holds which meta-docs and route apply to a work classification.
12. Use skills under `agentic/kit/skills/` as reusable specialist workflows. For implementation-stage work, pick it up through the matching domain persona under `agentic/kit/agents/` (FE, Mobile, BE, DB/Integration, QA, Security/DevOps — see `agentic/kit/agents/README.md`); a persona composes existing skills and scopes which tasks it takes, it does not replace them.
13. Record agent start/end timing and relevant task telemetry through the harness.
14. Preserve traceability from request -> requirements -> design -> tasks -> implementation -> QA -> release.
15. Commit per `agentic/kit/policies/commit-policy.md`: only after a governed task finishes with checks green (`Commit-Trigger: task-finish`, one task = one commit) or when the user explicitly asks (`Commit-Trigger: user-request`). Build the message with `agentic_runtime.cli commit-message` (Conventional Commits + `Work-Item`/`Task`/`Run`/`Commit-Trigger` trailers), then `agentic_runtime.cli record-commit RUN_ID` when a run exists. `close-session` logs every commit since the previous session under `## Commits`. Never push, amend, or skip hooks without an explicit ask.

## Input modes

The system supports both:

- Prompt-first: a developer describes a feature, CR, bug, or hotfix in a prompt.
- Document-first: a developer points to an existing FEATURE.md, CR.md, BUG.md, or HOTFIX.md.

Both modes must normalize into a canonical work item before downstream execution.

## Project types

- **Greenfield**: no pre-existing implementation to reconcile against for the work at
  hand -- a new repo, or a new module/feature area in an existing repo with nothing to
  discover yet. Context starts at `MISSING`; there is no legacy code, architecture, or
  data model to recover before building. Use the full feature lifecycle
  (`agentic/kit/workflows/greenfield.md`).
- **Brownfield/legacy**: an existing implementation already governs the area being
  touched -- prior code, tests, data, and architectural constraints exist and must be
  discovered and reconciled before changing anything. Use context-first, incremental
  discovery and baseline recovery only where needed (`agentic/kit/workflows/brownfield.md`);
  do not re-run full discovery on context that is already `AVAILABLE` and fresh.

Classify per work item, not per repo: a brownfield repo can still take a genuinely
greenfield feature (new module, no existing code to reconcile), and a greenfield repo's
second feature is brownfield the moment the first one lands.

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
