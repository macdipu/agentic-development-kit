# Reference harness runtime

This Python 3.10+ standard-library runtime governs local workflow state and trusted adapter calls. It does not include a model provider, background worker, device driver, or deployment adapter. A CLI `start` creates state; it does not start an agent.

See the [production readiness checklist](production-readiness.md) for what organization-specific infrastructure this reference runtime still needs before a shared/production deployment.

## Capability matrix

| Capability | Implemented local behavior | Boundary |
|---|---|---|
| Workflow | Work-type routes, ordered transitions, terminal states, ready stage results | Coarse stages; no automatic business or sprint classification |
| Persistence | One JSON file per run (`runs/<run_id>.json`); a `transaction()` context commits run, checkpoint, audit together via write-temp+atomic-replace, guarded by a per-run lock file | Local store; writable by the operator, not immutable audit storage; the lock guards one machine, not cross-machine access |
| Approvals | Explicit decisions bound to scope revision, evidence prerequisites, rejection/revocation | `--by` is an operator assertion, not authenticated identity or RBAC |
| Context | Explicit scoped file hashes detect dirty changes and deletions | Caller selects sufficient files; no automatic dependency discovery or semantic freshness |
| Skills | Stage eligibility and SHA-256 pins for instructions, references, shared contract | Trusted local files and adapters; no automatic model execution |
| Results | Handoff shape, statuses, evidence presence, blocker consistency | Evidence truth and domain correctness require review |
| Tools | Explicit read/artifact/code/check/preview permissions, side-effect classification, idempotency reservation, audit, dry-run suppression | Legacy custom handlers may use L0–L6 ceilings; trusted handlers must declare effects correctly |
| Default tools | Read/search, `write_artifact`, `write_file`, `run_command`, `run_preview`; each searched file is contained and commands match complete argv | Trusted local handlers; not OS isolation or race-proof access against hostile filesystem changes |
| Coding-agent gate | A CLI-driven task protocol (`task-start`/`call-tool`/`task-finish`/`task-fail`) plus a Claude Code `PreToolUse` hook (`guard`) that checks native Bash/Write/Edit/NotebookEdit calls against the active task's explicit permissions and full Bash argument allowlist | Enforced only while a task is active and only for the matched tools; a session with no active governed task is unaffected |
| Budgets | Attempts per scope/stage/skill, tool calls per task, elapsed task deadline | Cooperative checks before/after calls; cannot kill a blocked process |
| Cancellation | Terminal run, no new calls or accepted late result | Cannot undo an external effect or terminate an arbitrary adapter |
| Recovery | Explicit interruption acknowledgment; failed/unknown tool outcomes are not replayed | Operator must stop the old worker and reconcile external effects |
| Timing | Start/end/failure/cancel/interruption events, duration for normal/failed adapters, retry count; `timing RUN_ID [--task]` queries recorded events and computed durations | Queue, approval-wait, active-vs-tool time attribution are not implemented |
| Redaction | Best-effort structured field and string masking for context, results, and error/audit payloads | Not comprehensive DLP; tool arguments reach the trusted handler unchanged |
| Dependency closure | `impact MODULE... --edges edges.json` expands a transitive dependency closure from a caller-supplied module graph | Not connected to automatic dependency discovery; edges must be supplied explicitly |
| Cross-agent handoff | `pickup`/`close-session` read/write `.agent/HANDOFF.md` + `.agent/sessions/*.md` (agent-handoff compatible, git-tracked), structured by task/completed/changed_files/tests/blockers/decisions/next_action plus the git-configured operator and a git-derived commit log | Handoff notes, session records (with a full `## Runtime` section) and the run store all live under `.agent/`, git-tracked, so another machine or platform resumes after `git pull` |
| Commits | `commit-message` builds a Conventional Commits message with `Work-Item`/`Task`/`Run`/`Commit-Trigger` trailers; `record-commit RUN_ID` appends a `COMMIT_RECORDED` audit event | Does not run `git commit` or decide when to commit; see [commit policy](../policies/commit-policy.md) |
| Production | No production stage or L7 tool registration | External production integration is intentionally unsupported |

The caller, adapter code, tool registrations, configuration, and database form one local trust boundary. Direct Python, shell, model-provider, or database access outside these APIs bypasses the controls. Use process isolation, authenticated approval services, least-privilege credentials, and durable infrastructure before shared autonomous execution.

## Start and inspect

From the repository root:

```sh
python3 agentic/kit/runtime/python/agentic_runtime/cli.py init
python3 agentic/kit/runtime/python/agentic_runtime/cli.py start --project my-app --type device_preview --title "Preview the home screen" --repo .
python3 agentic/kit/runtime/python/agentic_runtime/cli.py list
```

Copy the returned run ID. Commands below use `RUN_ID` as a placeholder, and paths must refer to your actual reviewed artifacts:

```sh
python3 agentic/kit/runtime/python/agentic_runtime/cli.py show RUN_ID
python3 agentic/kit/runtime/python/agentic_runtime/cli.py eligible RUN_ID
python3 agentic/kit/runtime/python/agentic_runtime/cli.py result RUN_ID --skill prompt-intake-adapter --file path/to/intake-result.json
python3 agentic/kit/runtime/python/agentic_runtime/cli.py transition RUN_ID CONTEXT
python3 agentic/kit/runtime/python/agentic_runtime/cli.py context RUN_ID path/to/module-context.md path/to/affected-source-file
python3 agentic/kit/runtime/python/agentic_runtime/cli.py result RUN_ID --skill baseline-verifier --file path/to/context-result.json
python3 agentic/kit/runtime/python/agentic_runtime/cli.py transition RUN_ID PREVIEW
python3 agentic/kit/runtime/python/agentic_runtime/cli.py result RUN_ID --skill device-preview-agent --file path/to/preview-result.json
python3 agentic/kit/runtime/python/agentic_runtime/cli.py transition RUN_ID COMPLETED
```

`result` validates and records an already-produced [handoff envelope](../skills/RESULT-CONTRACT.md). It does not execute the selected specialist or independently inspect its evidence. Its timing measures submission processing, not the earlier agent work. Use the adapter API below to measure execution and govern tools. The preview's result must be `PREVIEW_READY`, with visual evidence, before completion.

Query recorded task durations, or expand a caller-supplied module dependency closure, at any time (including on a completed run):

```sh
python3 agentic/kit/runtime/python/agentic_runtime/cli.py timing RUN_ID
python3 agentic/kit/runtime/python/agentic_runtime/cli.py timing RUN_ID --task TASK_ID
python3 agentic/kit/runtime/python/agentic_runtime/cli.py impact auth billing --edges path/to/edges.json
```

`edges.json` maps a module name to the list of modules that depend on it (e.g. `{"auth": ["billing"], "billing": ["invoicing"]}`); `impact` walks that graph from the given modules and returns the full affected set. The runtime does not discover these edges itself — supply them from `module-context.yaml`'s `dependencies` field or another source of truth.

Default state lives under `.agent/runtime/runs/` (git-tracked; paths inside are stored relative so the store resolves on any checkout). Put `--store-dir /path/to/runs` before the subcommand to select another store directory. Invalid input and denied transitions return a nonzero exit code and leave the previous stage intact. `BLOCKED` results can be retried within budget; unknown stage strings are rejected.

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
python3 agentic/kit/runtime/python/agentic_runtime/cli.py approve RUN_ID --gate technical --by actual-reviewer --comment "Reference to the decision"
python3 agentic/kit/runtime/python/agentic_runtime/cli.py approve RUN_ID --gate technical --by actual-reviewer --decision REJECTED --comment "Reason"
```

Never generate approval just because a file exists. Replacing prerequisite evidence revokes related approvals. `reopen RUN_ID --reason "Changed scope"` resets to CONTEXT, increments scope revision, and invalidates downstream results and previous approvals. It preserves the intake result and audit history. Terminal runs require a new run.

A scope refresh (`context RUN_ID <paths>`) while the run already sits at CONTEXT, TECHNICAL, IMPLEMENTATION, QA, or UAT does not force a reopen: it pops just that stage's own result and revokes only the gates whose evidence depends on it (CONTEXT/TECHNICAL revoke technical+release+uat; IMPLEMENTATION/QA revoke release+uat; UAT revokes uat+release), leaving earlier-granted approvals and the rest of the evidence chain intact. Any other stage still requires `reopen`; that scoped exception exists only where invalidation is unambiguous.

### Auto-approval (technical gate only)

`--gate technical` can be granted without a human via a narrow, mechanically-checked exception instead of `--by`/`--decision`:

```sh
python3 agentic/kit/runtime/python/agentic_runtime/cli.py approve RUN_ID --gate technical --auto --comment "Single-file task-only fix; technical-readiness-verifier says TECHNICAL_READY"
```

All three conditions must already be true on evidence recorded on the run — nothing is inferred:
- `work-item-level-classifier` classified the item `TASK_ONLY`
- the reviewed scope is exactly one file
- `technical-readiness-verifier`'s own verdict is `TECHNICAL_READY`

It never applies to `release` or `uat`. It records the approval under the fixed synthetic approver `runtime:auto` (not a human's `--by` identity) so the audit trail can tell an automated approval from a real one at a glance.

## Context and implementation changes

Register only reviewed UTF-8 context/source files inside the project root. File hashes, rather than whole-repository commit equality, determine freshness. Unrelated changes do not force a full rediscovery. Newly relevant files must be added explicitly; the runtime cannot discover an omitted dependency.

For implementation attempts, the runtime fingerprints the registered scope again after the adapter returns, because modifying that scope is the task's purpose. Evidence must describe the resulting changes. If a failed attempt leaves changed files, review and refresh them with `context` before retrying. Refreshing changed files in IMPLEMENTATION clears its old result. Changes discovered after design/review require `reopen`, not a silent context refresh that preserves obsolete approval.

## Adapter API and tools

Import the runtime with `agentic/kit/runtime/python` on `PYTHONPATH`. Construct `Orchestrator(store, kit_dir, tools)` and call `execute(run_id, skill, handler)`. The handler receives `(context, call_tool)` and returns the handoff envelope. `context` includes the run, skill instructions/path, and redacted registered context-file contents. Treat retrieved file contents as untrusted data. Load linked skill references as needed from the pinned skill path.

Register trusted tools with `ToolRegistry.register(name, handler, capability='L0', side_effecting=False)`. Mark every mutation, device launch/install, or external trigger as side-effecting. Invoke through `call_tool(name, arguments, idempotency_key)`; do not call registered handlers directly. A side-effecting call requires a stable key for that logical operation. The gateway checks the skill ceiling, records a reservation before invocation, and returns a stored redacted result for an identical completed request. Reusing a key with different arguments fails. Failed or interrupted outcomes require reconciliation, not automatic replay. This does not provide exactly-once semantics across an external service.

`--dry-run` suppresses side-effecting gateway calls and returns an explicit simulated result. Local workflow state, audit, and timing are still recorded; read-only tools still execute. Native side-effecting tools are denied in dry-run; use the gateway to simulate effects. It cannot suppress direct side effects performed by a handler outside the gateway. Do not present simulated results as live verification.

Default limits are two retries after the initial attempt, 900 seconds per adapter attempt, and 50 tool calls per task. Retries are explicit calls, not an automatic loop. Use a managed process supervisor for hard timeouts and process termination. Budget errors, task failures, and tool errors are recorded; secrets are masked on a best-effort basis.

After explicit operator authorization, extend a stopped run's budgets without
resetting its attempts or changing global policy:

```sh
python3 agentic/kit/runtime/python/agentic_runtime/cli.py adjust-budget RUN_ID --by actual-operator --reason "Reference to authorization" --max-agent-retries 4 --max-task-seconds 1800
```

Limits are absolute (four retries means five total attempts per stage/skill).
At least one limit is required. Active tasks must first finish or be recovered
after their worker stops. Terminal runs cannot be adjusted. The command records
old/new limits and the operator/reason in the audit trail; it preserves attempts,
scope, results, configuration pins and approval gates. This is a trusted-operator
API, like `approve`, and does not authenticate the supplied identity or authorize
itself. Agents must not grant themselves extensions without user authorization.

## Coding-agent integration

Two adapters route real work through the harness instead of only recording a pasted result.

**A Python or subprocess-driven adapter** calls `orch.execute(run_id, skill, handler)` in-process (above), or drives the same lifecycle across process boundaries with the CLI:

```sh
python3 agentic/kit/runtime/python/agentic_runtime/cli.py task-start RUN_ID --skill implementation-agent
python3 agentic/kit/runtime/python/agentic_runtime/cli.py call-tool RUN_ID TASK_ID --name write_file --args '{"path":"lib/foo.dart","content":"..."}' --idempotency-key foo-1
python3 agentic/kit/runtime/python/agentic_runtime/cli.py task-finish RUN_ID TASK_ID --file path/to/result.json
```

`call-tool` uses the default tools above (`read_file`, `list_directory`, `search_text`, `write_file`, `run_command`), bound to the run's registered repo root and the allowlist in `config/allowed-commands.json`. An error before `task-finish` should be reported with `task-fail RUN_ID TASK_ID --error "..."` rather than left active; recover the marker only after confirming the worker actually stopped.

**Claude Code integration:** installing with `--mode local-harness --agent claude`
merges the packaged hooks into host settings. To wire them without a full install
(for example, in the kit repo itself), run `cli.py install-hooks [--repo PATH]`: it
merges `config/hooks.json` into `.claude/settings.json`, preserving existing settings
and hooks, and is a no-op when already present; then run `doctor` and restart the
Claude session. The tool hook checks the active task,
pins, approvals, timeout, permissions, complete command arguments, and document/code
write paths before Bash/Write/Edit/NotebookEdit calls. With no active marker, normal
ad hoc use is unaffected. Unreadable markers, missing state, and internal gate errors
deny matched calls until the operator diagnoses and recovers the task.

The CLI, tool gate, session hook, compaction hook, and stop hook share one path
definition. CLI task markers are reserved exclusively and replaced atomically;
finishing another run cannot clear the current marker. The session hook reports
unknown state explicitly. The compaction hook persists checkpoint/audit together
and reminds the agent to record remaining work. It does not block compaction if
recording fails. The stop hook (below) writes cross-agent handoff notes when a
governed task is active; it does not block `Stop` either.

Only matched native tools are intercepted. These hooks are cooperative controls,
not process isolation. Use a supervising terminal for lifecycle CLI commands and
recovery when a native tool gate prevents them. CLI adapters use
`task-start / call-tool / task-finish` directly.

Run `python3 agentic/kit/runtime/python/agentic_runtime/cli.py doctor` after adoption
or upgrade. It separates installed configuration, isolated hook execution, storage
checks, unavailable project tools, and platform limitations. Actual agent-platform
invocation still needs one observed session.

## Cross-agent-platform handoff

Separate from this runtime's own governed-run store, and compatible with
[ishipu/agent-handoff](https://github.com/ishipu/agent-handoff)'s file format (a
Python-native port here, not a Node dependency): `.agent/HANDOFF.md` and
`.agent/sessions/*.md` are plain Markdown, git-tracked, so any agent platform —
Claude Code, Codex, or another tool that speaks the same convention — can pick up
where a different one left off after `git pull`, with no server and no shared
runtime. The governed-run ledger sits beside them in `.agent/runtime/`
(active-task pointer, `runs/*.json`, route cache), also git-tracked, and each
session record carries a `## Runtime` section rendering that run's full ledger
(stages and results, every approval with its comment, timing per skill,
attempts, budget overrides, context hashes, skill pins, checkpoints, every audit
event with its redacted payload, tool calls). The pointer stores its store
directory relative to itself and each run stores `metadata.repo` relative to
the store, so `git pull` on another machine resumes the same run. Only
`*.lock`, `*.tmp`, and `logs/` are gitignored. Git provides no cross-machine
lock: finish and push on one machine before resuming on another.

`init_project.py` scaffolds `.agent/`, `.claude/skills/agent-handoff/SKILL.md`,
and `.codex/skills/agent-handoff/SKILL.md` on every install, regardless of the
chosen `--agent`, so a Codex user can join a Claude-installed project (or vice
versa) without reinstalling.

Before starting work, read the current handoff state:

```sh
python3 agentic/kit/runtime/python/agentic_runtime/cli.py pickup
```

Prints `.agent/HANDOFF.md` and the latest `.agent/sessions/*.md` entry. Claude
Code gets this automatically in the `SessionStart` hook's `additionalContext`;
`pickup` is for hookless CLIs (including Codex) or manual use.

When finishing a work session, record it:

```sh
python3 agentic/kit/runtime/python/agentic_runtime/cli.py close-session \
  --agent claude --status BLOCKED --task "Implement token refresh" \
  --completed "Added refresh flow" \
  --changed-files src/auth.ts src/api.ts \
  --tests "npm test passes" \
  --blockers "API retry logic missing" \
  --decisions "Used rotating refresh tokens" \
  --next-action "Implement retry handling"
```

`--agent` is exactly `claude` or `codex` (matching upstream's own restriction, so
these files stay valid input to the real `agent-handoff` CLI too). `--status` is
one of `RUNNING`/`BLOCKED`/`COMPLETED`/`CANCELLED` and is required -- there is no
default, so a hookless close can't silently claim `COMPLETED` for a session that
didn't finish. Structured fields, not one free-form summary: `--agent`/`--status`/
`--task`/`--completed` are required; the rest are optional but each gets its own
heading in the written files, so a picking-up agent reads a specific field instead
of parsing prose. The git-configured
operator (`git config user.name`/`user.email`) is captured automatically
alongside the `claude`/`codex` platform tag, since more than one person can
drive either platform on a shared project.

This rewrites `.agent/HANDOFF.md` and appends a new
`.agent/sessions/<timestamp>-<agent>.md`. Claude Code does this automatically via
the `Stop` hook whenever a governed task is active (never blocks `Stop`, fails
open on error); on a hookless CLI, run `close-session` yourself before ending
the session.

Both files also get a `## Commits` section derived from git, not from the
caller: every commit since the previous session record's HEAD (the last 20 when
there is no usable previous record), each tagged with its `Commit-Trigger`,
`Work-Item`, and `Task` trailers, or `[no Commit-Trigger]` for a commit made
outside the [commit policy](../policies/commit-policy.md).

## Commits

```sh
python3 agentic/kit/runtime/python/agentic_runtime/cli.py commit-message \
  --type fix --scope billing --subject "round tax per line item" \
  --body "Totals drifted by a cent on multi-line invoices." \
  --trigger task-finish --work-item BUG-7 --task T-2 --run RUN_ID | git commit -F -
python3 agentic/kit/runtime/python/agentic_runtime/cli.py record-commit RUN_ID
```

`commit-message` rejects unknown types/triggers, a header over 72 characters, and a
trailing period. `record-commit` reads the commit from the run's repo and refuses
one without a valid `Commit-Trigger` trailer. Neither command commits or pushes.

## Routing-decision cache

Separate from `agentic/data/project-context/` (discovered facts about the target
codebase) and from the governed-run store: a small git-tracked cache
(`.agent/runtime/route-cache.json`) that lets a session skip
re-reading `AGENTS.md`'s matched `workflows/*.md`, a persona `AGENT.md`, and
`SKILL.md` files in full for a (work type, project type, module) triple it has
already routed before.

```sh
python3 agentic/kit/runtime/python/agentic_runtime/cli.py route-cache-get \
  --work-type bug --project-type brownfield --module auth
```

On a hit (`"hit": true`), reuse `entry.decision` instead of re-reading those
docs. On a miss, do the full doc read as usual, then write the decision back:

```sh
python3 agentic/kit/runtime/python/agentic_runtime/cli.py route-cache-put \
  --work-type bug --project-type brownfield --module auth --file decision.json
```

`decision.json` is any JSON object; keep at least `route`, `workflow_doc`, and
`skill_docs` so the next session has enough to skip the re-read. Invalidation
is one aggregate content hash (`kit_version`) over every routing-relevant
doc — editing any one of them invalidates every cached entry at once, so a
kit upgrade or an AGENTS.md edit can never serve a stale decision. Force a
clean slate (e.g. right after upgrading the kit) with:

```sh
python3 agentic/kit/runtime/python/agentic_runtime/cli.py route-cache-clear
```

## Permissions and commands

`agentic/kit/config/permissions.json` supplies independent per-skill permissions:

| Permission | Responsibility |
|---|---|
| read | Inspect project files |
| write_artifact | Write Markdown/JSON/YAML/text/CSV in project context, work-item, or artifact directories |
| modify_code | Modify project source through write_file/native writes |
| run_check | Execute an exactly registered local check |
| preview | Execute an exactly registered preview command |

Document generators can write artifacts without source-write permission.
Implementation and baseline specialists can execute checks. Code review and QA do
not receive source-write permission. Direct writes into Git internals are denied.

Default tools declare their permission at registration. A custom tool can use
`permission='run_check'` (for example); older custom registrations without an
explicit permission retain their L0–L6 ceiling behavior. Production levels remain
unsupported.

Register complete argument lists in `agentic/kit/config/allowed-commands.json`:

```json
{
  "commands": [
    {"argv": ["python3", "-m", "unittest", "discover", "-s", "tests"], "permission": "run_check"},
    {"argv": ["flutter", "run", "-d", "reviewed-device-id", "--detach"], "permission": "preview"}
  ]
}
```

Replace the illustrative device ID and include the project's variant/environment
arguments. Preview commands must finish within the command timeout; detached launch
commands leave the app available for inspection. Interactive hot-reload sessions
require a managed host adapter. No SDK or target is selected by the allowlist.

`run_command` accepts read/check rules; `run_preview` accepts preview rules.
Extra arguments are permitted only when the entire resulting argv matches a rule.
Legacy string rules are accepted as exact check commands. Configure rules before
starting a run: modifying permissions or commands invalidates existing pins.

## Cancel, recover, and upgrade

```sh
python3 agentic/kit/runtime/python/agentic_runtime/cli.py cancel RUN_ID
python3 agentic/kit/runtime/python/agentic_runtime/cli.py recover RUN_ID --reason "Worker stopped; effects reconciled"
```

If a marker is damaged, first stop its worker and reconcile the store from a
supervising terminal. After recovering active tasks, use
`python3 agentic/kit/runtime/python/agentic_runtime/cli.py repair-marker --workers-stopped --reason "Recovery evidence"`.
Use `--store-dir` before the subcommand for a custom store. The command refuses to clear
a marker while that store has active tasks and retains the old marker as a
recovery artifact. It is an operator acknowledgment, not automatic worker termination.

A cancelled run is terminal. Recovery applies to an active marker left by an interrupted worker; stop that worker first. Recovery clears the marker and records interruption, without replaying a call or resetting attempt counts. Callbacks already running may finish externally even after cancellation; late results are not accepted.

Read the [upgrade notes](../../ADOPTION.md#upgrade-an-existing-installation) before opening old state. The per-run JSON files carry no schema version; a mismatched shape simply won't match the current WorkflowRun fields, and does not turn old approvals into current authorization.

## Verification

```sh
sh agentic/kit/scripts/validate-kit.sh
```

Checks packaging, permissions, Markdown links and literal source paths, then runs the isolated smoke demo and behavioral tests for runtime policy, approvals, retries, cancellation, persistence rollback, hook execution, adoption, upgrades, installer recovery, and production evidence. The legacy delivery fixture reproduces a defect, modifies code, and executes review/QA with real checks and explicitly synthetic approvals. Run it separately with `python3 agentic/kit/examples/legacy-delivery.py`.
