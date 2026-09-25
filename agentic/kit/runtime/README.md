# Reference harness runtime

This Python 3.10+ standard-library runtime governs local workflow state and trusted adapter calls. It does not include a model provider, background worker, device driver, or deployment adapter. A CLI `start` creates state; it does not start an agent.

See the [production readiness checklist](production-readiness.md) for what organization-specific infrastructure this reference runtime still needs before a shared/production deployment.

## Capability matrix

| Capability | Implemented local behavior | Boundary |
|---|---|---|
| Workflow | Work-type routes, ordered transitions, terminal states, ready stage results | Coarse stages; no automatic business or sprint classification |
| Persistence | Append-only event log per run (`.agent/state/runs/<run_id>/events/*.json`): a `transaction()` writes one event with its run/checkpoint/audit operations; state is their replay (cached locally); files are added, never edited, so two machines merge with `git pull`; a terminal run is compacted to one snapshot event; paths stored with `/` on every OS | Writable by the operator, not immutable audit storage; the per-run lock guards one machine (across machines: claims) |
| Cross-machine | `.agent/state/` and `.agent/sessions/` are committed with the project's branches; claims (`.agent/state/claims/<run>/`) hold a run for one clone; `handoff` commits work in progress and pushes; `resume` pulls, claims, and adopts the task; see [Cross-machine work](#cross-machine-work) | A claim protects only as far as git has carried it (commit + push + pull); a claim expires rather than detecting a dead machine |
| Approvals | Explicit decisions bound to scope revision, evidence prerequisites, rejection/revocation; `--by` defaults to, and the operator's own spellings normalize to, the git identity | `--by` is an operator assertion, not authenticated identity or RBAC |
| Context | Explicit scoped file hashes detect dirty changes and deletions | Caller selects sufficient files; no automatic dependency discovery or semantic freshness |
| Skills | Stage eligibility and SHA-256 pins for instructions, references, shared contract | Trusted local files and adapters; no automatic model execution |
| Results | Handoff shape, statuses, evidence presence, blocker consistency; each skill's result is kept per stage (`skill_results`), attributed, beside the stage verdict | Evidence truth and domain correctness require review |
| Tools | Explicit read/artifact/code/check/preview permissions, side-effect classification, idempotency reservation, audit, dry-run suppression | Legacy custom handlers may use L0–L6 ceilings; trusted handlers must declare effects correctly |
| Default tools | Read/search, `write_artifact`, `write_file`, `run_command`, `run_preview`; each searched file is contained and commands match complete argv | Trusted local handlers; not OS isolation or race-proof access against hostile filesystem changes |
| Coding-agent gate | A CLI-driven task protocol (`task-start`/`call-tool`/`task-finish`/`task-fail`) plus a Claude Code `PreToolUse` hook (`guard`) that checks native Bash/Write/Edit/NotebookEdit calls against the active task's explicit permissions and full Bash argument allowlist; with no active task, native code writes are denied while any run is open (`require_task_for_code_writes`); calls the harness does not govern defer to the host's own permission prompts | Matched tools only; Bash without a task is not parsed; not process isolation |
| Budgets | Attempts per scope/stage/skill, tool calls per task, elapsed task deadline; per-skill defaults (`skill_budgets`, e.g. implementation 7200s/4 retries) under run-level operator overrides | Cooperative checks before/after calls; cannot kill a blocked process |
| Cancellation | Terminal run, no new calls or accepted late result | Cannot undo an external effect or terminate an arbitrary adapter |
| Recovery | Explicit interruption acknowledgment; failed/unknown tool outcomes are not replayed | Operator must stop the old worker and reconcile external effects |
| Timing | Start/end/failure/cancel/interruption events, duration for normal/failed adapters, retry count; a task closed within `post_hoc_threshold_seconds` with no governed tool call is flagged `post_hoc` (a record of work done elsewhere, not execution time); `timing RUN_ID [--task]` queries events and durations | Queue, approval-wait, active-vs-tool time attribution are not implemented |
| Redaction | Best-effort structured field and string masking for context, results, and error/audit payloads | Not comprehensive DLP; tool arguments reach the trusted handler unchanged |
| Dependency closure | `impact MODULE... --edges edges.json` expands a transitive dependency closure from a caller-supplied module graph | Not connected to automatic dependency discovery; edges must be supplied explicitly |
| Cross-agent handoff | `pickup`/`close-session` read/write `.agent/HANDOFF.md` + `.agent/sessions/*.md` (agent-handoff compatible), structured by task/completed/changed_files/tests/blockers/decisions/next_action plus the git-configured operator and a git-derived commit log; every `task-finish`/`task-fail` rewrites HANDOFF from the ledger | Committed append-only (`.agent/state/handoffs/`); `.agent/HANDOFF.md` is a local copy |
| Commits | `commit` validates the message first, stages `--path` files, runs `git commit -F` with hooks, and records `COMMIT_RECORDED`; `--trailer` joins attribution to the trailer block; `commit-message` previews; `record-commit` audits a commit made another way | Does not decide when to commit; see [commit policy](../policies/commit-policy.md) |
| Context freshness | `context-check` (and `doctor`) report `context-index.yaml` entries marked reusable whose context file or hashed evidence is missing or changed | Read-only; refreshing context means re-reviewing it |
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

Default state lives under `.agent/state/runs/` (committed; paths inside are stored relative, with `/`, so the store resolves on any checkout and OS). Command output is a compact summary (`run_id`, `stage`, `next_stage`, per-stage status, active task, blockers) to keep agent context small; add `--full` (before or after the subcommand) for the complete record, e.g. `cli.py show RUN_ID --full`. Put `--store-dir /path/to/runs` before the subcommand to select another store directory. Invalid input and denied transitions return a nonzero exit code and leave the previous stage intact. `BLOCKED` results can be retried within budget; unknown stage strings are rejected.

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
- `work-item-level-classifier`'s own result (not another skill's) classified the item `TASK_ONLY`
- the reviewed scope is exactly one file
- `technical-readiness-verifier`'s own result says `TECHNICAL_READY`

Each skill's result is kept per stage in `skill_results`, so both verdicts can be
recorded at the same stage without the second overwriting the first. Both skills
are also eligible at CONTEXT, so an `existing_task` run can qualify.

It never applies to `release` or `uat`. It records the approval under the fixed synthetic approver `runtime:auto` (not a human's `--by` identity) so the audit trail can tell an automated approval from a real one at a glance.

## Context and implementation changes

Register only reviewed UTF-8 context/source files inside the project root. File hashes, rather than whole-repository commit equality, determine freshness. Unrelated changes do not force a full rediscovery. Newly relevant files must be added explicitly; the runtime cannot discover an omitted dependency.

For implementation attempts, the runtime fingerprints the registered scope again after the adapter returns, because modifying that scope is the task's purpose. Evidence must describe the resulting changes. If a failed attempt leaves changed files, review and refresh them with `context` before retrying. Refreshing changed files in IMPLEMENTATION clears its old result. Changes discovered after design/review require `reopen`, not a silent context refresh that preserves obsolete approval.

## Adapter API and tools

Import the runtime with `agentic/kit/runtime/python` on `PYTHONPATH`. Construct `Orchestrator(store, kit_dir, tools)` and call `execute(run_id, skill, handler)`. The handler receives `(context, call_tool)` and returns the handoff envelope. `context` includes the run, skill instructions/path, and redacted registered context-file contents. Treat retrieved file contents as untrusted data. Load linked skill references as needed from the pinned skill path.

Register trusted tools with `ToolRegistry.register(name, handler, capability='L0', side_effecting=False)`. Mark every mutation, device launch/install, or external trigger as side-effecting. Invoke through `call_tool(name, arguments, idempotency_key)`; do not call registered handlers directly. A side-effecting call requires a stable key for that logical operation. The gateway checks the skill ceiling, records a reservation before invocation, and returns a stored redacted result for an identical completed request. Reusing a key with different arguments fails. Failed or interrupted outcomes require reconciliation, not automatic replay. This does not provide exactly-once semantics across an external service.

`--dry-run` suppresses side-effecting gateway calls and returns an explicit simulated result. Local workflow state, audit, and timing are still recorded; read-only tools still execute. Native side-effecting tools are denied in dry-run; use the gateway to simulate effects. It cannot suppress direct side effects performed by a handler outside the gateway. Do not present simulated results as live verification.

Default limits are two retries after the initial attempt, 900 seconds per adapter attempt, and 50 tool calls per task. `skill_budgets` in `platform.json` raises them for skills whose real work is longer (implementation 7200s/4 retries, QA 3600s/3, review and previews 1800s); a run-level `adjust-budget` override still wins. Retries are explicit calls, not an automatic loop. Use a managed process supervisor for hard timeouts and process termination. Budget errors, task failures, and tool errors are recorded; secrets are masked on a best-effort basis.

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
write paths before Bash/Write/Edit/NotebookEdit calls. With no active marker, Write/Edit/
NotebookEdit into project code are denied while any run is `RUNNING`/`BLOCKED` (the
message names the `task-start` to run); documents under `agentic/data/` and `.agent/`,
files outside the project, and Bash stay allowed, and with no open run nothing is
enforced except the ledger's write protection. Only a governed pass returns `allow`;
everything else defers to the host's normal permission prompts. Unreadable markers,
missing state, and internal gate errors deny matched calls until the operator
diagnoses and recovers the task.

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

`.agent/HANDOFF.md` and `.agent/sessions/*.md` are plain Markdown, compatible with
[ishipu/agent-handoff](https://github.com/ishipu/agent-handoff)'s file format (a
Python-native port here, not a Node dependency), so Claude Code, Codex, or another
tool that speaks the same convention can pick up where a different one left off.
`init_project.py` scaffolds `.agent/`, `.claude/skills/agent-handoff/SKILL.md`, and
`.codex/skills/agent-handoff/SKILL.md` on every install, regardless of `--agent`.

Before starting work (the `SessionStart` hook does this for Claude Code):

```sh
git pull
python3 agentic/kit/runtime/python/agentic_runtime/cli.py pickup
```

`pickup` prints a condensed note (~4KB cap): the HANDOFF header, a one-line Runtime
summary, and Task/Completed/Blockers/Decisions/Next Action. The latest session record
is added only when it differs from HANDOFF, and a note about a different run than the
active task is flagged `STALE HANDOFF`. `pickup --full` prints both files verbatim.

HANDOFF is rewritten from the ledger at every `task-finish`/`task-fail` (task, what
finished with which status and evidence, blockers, the result's next step), so the
next agent can continue even if a session crashes or never closes. When finishing a
work session, add the human-level summary:

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

`--agent` is exactly `claude` or `codex` (upstream's restriction). `--status` is
required, so a hookless close cannot silently claim `COMPLETED`. The git-configured
operator is captured beside the platform tag. The session record carries a Runtime
section (stages, approvals, timing, attempts, pins, the latest checkpoint, the last 25
audit events, tool-call counts) and a `## Commits` section derived from git: every
commit since the previous session record's HEAD, each tagged with its
`Commit-Trigger`/`Work-Item`/`Task` trailers, or `[no Commit-Trigger]`. The `Stop` hook
keeps one record per Claude session and writes it only while a governed task is active.

## Cross-machine work

Agent state is committed with the project, in a layout where git can always merge it:

```text
.agent/
├── HANDOFF.md        local copy of the newest handoff (gitignored)
├── sessions/*.md     committed, one file per session
├── state/            committed, append-only
│   ├── runs/<RUN>/events/*.json    one file per change; state = replay
│   ├── claims/<RUN>/*.json         who holds the run
│   └── handoffs/*.md               one file per handoff note (newest 30 kept)
└── local/            gitignored: active-task pointer, clone id, route cache
```

Nothing is ever edited in place (only added, or deleted by compaction), so two
machines that both worked since their last pull merge with a plain `git pull` --
no conflicts in the ledger. Event stamps never go backwards within a run, so a
machine with a lagging clock cannot reorder history.

State reaches the branch three ways: every task end (and `cancel`, `recover`,
completion, `resume`) makes a state-only commit (`chore(agent): ...`,
`Commit-Trigger: agent-state`, `git commit --only` so nothing else you staged is
included; `auto_commit_state` in `config/state.json` turns it off); `cli.py commit`
includes pending state in the task's own commit; and `handoff` commits everything.
Nothing is pushed except by `handoff`.

**Switching machines:**

```sh
# machine A, before leaving
cli.py handoff                 # handoff note, frees A's claim and task pointer, commits all work (WIP included), pushes
# machine B
cli.py resume RUN_ID           # git pull --ff-only, claim, adopt the active task, refresh HANDOFF.md
```

**Claims.** The first `task-start` on a run claims it for this clone
(`.agent/state/claims/`) and commits the claim at once; the clone keeps it across
tasks (renewed at every task start and end) until the run completes or is
cancelled, or `handoff` releases it for the next machine. Another machine sees
the claim as soon as any later commit of this clone is pushed and pulled. While
another clone's unexpired claim is visible here, run-changing commands
(`task-start`, `approve`, `transition`, `context`, `task-finish`, ...) are refused
with the holder's name. `resume --takeover --reason "..."` (or `claim --takeover`)
records a takeover, with the previous holder, in the claim history; the old
clone's own commands are refused once that claim reaches it. A claim expires
after `claim_ttl_seconds` (default one day) rather than detecting a dead machine;
an expired claim is taken over automatically, with the expiry as the recorded
reason. `handoff` also clears this clone's active-task pointer, and `resume`
restarts the adopted task's time budget (attempts are kept).

`SessionStart` and `pickup` report other clones' claims, commits waiting upstream
(`git fetch`, disable with `fetch_on_session_start`), unpushed commits, and
uncommitted agent state.

```sh
cli.py claims                 # who holds which run
cli.py claim|release RUN_ID   # manual claim control
cli.py handoff [--run RUN_ID] [--no-push]
cli.py resume RUN_ID [--takeover --reason "..."] [--no-pull]
```

A project on the previous layout (one rewritten `.agent/runtime/runs/<RUN>.json` per
run, committed `HANDOFF.md`) converts with `cli.py migrate-state`: each run becomes
one snapshot event (finished runs compacted), the pointer and route cache move to
`.agent/local/`, `.gitignore` gains the local-file lines, and the result is staged
for you to review and commit. Other clones pull that commit, then run
`migrate-state` once for their local files.

## Commits

```sh
python3 agentic/kit/runtime/python/agentic_runtime/cli.py commit \
  --type fix --scope billing --subject "round tax per line item" \
  --body "Totals drifted by a cent on multi-line invoices." \
  --trigger task-finish --work-item BUG-7 --task T-2 --run RUN_ID \
  --path src/billing/tax.py --trailer "Co-Authored-By: Agent <agent@example.com>"
```

`commit` rejects unknown types/triggers, a header over 72 characters, a trailing
period, and spoofed traceability trailers before anything is staged; then stages
exactly the `--path` files, runs `git commit -F` with hooks, reports a hook failure,
and records the commit in the run. `commit-message` prints the same message for
preview; do not pipe it into `git commit`. `record-commit RUN_ID` audits a commit made
another way and refuses one without a valid `Commit-Trigger` trailer. Nothing here
pushes a branch.

## Routing-decision cache

Separate from `agentic/data/project-context/` (discovered facts about the target
codebase) and from the governed-run store: a small shared cache
(`.agent/local/route-cache.json`, machine-local; each clone builds its own) that lets a session skip
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

Runs started before stored hashes became OS-portable (native path separator, raw
CRLF bytes) can be re-pinned with `migrate-pins RUN_ID --reason "..."`: it succeeds
only if every recorded pin equals the old-algorithm digest of the current content,
i.e. nothing actually changed, and records `PINS_MIGRATED`.

Read the [upgrade notes](../../ADOPTION.md#reinstall-upgrade-and-recover) before opening old state. The per-run JSON files carry no schema version; a mismatched shape simply won't match the current WorkflowRun fields, and does not turn old approvals into current authorization.

## Verification

```sh
sh agentic/kit/scripts/validate-kit.sh
```

Checks packaging, permissions, Markdown links and literal source paths, then runs the isolated smoke demo and behavioral tests for runtime policy, approvals, retries, cancellation, persistence rollback, hook execution, adoption, upgrades, installer recovery, and production evidence. The legacy delivery fixture reproduces a defect, modifies code, and executes review/QA with real checks and explicitly synthetic approvals. Run it separately with `python3 agentic/kit/examples/legacy-delivery.py`.
