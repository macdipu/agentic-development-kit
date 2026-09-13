# Adopt the kit

## Choose an operating mode

- **Instruction mode:** use the skills and Markdown workflows with your existing agent tooling. Rules guide agent behavior, but copying these files does not activate deterministic runtime enforcement.
- **Local harness mode:** route work and trusted adapter calls through the reference Python runtime. It stores checkpoints, validates results, checks gates, and controls registered tool calls. It does not include a model provider or automatically execute Markdown instructions.

## Add to an existing project

Steps 1-6 below can be run in one shot with `python3 agentic/scripts/init_project.py --target /path/to/project --project name --type greenfield|brownfield` (from this kit's own checkout) or via the `/agentic-init` skill in a Claude Code session. It is idempotent and non-destructive: it merges rather than overwrites `AGENTS.md`/`CLAUDE.md`/`.gitignore`/`.claude/settings.json`, and never touches an already-populated `project.yaml`. It ends with a PASS/FAIL activation report per layer (instructions loaded, harness recording, hook wired) instead of just "files copied" — read that report, not just the exit code. Manual steps remain below for anyone who wants to do it by hand or understand what the script does.

1. Copy `agentic/` from a reviewed kit revision, excluding local `runtime/state/`, `artifacts/`, and Python caches. Preserve the host project's README and existing project-specific rules. Also copy `.claude/settings.json` (merge its `hooks.PreToolUse` entry into an existing settings file rather than overwriting it) if you want Claude Code's own tool calls gated during a governed task; see [coding-agent integration](runtime/README.md#coding-agent-integration).
2. Merge the kit's root `AGENTS.md` guidance into the host's entrypoint; do not overwrite existing instructions. Keep the root `CLAUDE.md` reference for kit completeness, merging any existing Claude instructions. Tools that do not use it can ignore it. The kit's graph-tool preference applies when those tools are available; use scoped source discovery when unavailable.
3. Set `agentic/project-context/project.yaml` for the host project. Start unknown sections as `MISSING`; populate only the module scope needed for the first task with source evidence and freshness information. Do not copy another project's recovered context as the host baseline.
4. Review `agentic/config/platform.json`, skill eligibility, and capability ceilings against the team's workflow. Choose sprint handling for the specific work item. `NO_REPLAN` is the CLI default, not an automatic planning assessment.
5. Merge the kit's local state/cache ignore patterns into the host `.gitignore`. Preserve existing ignore rules. Do not commit workflow databases, private logs, screenshots containing private data, or credentials.
6. Regenerate the manifests with `python3 agentic/scripts/validate_structure.py --write-manifests` to reflect the host's optional root files, then run validation below. For local harness mode, complete the isolated demo, then submit one real bounded task using the [runtime guide](runtime/README.md).

The root README and `.github/workflows/validate-kit.yml` belong to this kit repository. For a host project, merge their relevant links/check command into its existing README and CI instead of replacing them.

## Validate and extend

```sh
sh agentic/scripts/validate-kit.sh
python3 agentic/examples/runtime-demo.py
```

Validation checks Python syntax, JSON, skill names and local links, manifest consistency, behavioral runtime tests, and deterministic eval cases. GitHub Actions runs the same command on Python 3.10 and 3.13. Action usage follows the official [checkout](https://github.com/actions/checkout) and [setup-python](https://github.com/actions/setup-python) documentation. Hosted CI execution still needs to run after publishing the change.

To add a specialist:

1. Add `agentic/skills/<name>/SKILL.md` with a discriminating description, inputs, procedure, deliverable, and readiness boundary. Link the shared [handoff contract](skills/RESULT-CONTRACT.md).
2. Add its allowed stages to `config/skill-registry.json` and its capability ceiling to `config/capabilities.json`. Missing eligibility or capability entries deny execution.
3. Update the catalog and appropriate workflow routing. Keep platform-only command details in linked references.
4. Regenerate the manifests with `python3 agentic/scripts/validate_structure.py --write-manifests`, then run validation. Add behavioral tests if the specialist introduces runtime behavior; do not turn wording checks into behavioral evidence.

## Upgrade an existing installation

Review the kit diff, merge host customizations, and rerun validation. Active governed runs pin skill contents (including references and the handoff contract) and configuration. A changed pinned skill or configuration requires a new run; do not silently substitute instructions into an active run.

The earlier runtime stored state at `<repo>/runtime/state/agentic.db` despite documenting `agentic/runtime/state/`. The default is now `agentic/runtime/state/agentic.db`; `--db` explicitly selects another path. Back up the old database before opening it with the new runtime. Schema initialization adds audit/tool-call tables and an approval scope column. Legacy runs remain readable through `show`/`list`, but cannot execute or transition; start a new governed run and review evidence and approvals again. There is no automatic approval migration or automatic state move.

## Preview a mobile app

Ask: “Run the app on an Android emulator and show the home screen,” or “Launch the iOS simulator preview for this flavor.” The orchestrator selects `device-preview-agent`, which resolves the project configuration, selects one explicit target, launches the app, and inspects screenshots. Existing tasks do not need new feature or sprint artifacts just to preview them.

A missing SDK/runtime, signing requirement, unavailable device, or inability to inspect the requested screen is reported as a concrete blocker or partial result. Successful compilation alone is not a verified preview. The kit has command guidance; your environment supplies Flutter/Android/Xcode and permitted UI/image tools.
