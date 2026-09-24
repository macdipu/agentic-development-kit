# Commit Policy

When an agent commits, how the message is written, and how commits are logged
per session. Applies to every workflow in `agentic/kit/workflows/`.

## When to commit

An agent commits in exactly two cases:

| Trigger | When | Requirements |
|---|---|---|
| `task-finish` | A governed task has closed (`task-finish` accepted a success status) | Checks for the affected behavior ran and passed; the diff is limited to that task's scope. One task = one commit. |
| `user-request` | The user explicitly asks for a commit in chat | Commit what the user asked for. Never infer the ask from "looks done". |

Rules for both:

- Commit **after** `task-finish`, not during the task — the task's result
  envelope and check evidence must exist first.
- Never commit a `BLOCKED`/`FAILED` task, a failing check, or a half-done task,
  unless the user explicitly asks (then it is a `user-request` commit and the body
  says what is unfinished).
- Stage paths explicitly (`git add <paths>`); never `git add -A`/`.` blindly.
  Leave unrelated working-tree changes, and other agents' uncommitted changes,
  untouched.
- Never stage secrets, `.env*`, or runtime lock/temp files and logs
  (`.agent/runtime/**/*.lock`, `*.tmp`, `logs/` — gitignored). `.agent/HANDOFF.md`,
  `.agent/sessions/*.md`, and the run ledger under `.agent/runtime/` may be
  committed; approval comments and redacted audit payloads land in git with them.
- Never push, force-push, amend a pushed commit, rebase shared history, or skip
  hooks (`--no-verify`) without an explicit user ask. Committing does not imply
  pushing.
- Committing is not approval: it never satisfies a technical, release, or UAT gate.

## Message format

Conventional Commits header, a body saying *why*, then git trailers for
traceability (request -> work item -> task -> run -> commit):

```text
feat(auth): add rotating refresh tokens

Access tokens expired mid-session; refresh keeps users signed in
without widening token lifetime.

Work-Item: FEAT-12
Task: T-3
Run: run_8f2c
Commit-Trigger: task-finish
```

- Header: `type(scope): subject`, at most 72 characters, imperative mood, no
  trailing period. `!` after the scope marks a breaking change.
- Types: `feat`, `fix`, `refactor`, `perf`, `test`, `docs`, `build`, `ci`,
  `chore`, `revert`, `style`. Hotfixes are `fix`.
- Scope: the module/feature touched (lowercase), matching the
  `agentic/data/project-context/` module name where one exists.
- Body: why the change was made and anything unfinished; omit only when the
  header already says it all.
- Trailers: `Commit-Trigger` is required. `Work-Item`, `Task`, `Run` are required
  whenever they exist for the work. Platform attribution trailers (for example
  `Co-Authored-By`) go after these.

Build the message with the runtime so the format is checked rather than
remembered:

```sh
python3 agentic/kit/runtime/python/agentic_runtime/cli.py commit-message \
  --type feat --scope auth --subject "add rotating refresh tokens" \
  --body "Access tokens expired mid-session; ..." \
  --trigger task-finish --work-item FEAT-12 --task T-3 --run run_8f2c \
  | git commit -F -
```

## Logging

Every commit is logged in two places:

1. **Session record (git-tracked, cross-platform).** `close-session` (and the
   `Stop` hook) writes a `## Commits` section into `.agent/HANDOFF.md` and the new
   `.agent/sessions/*.md` record: every commit since the previous session
   record's HEAD, each tagged with its `Commit-Trigger`, `Work-Item`, and `Task`
   trailers. Commits missing the trailer show `[no Commit-Trigger]`, which flags a
   commit made outside this policy.
2. **Run audit (local, when a governed run exists).** Right after committing, run
   `cli.py record-commit RUN_ID [--rev HEAD]`. It appends a `COMMIT_RECORDED`
   event with the sha, subject, and trailers to the run's audit log, and refuses a
   commit without a valid `Commit-Trigger`.
