---
name: agentic-init
description: Activate the agentic development kit for a project -- copy it into a new or existing project (or verify it in-place), set project identity, wire the PreToolUse governance hook, run validation, and report pass/fail per layer (instructions loaded, harness recording, native enforcement). Use for "initialize/activate/set up the agentic kit", "add this kit to my project", "/agentic-init".
---

# Agentic kit activation

Single entry point for `agentic/ADOPTION.md`'s manual checklist. Runs `agentic/scripts/init_project.py`, which is idempotent and non-destructive: it never overwrites `AGENTS.md`/`CLAUDE.md`/`.gitignore` content (merges or leaves a note instead), never overwrites an already-populated `project.yaml`, and only overwrites an existing `agentic/` tree with `--force` (after backing it up).

## Steps

1. Determine three inputs. Ask the user (AskUserQuestion) for whichever aren't already clear from their message or the conversation:
   - **Target directory**: the project root to activate the kit in. If the user is asking about *this* repository (the kit's own checkout) and it already has `agentic/`, that's an in-place check, not a copy.
   - **Project name**: a short identifier for `project.yaml`.
   - **Project type**: `greenfield` (new project, no existing code/history to reconcile) or `brownfield` (existing project — discovery happens incrementally, not a full audit).

2. Run:

   ```sh
   python3 <path-to-this-kit-repo>/agentic/scripts/init_project.py --target <target-dir> --project <name> --type <greenfield|brownfield>
   ```

   Add `--force` only if the user explicitly wants an existing `agentic/` tree in the target replaced (it gets backed up first, never deleted outright).

3. Read the script's own "Activation status" block at the end of its output — do not re-derive pass/fail yourself. Report it to the user plainly, PASS/FAIL per row.

4. If `.claude/settings.json` was just created or newly merged in the target project, tell the user: open `/hooks` once in a Claude Code session rooted at that target directory (or restart the session) — the settings watcher only picks up a `.claude/` directory that existed when the session started, so a brand-new one needs that nudge before the gate hook actually fires.

5. If any row still FAILs after the script ran, report exactly which one and why (read the script's stdout for the specific COPY/KEEP/MERGE/RUN lines above the status block — don't guess) rather than declaring success.

## What this does not do

It does not fabricate project context (module list, integrations, discovered baseline) — those stay `MISSING` until the orchestrator skill (`agentic/skills/agentic-sdlc-orchestrator/SKILL.md`) actually discovers them on a real task. Activating the kit and populating its context are separate steps; don't claim brownfield discovery happened just because activation passed.
