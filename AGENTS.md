# Agentic Development Instructions

This file is the canonical repository-level instruction entrypoint for agentic development. The managed block below is `agentic/kit/config/AGENTS.fragment.md`, the same text the installer merges into a host AGENTS.md.

<!-- agentic-kit:start -->
# Agentic kit workflow

## Core behavior

1. Midflight first. The `SessionStart` hook (`agentic/kit/runtime/hooks/session_start_check.py`; run it yourself on a hookless CLI) reports an unclosed task (`.agent/runtime/active-task.json`) or a `RUNNING`/`BLOCKED` run in `.agent/runtime/runs/`: resume it, never start a new run for that work item. It also prints a condensed `.agent/HANDOFF.md` pickup note (hookless: `agentic_runtime.cli pickup`, `--full` for the whole record); a note flagged stale yields to the midflight report. Unknown or damaged state requires explicit recovery (`doctor`). `.agent/` is git-tracked so another machine resumes after `git pull`; finish and push before resuming elsewhere -- git gives no cross-machine lock.
2. Before compaction (`PreCompact` hook or own judgment), update every doc this session touched -- work-item status, README/AGENTS notes, tracked plans -- and shrink remaining work to the smallest subtask that can finish. At session end the `Stop` hook writes HANDOFF + a `.agent/sessions/*.md` record while a governed run is active; otherwise run `agentic_runtime.cli close-session --agent <claude|codex> --status <RUNNING|BLOCKED|COMPLETED|CANCELLED> --task "..." --completed "..." --next-action "..."`.
3. The current repository is the source project.
4. Use `agentic/data/project-context/` before broad discovery.
5. Reuse context that is available and fresh.
6. Refresh only the stale or missing module/feature scope.
7. Never audit the whole repository per task.
8. Prefer existing implementations, shared components, and established patterns.
9. Never invent missing business rules.
10. Never infer human approval. Only explicit user approval (e.g. "yes, approve" in chat) counts; then the agent may record it -- `agentic_runtime.cli approve RUN_ID --gate <gate> --by <user> --comment "..."` or `adjust-budget RUN_ID --by <user> --reason "..."` -- quoting where it was given. `approve --auto` is for technical gates only, never release/UAT.
11. Route via `agentic/kit/workflows/routing.md`. Check the routing cache first: `agentic_runtime.cli route-cache-get --work-type <type> --project-type <greenfield|brownfield> --module <name>`. A hit whose `kit_version` matches -> reuse its route and doc list, skip reading workflow/persona/SKILL docs. Miss or stale -> read them, then `route-cache-put ... --file <decision.json>` (at least `route`, `workflow_doc`, `skill_docs`). The cache holds routing decisions; project-context (4-6) holds codebase facts.
12. Skills live in `agentic/kit/skills/`. Implementation work goes through the matching persona in `agentic/kit/agents/` (FE, Mobile, BE, DB/Integration, QA, Security/DevOps); a persona composes skills, it does not replace them.
13. Record start/end timing and task telemetry through the harness.
14. Preserve traceability: request -> requirements -> design -> tasks -> implementation -> QA -> release.
15. Commit per `agentic/kit/policies/commit-policy.md`: only after a governed task finishes with checks green (`Commit-Trigger: task-finish`, one task = one commit) or on explicit user ask (`user-request`). Build the message with `agentic_runtime.cli commit-message` (Conventional Commits + `Work-Item`/`Task`/`Run`/`Commit-Trigger` trailers), then `record-commit RUN_ID` when a run exists. Never push, amend, or skip hooks without an explicit ask.

## Work classification

- Input: prompt-first or document-first (FEATURE.md, CR.md, BUG.md, HOTFIX.md); both normalize to a canonical work item first.
- Project type is per work item, not per repo. Greenfield: nothing to reconcile, context starts `MISSING`, full lifecycle (`agentic/kit/workflows/greenfield.md`). Brownfield: existing code/tests/data govern the area; context-first incremental discovery, baseline recovery only where needed, no rediscovery of fresh `AVAILABLE` context (`agentic/kit/workflows/brownfield.md`). A repo's second feature is brownfield once the first lands.
- The Workflow Orchestrator picks the next skill from work type, stage, context availability, impact, policy, and approvals.
- Never choose hierarchy or Sprint Planning from request type alone: classify the minimum useful work level, then sprint handling (full Sprint Planning is conditional). Approved tasks execute without recreating Feature/Epic/Story artifacts or replanning unless impact changes materially.
- Generated artifacts and host work items belong under `agentic/data/`; reusable skills, templates, and runtime under `agentic/kit/`.
- In local-harness mode the harness owns workflow state, approvals, policies, context freshness, capability limits, checkpoints, and timing -- never substitute model judgment; verify the install with `doctor`.
<!-- agentic-kit:end -->
