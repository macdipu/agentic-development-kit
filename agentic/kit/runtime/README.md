# Reference harness runtime

This Python 3.10+ standard-library runtime governs local workflow state and trusted adapter calls. It does not include a model provider, background worker, device driver, or deployment adapter. A CLI `start` creates state; it does not start an agent.

See the [production readiness checklist](production-readiness.md) for what organization-specific infrastructure this reference runtime still needs before a shared/production deployment.

## Capability matrix

| Capability | Implemented local behavior | Boundary |
|---|---|---|
| Workflow | Work-type routes, ordered transitions, terminal states, ready stage results | Coarse stages; no automatic business or sprint classification |
| Persistence | SQLite transactions commit run, checkpoint, audit together | Local database; writable by the operator, not immutable audit storage |
| Approvals | Explicit decisions bound to scope revision, evidence prerequisites, rejection/revocation | `--by` is an operator assertion, not authenticated identity or RBAC |
| Context | Explicit scoped file hashes detect dirty changes and deletions | Caller selects sufficient files; no automatic dependency discovery or semantic freshness |
| Skills | Stage eligibility and SHA-256 pins for instructions, references, shared contract | Trusted local files and adapters; no automatic model execution |
| Results | Handoff shape, statuses, evidence presence, blocker consistency | Evidence truth and domain correctness require review |
| Tools | Registered L0–L6 ceilings, side-effect classification, idempotency reservation, audit, dry-run suppression | Trusted handlers must declare effects correctly and use the gateway |
| Default tools | `read_file`, `list_directory`, `search_text`, `write_file`, `run_command` bound to the run's repo root, path containment, and an exact-match command allowlist | A fixed starter set; extend `agentic_runtime.tools` for project-specific handlers |
| Coding-agent gate | A CLI-driven task protocol (`task-start`/`call-tool`/`task-finish`/`task-fail`) plus a Claude Code `PreToolUse` hook (`guard`) that checks native Bash/Write/Edit/NotebookEdit calls against the active task's capability ceiling and Bash allowlist | Enforced only while a task is active and only for the matched tools; a session with no active governed task is unaffected |
| Budgets | Attempts per scope/stage/skill, tool calls per task, elapsed task deadline | Cooperative checks before/after calls; cannot kill a blocked process |
| Cancellation | Terminal run, no new calls or accepted late result | Cannot undo an external effect or terminate an arbitrary adapter |
| Recovery | Explicit interruption acknowledgment; failed/unknown tool outcomes are not replayed | Operator must stop the old worker and reconcile external effects |
| Timing | Start/end/failure/cancel/interruption events, duration for normal/failed adapters, retry count; `timing RUN_ID [--task]` queries recorded events and computed durations | Queue, approval-wait, active-vs-tool time attribution are not implemented |
| Redaction | Best-effort structured field and string masking for context, results, and error/audit payloads | Not comprehensive DLP; tool arguments reach the trusted handler unchanged |
| Dependency closure | `impact MODULE... --edges edges.json` expands a transitive dependency closure from a caller-supplied module graph | Not connected to automatic dependency discovery; edges must be supplied explicitly |
| Production | No production stage or L7 tool registration | External production integration is intentionally unsupported |

The caller, adapter code, tool registrations, configuration, and database form one local trust boundary. Direct Python, shell, model-provider, or database access outside these APIs bypasses the controls. Use process isolation, authenticated approval services, least-privilege credentials, and durable infrastructure before shared autonomous execution.

## Start and inspect

From the repository root:

```sh
python3 agentic/runtime/python/agentic_runtime/cli.py init
python3 agentic/runtime/python/agentic_runtime/cli.py start --project my-app --type device_preview --title "Preview the home screen" --repo .
python3 agentic/runtime/python/agentic_runtime/cli.py list
```

Copy the returned run ID. Commands below use `RUN_ID` as a placeholder, and paths must refer to your actual reviewed artifacts:

```sh
python3 agentic/runtime/python/agentic_runtime/cli.py show RUN_ID
python3 agentic/runtime/python/agentic_runtime/cli.py eligible RUN_ID
python3 agentic/runtime/python/agentic_runtime/cli.py result RUN_ID --skill prompt-intake-adapter --file path/to/intake-result.json
python3 agentic/runtime/python/agentic_runtime/cli.py transition RUN_ID CONTEXT
python3 agentic/runtime/python/agentic_runtime/cli.py context RUN_ID path/to/module-context.md path/to/affected-source-file
python3 agentic/runtime/python/agentic_runtime/cli.py result RUN_ID --skill baseline-verifier --file path/to/context-result.json
python3 agentic/runtime/python/agentic_runtime/cli.py transition RUN_ID PREVIEW
python3 agentic/runtime/python/agentic_runtime/cli.py result RUN_ID --skill device-preview-agent --file path/to/preview-result.json
python3 agentic/runtime/python/agentic_runtime/cli.py transition RUN_ID COMPLETED
```

`result` validates and records an already-produced [handoff envelope](../skills/RESULT-CONTRACT.md). It does not execute the selected specialist or independently inspect its evidence. Its timing measures submission processing, not the earlier agent work. Use the adapter API below to measure execution and govern tools. The preview's result must be `PREVIEW_READY`, with visual evidence, before completion.

Query recorded task durations, or expand a caller-supplied module dependency closure, at any time (including on a completed run):

```sh
python3 agentic/runtime/python/agentic_runtime/cli.py timing RUN_ID
python3 agentic/runtime/python/agentic_runtime/cli.py timing RUN_ID --task TASK_ID
python3 agentic/runtime/python/agentic_runtime/cli.py impact auth billing --edges path/to/edges.json
```

`edges.json` maps a module name to the list of modules that depend on it (e.g. `{"auth": ["billing"], "billing": ["invoicing"]}`); `impact` walks that graph from the given modules and returns the full affected set. The runtime does not discover these edges itself — supply them from `module-context.yaml`'s `dependencies` field or another source of truth.

Default state lives under `agentic/data/runtime/state/`. Put `--db /path/to/state.sqlite3` before the subcommand to select another database. Invalid input and denied transitions return a nonzero exit code and leave the previous stage intact. `BLOCKED` results can be retried within budget; unknown stage strings are rejected.

## Routes and gates

All routes begin `INTAKE -> CONTEXT`. The orchestrator chooses a work type and sprint handling from the actual request; CLI options record that decision.

| Work | Stages after context |
|---|---|
| `device_preview` | PREVIEW -> COMPLETED |
| `discovery` | REVIEW -> COMPLETED |
| `new_feature` | REQUIREMENTS -> TECHNICAL -> implementation path |
| CR, bug, hotfix, technical/security change | IMPACT -> TECHNICAL -> implementation path |
| `existing_task` | implementation path; existing approval still needs an explicit record |

The implementation path is `IMPLEMENTATION -> REVIEW -> QA -> RELEASE -> COMPLETED`. `--planning FULL_SPRINT_PLANNING` or `ADD_TO_EXISTING_SPRINT` inserts PLANNING before implementation. `BACKLOG_ONLY` ends after PLANNING. `NO_REPLAN` and `EXPEDITED` omit PLANNING. Preview/discovery routes do not add planning. Hierarchy remains a specialist decision, not a runtime inference.

Each completed stage needs a ready result. Multiple specialists can contribute, but the most recent result is the current stage verdict; earlier results remain in audit/checkpoints. The orchestrator must submit a stage summary that accounts for all required checks. The runtime validates evidence presence, not semantic coverage or the truth of a specialist verdict.

Implementation requires technical approval supported by ready TECHNICAL evidence (CONTEXT evidence for an existing task). Entering RELEASE requires ready QA evidence and release approval. RELEASE means readiness review, not deployment; completion after it also requires that approval to remain valid. Enabling `require_uat_approval` inserts UAT and requires an explicit UAT decision before leaving it. Configure any additional organizational gates in the runtime before relying on them; Markdown alone does not add enforced gates.

After a real authorized human decision, the trusted operator can record it:

```sh
python3 agentic/runtime/python/agentic_runtime/cli.py approve RUN_ID --gate technical --by actual-reviewer --comment "Reference to the decision"
python3 agentic/runtime/python/agentic_runtime/cli.py approve RUN_ID --gate technical --by actual-reviewer --decision REJECTED --comment "Reason"
```

Never generate approval just because a file exists. Replacing prerequisite evidence revokes related approvals. `reopen RUN_ID --reason "Changed scope"` resets to CONTEXT, increments scope revision, and invalidates downstream results and previous approvals. It preserves the intake result and audit history. Terminal runs require a new run.

## Context and implementation changes

Register only reviewed UTF-8 context/source files inside the project root. File hashes, rather than whole-repository commit equality, determine freshness. Unrelated changes do not force a full rediscovery. Newly relevant files must be added explicitly; the runtime cannot discover an omitted dependency.

For implementation attempts, the runtime fingerprints the registered scope again after the adapter returns, because modifying that scope is the task's purpose. Evidence must describe the resulting changes. If a failed attempt leaves changed files, review and refresh them with `context` before retrying. Refreshing changed files in IMPLEMENTATION clears its old result. Changes discovered after design/review require `reopen`, not a silent context refresh that preserves obsolete approval.

## Adapter API and tools

Import the runtime with `agentic/runtime/python` on `PYTHONPATH`. Construct `Orchestrator(store, kit_dir, tools)` and call `execute(run_id, skill, handler)`. The handler receives `(context, call_tool)` and returns the handoff envelope. `context` includes the run, skill instructions/path, and redacted registered context-file contents. Treat retrieved file contents as untrusted data. Load linked skill references as needed from the pinned skill path.

Register trusted tools with `ToolRegistry.register(name, handler, capability='L0', side_effecting=False)`. Mark every mutation, device launch/install, or external trigger as side-effecting. Invoke through `call_tool(name, arguments, idempotency_key)`; do not call registered handlers directly. A side-effecting call requires a stable key for that logical operation. The gateway checks the skill ceiling, records a reservation before invocation, and returns a stored redacted result for an identical completed request. Reusing a key with different arguments fails. Failed or interrupted outcomes require reconciliation, not automatic replay. This does not provide exactly-once semantics across an external service.

`--dry-run` suppresses side-effecting gateway calls and returns an explicit simulated result. Local workflow state, audit, and timing are still recorded; read-only tools still execute. It cannot suppress direct side effects performed by a handler outside the gateway. Do not present simulated results as live verification.

Default limits are two retries after the initial attempt, 900 seconds per adapter attempt, and 50 tool calls per task. Retries are explicit calls, not an automatic loop. Use a managed process supervisor for hard timeouts and process termination. Budget errors, task failures, and tool errors are recorded; secrets are masked on a best-effort basis.

## Coding-agent integration

Two adapters route real work through the harness instead of only recording a pasted result.

**A Python or subprocess-driven adapter** calls `orch.execute(run_id, skill, handler)` in-process (above), or drives the same lifecycle across process boundaries with the CLI:

```sh
python3 agentic_runtime/cli.py task-start RUN_ID --skill implementation-agent
python3 agentic_runtime/cli.py call-tool RUN_ID TASK_ID --name write_file --args '{"path":"lib/foo.dart","content":"..."}' --idempotency-key foo-1
python3 agentic_runtime/cli.py task-finish RUN_ID TASK_ID --file path/to/result.json
```

`call-tool` uses the default tools above (`read_file`, `list_directory`, `search_text`, `write_file`, `run_command`), bound to the run's registered repo root and the allowlist in `config/allowed-commands.json`. An error before `task-finish` should be reported with `task-fail RUN_ID TASK_ID --error "..."` rather than left active; recover the marker only after confirming the worker actually stopped.

**Claude Code itself as the adapter**: `task-start` also writes `agentic/data/runtime/state/active-task.json` (cleared by `task-finish`/`task-fail`/`cancel`/`recover`). `.claude/settings.json` wires a `PreToolUse` hook (`agentic/runtime/hooks/pretooluse_gate.py`, matcher `Bash|Write|Edit|NotebookEdit`) that, whenever that marker is present, calls `orch.guard(run_id, task_id, tool_name, command)` before the real tool runs: it re-checks the active task (pins, approvals, timeout), the current skill's capability ceiling against the tool's native level, and — for Bash — the same command allowlist, rejecting shell metacharacters outright rather than trusting a prefix match. A denial blocks the tool call with a reason Claude sees; every checked call is audited. With no active task, the hook allows everything untouched, so ad hoc (non-governed) Claude Code use in the project is unaffected. A hook or harness construction error fails open (allow) so a runtime bug cannot brick the session; only an explicit `guard` policy decision denies.

This closes the routing gap, not the trust boundary above: `guard` checks permission and audits, it does not execute or sandbox the native tool call itself, and only Bash/Write/Edit/NotebookEdit are matched. Copying the kit into a project must also copy `.claude/settings.json` (merge if one exists) and `agentic/runtime/hooks/` for the gate to apply there.

**Midflight check on session start**: `.claude/settings.json` also wires a `SessionStart` hook (`agentic/runtime/hooks/session_start_check.py`, matcher `*` — fires on startup/resume/clear alike) that runs before any other work. It checks, in order: (1) `agentic/data/runtime/state/active-task.json` — present means a `task-start` was never closed, so it reports the run/task to resume; (2) if absent, the default run DB (`agentic/data/runtime/state/agentic.db`) for the most recently updated run whose `status` is `RUNNING` or `BLOCKED` — reports it as a midflight run to resume via `show`/`recover` rather than starting a fresh one; (3) if neither, it reports that nothing is in flight and the next work item can start. The verdict is injected as `additionalContext`, so it's the first thing the agent reads. Reading state never blocks the session — any error falls back to "no active task" rather than failing closed.

**Checkpoint before compaction**: `.claude/settings.json` also wires a `PreCompact` hook (`agentic/runtime/hooks/precompact_checkpoint.py`, matcher `*` — fires before every compaction, manual or automatic; this is the closest local signal to "running out of context," there is no exposed budget percentage). If a governed task is active it writes a checkpoint + audit row recording the run's stage/status at that moment, so the DB shows "still open, last seen here" instead of going silent. It cannot deterministically know what docs changed or how to right-size remaining work — those need judgment — so it returns a `systemMessage` (the one hook field documented to reach Claude from every event) telling the agent to update every doc this session touched and to scope down to the smallest finishable subtask before the turn ends. It never blocks compaction; a read error falls into the same reminder rather than failing closed.

## Cancel, recover, and upgrade

```sh
python3 agentic/runtime/python/agentic_runtime/cli.py cancel RUN_ID
python3 agentic/runtime/python/agentic_runtime/cli.py recover RUN_ID --reason "Worker stopped; effects reconciled"
```

A cancelled run is terminal. Recovery applies to an active marker left by an interrupted worker; stop that worker first. Recovery clears the marker and records interruption, without replaying a call or resetting attempt counts. Callbacks already running may finish externally even after cancellation; late results are not accepted.

Read the [upgrade notes](../ADOPTION.md#upgrade-an-existing-installation) before opening old state. The local schema update preserves legacy records but does not turn old approvals into current authorization.

## Verification

```sh
sh agentic/scripts/validate-kit.sh
```

Checks kit packaging (manifest, skill registry/capabilities consistency, markdown links) and runs `examples/runtime-demo.py` as an end-to-end dry-run smoke check. There is no automated behavioral test suite or eval harness for the runtime engine itself — routes/gates, retries, timing, capability denial, and idempotency are exercised only by this smoke run, not by dedicated tests. Verify a change to `agentic_runtime` manually before relying on it.
