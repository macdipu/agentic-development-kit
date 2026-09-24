# Adopt the kit

## Choose an operating mode

- **instruction-only:** installs workflow instructions, skills, templates, and
  configuration. No automatic tool interception or initialized workflow state.
- **local-harness:** also initializes workflow state. Use the CLI task protocol,
  or select Claude integration to install native tool hooks.

From a reviewed kit checkout:

```sh
python3 agentic/kit/scripts/init_project.py --target /path/to/project --project my-project --type brownfield --mode instruction-only --agent cli
python3 agentic/kit/scripts/init_project.py --target /path/to/project --project my-project --type brownfield --mode local-harness --agent claude
python3 agentic/kit/scripts/init_project.py --target /path/to/project --project my-project --type brownfield --mode local-harness --agent codex
```

Use `--type greenfield` for a new application. An omitted mode defaults to
instruction-only on first install; subsequent runs retain the previous selection.
Agent selection detects an existing `.claude/` or `.codex/` directory, otherwise
it uses CLI mode. `claude` gets native Claude Code hooks (`PreToolUse`,
`SessionStart`, `PreCompact`, `Stop`); `codex` and other agent platforms use the
CLI adapter (`task-start`/`call-tool`/`task-finish`, `pickup`/`close-session`),
but native interception requires their own integration. The installer reports
this boundary.

Every install also scaffolds `.agent/HANDOFF.md`, `.agent/sessions/`, and
`.claude/skills/agent-handoff/` + `.codex/skills/agent-handoff/` (compatible
with [ishipu/agent-handoff](https://github.com/ishipu/agent-handoff)) regardless
of the chosen agent, so any platform can pick up or hand off a session from
what's committed to git. The runtime ledger lives beside them in
`.agent/runtime/` (active-task pointer, `runs/*.json`, route cache), also
git-tracked with repo-relative paths, so a governed run resumes on another
machine after `git pull`. Only lock/temp files and `logs/` are gitignored.

## What installation does

The installer stages and validates a complete kit before replacing host files.
It includes the catalog, adoption/workflow guides, hook templates, reusable runtime,
skills, templates, examples, and tests. Existing host README content remains intact.

A marked section is merged into AGENTS.md and CLAUDE.md. Text outside that section,
existing ignore rules, and unrelated Claude settings/hooks are preserved. Generated
host identity, installation metadata, and later work artifacts belong under
`agentic/data/`. Another project's recovered context and work items are never copied.

Framework detection supplies commands for observed Flutter/Dart, Node, and Rust
projects. Python environments and unknown toolchains are reported for configuration.
Existing Node scripts are reused; the installer does not invent missing scripts.
Review generated commands and their environment before governing a real task.

Command rules match the complete argument list. Preview rules require an explicit
device and variant, chosen by the project; see [runtime permissions](kit/runtime/README.md#permissions-and-commands).
The kit does not guess device IDs or install SDKs.

## Verify activation

From the host root:

```sh
python3 agentic/kit/runtime/python/agentic_runtime/cli.py doctor
sh agentic/kit/scripts/validate-kit.sh
python3 agentic/kit/examples/legacy-delivery.py
```

Doctor reports mode, instruction presence, packaged documents, configuration,
database integrity, command availability, and integration limits. Harness-mode
probes execute copies of the installed hooks with a disposable database, exercising
permitted/denied writes, session recovery, and compaction checkpoints. Claude wiring
is checked separately. Confirm actual invocation once in a real Claude session;
an isolated probe cannot establish what a running agent platform loaded.

Missing SDKs or unresolved project commands appear as warnings: the installation
can be valid while a requested project task remains unavailable.

Validation includes syntax, JSON, registry/permission consistency, Markdown links,
literal kit paths in examples, manifest consistency, the synthetic smoke demo, and
behavioral regression tests. Repository CI runs the same command on Linux/macOS
with Python 3.10 and 3.13; a hosted run must still be observed after pushing changes.

The legacy example executes a failing baseline, a bounded source fix, code review,
tests, and release-readiness stages in a temporary project. Its approval records
are explicitly synthetic fixtures. It neither calls a model nor deploys.

## Reinstall, upgrade, and recover

Rerunning installation preserves host configuration, identity, and data. To install
new reusable kit code:

```sh
python3 agentic/kit/scripts/init_project.py --target /path/to/project --project my-project --type brownfield --upgrade
```

The old kit and replaced files are retained under the host's `agentic-backups/`
directory; the command reports the exact backup. Existing JSON configuration is
preserved, and newly introduced configuration files receive defaults. Review new
configuration requirements: staged validation rejects incompatible preserved settings.

Finish or cancel active runs before upgrading: their code/configuration pins cannot
be silently changed. Ordinary installation exceptions restore replaced files.
A machine crash or forced process termination can leave a partial installation;
inspect the reported backup and restore affected files before retrying. Keep workflow
database backups separately. Do not erase active state to make installation pass.

Changing from harness mode to instruction-only requires explicit hook removal and
run reconciliation; the installer rejects an automatic downgrade.

For interrupted runtime tasks, use the [recovery commands](kit/runtime/README.md#cancel-recover-and-upgrade).
The database schema retains legacy records, but legacy approvals do not become
new authorization. Start a fresh governed run after reviewing changed pins.

## Extend the kit

Add a specialist with inputs, procedure, deliverable, and readiness boundary;
link the shared [result contract](kit/skills/RESULT-CONTRACT.md). Register stage
eligibility, compatibility capability, and explicit permissions. Missing entries
fail validation or deny execution.

Regenerate the manifest after changing packaged files:

```sh
python3 agentic/kit/scripts/validate_structure.py --write-manifests
sh agentic/kit/scripts/validate-kit.sh
```

## Production adoption

Use the [staged readiness contract](kit/runtime/production-readiness.md).
The checker validates evidence bindings and freshness. Organization-specific
isolation, authenticated identity, durable execution, monitoring, deployment, and
rollback systems must enforce the corresponding controls.
