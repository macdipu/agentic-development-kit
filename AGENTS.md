# Agentic Development Instructions

This file is the canonical repository-level instruction entrypoint for agentic development. The managed block below is `agentic/kit/config/AGENTS.fragment.md`, the same text the installer merges into a host AGENTS.md.

<!-- agentic-kit:start -->
# Agentic kit workflow

CLI below = `python3 agentic/kit/runtime/python/agentic_runtime/cli.py`. Output is compact; add `--full` only when you need the whole record.

## Core behavior

1. Midflight first. The `SessionStart` hook (hookless: `git pull`, then `CLI pickup`) reports an unclosed task, a `RUNNING`/`BLOCKED` run, other clones' claims, commits waiting upstream, and the handoff note. Resume what it reports; never start a new run for that work item. A run another machine handed off: `CLI resume RUN_ID` (pulls, claims, adopts its task). `--takeover --reason` only with the user's OK. Damaged state: `CLI doctor`.
2. Leaving for another machine: `CLI handoff` (commits all work + state, frees the claim, pushes). Before compaction, update docs this session touched and shrink remaining work to the smallest finishable subtask. Hookless session end: `CLI close-session --agent <claude|codex> --status <...> --task ... --completed ... --next-action ...`.
3. While a run is `RUNNING`/`BLOCKED`, change code only inside a task (`CLI task-start RUN_ID --skill <skill>`); the hook denies Write/Edit to code otherwise (and Bash is not a way around it). `agentic/data/` docs stay writable; never hand-edit `.agent/state/` or `.agent/local/`.
4. The current repository is the source project. Use `agentic/data/project-context/` before discovery (`CLI context-check` lists stale entries); reuse fresh context, refresh only stale/missing scope, never audit the whole repo per task.
5. Prefer existing implementations and patterns. Never invent business rules.
6. Never infer approval. Only explicit user approval counts; record it with `CLI approve RUN_ID --gate <gate> --comment "<quote>"` (`--by` defaults to the git user; pass it only for another reviewer). Never grant yourself a budget (`adjust-budget` needs the user's OK). `approve --auto` is technical-gate only.
7. Route via `agentic/kit/workflows/routing.md`, cache first: `CLI route-cache-get --work-type <t> --project-type <greenfield|brownfield> --module <m>`; on a hit reuse its route and doc list without reading workflow/persona/SKILL docs; on a miss read them, then `route-cache-put ... --file decision.json` (`route`, `workflow_doc`, `skill_docs`).
8. Skills: `agentic/kit/skills/`; run core-tier skills always, on-demand ones only when needed (`agentic/SKILL-CATALOG.md`). Implementation goes through the matching persona in `agentic/kit/agents/`.
9. Do the work inside the task; a task closed with no governed tool call is flagged `post_hoc`, not execution time.
10. Traceability: request -> requirements -> design -> tasks -> implementation -> QA -> release.
11. Commit per `agentic/kit/policies/commit-policy.md`: after a task finishes green (`task-finish`, one task = one commit) or on explicit user ask (`user-request`), with `CLI commit --type ... --subject ... --trigger ... --run RUN_ID --task T --path <file>...` (`--trailer` for attribution). Never pipe `commit-message` into git. Task ends also make a state-only commit. Never push, amend, or skip hooks without an ask (`handoff` pushes because the user runs it to switch machines).

## Work classification

- Prompt-first or document-first (FEATURE/CR/BUG/HOTFIX.md); both normalize to a canonical work item.
- Project type is per work item: greenfield -> full lifecycle (`agentic/kit/workflows/greenfield.md`); brownfield -> context-first incremental (`agentic/kit/workflows/brownfield.md`).
- Never pick hierarchy or Sprint Planning from request type alone: classify the minimum work level, then sprint handling. Approved tasks execute without recreating planning artifacts.
- Generated artifacts belong under `agentic/data/`; kit code under `agentic/kit/`. In local-harness mode the harness owns state, approvals, freshness, limits, and timing -- never substitute model judgment.
<!-- agentic-kit:end -->
