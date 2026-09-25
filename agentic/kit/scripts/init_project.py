#!/usr/bin/env python3
"""Install or upgrade a kit with staged validation and recoverable file replacement."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'agentic/kit/runtime/python'))
from agentic_runtime.doctor import detect_project, diagnose
from agentic_runtime.installation import claude_text, managed_text, merge_hooks, unfinished_runs
from agentic_runtime import handoff
from agentic_runtime.context import file_hash
from agentic_runtime.paths import ACTIVE_TASK_POINTER_REL, LEGACY_RUNS_DIR_REL
from agentic_runtime.migration import IGNORE_LINES

DOCS = ['README.md', 'ADOPTION.md', 'SKILL-CATALOG.md']
# .agent/state/ and .agent/sessions/ are committed (append-only, conflict-free);
# the local copy of HANDOFF.md, machine-local files, locks, and caches are not.
IGNORE = IGNORE_LINES + ['/agentic/data/artifacts/', '/agentic-backups/', '__pycache__/', '*.py[cod]']

HANDOFF_SKILL = """---
name: agent-handoff
description: Read and write this project's cross-agent-platform handoff notes ({invoke})
---

Before starting work, `git pull`, then read the note:

```
python3 agentic/kit/runtime/python/agentic_runtime/cli.py pickup
```

That shows where the last agent -- on this platform or another, on this machine
or another -- left off, which clone holds which run, and whether commits are
waiting upstream. To continue a run another machine handed off (its task and
work in progress included): `python3 agentic/kit/runtime/python/agentic_runtime/cli.py resume RUN_ID`.
Before leaving for another machine: `python3 agentic/kit/runtime/python/agentic_runtime/cli.py handoff`.

When you finish a work session, record it so a different agent/platform can
continue:

```
python3 agentic/kit/runtime/python/agentic_runtime/cli.py close-session \\
  --agent {agent} --status RUNNING|BLOCKED|COMPLETED|CANCELLED \\
  --task "what this run is for" --completed "what you did" \\
  --changed-files path/one path/two --tests "npm test passes" \\
  --blockers "..." --decisions "..." --next-action "what to do next"
```

`--changed-files`, `--tests`, `--blockers`, and `--decisions` are optional;
`--agent`, `--status`, `--task`, and `--completed` are not -- `--status` has no
default, so it can't silently claim `COMPLETED` for a session that didn't
finish. Structured fields, not one free-form summary, so the next agent can
read a specific field instead of parsing prose. A `## Commits` section is added
from git automatically: every commit since the previous session record, tagged
with its `Commit-Trigger` (`task-finish`/`user-request`) and `Work-Item`/`Task`
trailers -- see `agentic/kit/policies/commit-policy.md`.

This adds `.agent/state/handoffs/<timestamp>-{agent}-*.md` (copied to the local
`.agent/HANDOFF.md`) and a new `.agent/sessions/<timestamp>-{agent}.md`, and
commits them (state-only commit). They travel with your branch on the next push.
Never overwrite another agent's uncommitted changes without explicit user approval.
"""


def _handoff_skill(agent, invoke):
    return HANDOFF_SKILL.format(agent=agent, invoke=invoke)


def _resolve_mode_agent(target, mode, agent, previous):
    """Default reruns retain an explicitly chosen mode and platform."""
    mode = mode or previous.get('mode', 'instruction-only')
    agent = agent or previous.get('agent', 'claude' if (target / '.claude').is_dir()
                                   else 'codex' if (target / '.codex').is_dir() else 'cli')
    if previous.get('mode') == 'local-harness' and mode != previous['mode']:
        raise ValueError('Mode downgrade requires removing hooks and reconciling runs manually')
    return mode, agent


def kit_hashes(kit_dir):
    """LF-normalized sha256 of every packaged kit file except host-owned config/*.json."""
    kit_dir = Path(kit_dir)
    hashes = {}
    for path in sorted(kit_dir.rglob('*')):
        rel = path.relative_to(kit_dir).as_posix()
        if not path.is_file() or '__pycache__' in path.parts or path.suffix in {'.pyc', '.pyo'} \
                or (rel.startswith('config/') and path.suffix == '.json'):
            continue
        hashes[rel] = file_hash(str(path))
    return hashes


def host_kit_edits(current_kit, recorded):
    """Kit files the host changed since installation (edits a plain upgrade would discard)."""
    if not recorded:
        return None  # installed before hashes were recorded: unknown, reported
    current = kit_hashes(current_kit)
    return sorted(rel for rel, digest in recorded.items() if rel in current and current[rel] != digest)


def add_missing_keys(existing, defaults):
    """New configuration keys from the kit, never a changed value: host policy stays."""
    if not isinstance(existing, dict) or not isinstance(defaults, dict):
        return existing, []
    added = []
    merged = dict(existing)
    for key, value in defaults.items():
        if key not in merged:
            merged[key] = value
            added.append(key)
        elif isinstance(value, dict) and isinstance(merged[key], dict):
            merged[key], nested = add_missing_keys(merged[key], value)
            added += [f'{key}.{n}' for n in nested]
    return merged, added


def _stage_kit(put, changed, stage, target, source, upgrade, notes):
    """Copy the kit tree into stage; upgrades preserve existing config/*.json values."""
    kit_relative = 'agentic/kit'
    current_kit = target / kit_relative
    kit_source = current_kit if current_kit.exists() and not upgrade else source / 'kit'
    shutil.copytree(kit_source, stage / kit_relative, ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '.pytest_cache'))
    if upgrade and current_kit.exists():
        # Preserve project configuration. Keys introduced by the new kit are added;
        # existing policy choices are never silently replaced.
        for file in (current_kit / 'config').glob('*.json'):
            staged = stage / kit_relative / 'config' / file.name
            preserved = json.loads(file.read_text(encoding='utf-8'))
            defaults = json.loads(staged.read_text(encoding='utf-8')) if staged.exists() else {}
            merged, added = add_missing_keys(preserved, defaults)
            if added:
                notes.append(f'config/{file.name}: added new keys {added}')
            staged.write_text(json.dumps(merged, indent=2) + '\n', encoding='utf-8', newline='\n')
    if not current_kit.exists() or upgrade:
        changed.append(kit_relative)
    return current_kit


def _stage_docs_and_instructions(put, stage, target, source, upgrade=False):
    # Kit docs describe the kit, so an upgrade refreshes them; a plain reinstall keeps host copies.
    for name in DOCS:
        relative = 'agentic/' + name
        current = target / relative
        put(relative, current.read_text(encoding='utf-8') if current.exists() and not upgrade else (source / name).read_text(encoding='utf-8'))
    fragment = (stage / 'agentic/kit/config/AGENTS.fragment.md').read_text(encoding='utf-8')
    def existing(name):
        return (target / name).read_text(encoding='utf-8') if (target / name).exists() else ''
    put('AGENTS.md', managed_text(existing('AGENTS.md'), fragment))
    put('CLAUDE.md', claude_text(existing('CLAUDE.md')))
    ignore = (target / '.gitignore').read_text(encoding='utf-8') if (target / '.gitignore').exists() else ''
    wanted = IGNORE
    additions = [line for line in wanted if line not in ignore.splitlines()]
    put('.gitignore', ignore.rstrip('\n') + '\n' + '\n'.join(additions) + ('\n' if additions else ''))


def _scaffold_project_context(put, target, source, project, project_type):
    for relative in ['README.md', 'project-context/README.md', 'project-context/features/README.md']:
        dest = 'agentic/data/' + relative
        if not (target / dest).exists():
            put(dest, (source / 'data' / relative).read_text(encoding='utf-8'))
    identity = 'agentic/data/project-context/project.yaml'
    if not (target / identity).exists():
        put(identity, 'project: ' + json.dumps(project) + '\nproject_type: ' + project_type +
            '\ncontext_status: MISSING\nmodules: []\nintegrations: []\n')
    index = 'agentic/data/project-context/context-index.yaml'
    if not (target / index).exists():
        put(index, 'system:\n  status: MISSING\nmodules: {}\nproject_docs: {}\nfeatures: {}\n')


def _scaffold_handoff(put, target):
    """Cross-agent-platform handoff notes (agent-handoff compatible, committed append-only):
    scaffold once, never clobber live notes."""
    if not (target / '.agent/HANDOFF.md').exists():
        put('.agent/sessions/.gitkeep', '')
        note = handoff.render_handoff(
            last_agent='claude', operator=handoff.git_user(target), status='NOT_STARTED',
            task='(not started)', completed='Project scaffolded; no session has run yet.',
            changed_files=[], tests='', blockers='',
            decisions='', next_action='Start the first governed run or work item.',
            git_snapshot_text=handoff.git_snapshot(target))
        put('.agent/state/handoffs/00000000T000000000000Z-scaffold.md', note)  # committed
        put('.agent/HANDOFF.md', note)  # local copy, gitignored
    if not (target / '.claude/skills/agent-handoff/SKILL.md').exists():
        put('.claude/skills/agent-handoff/SKILL.md', _handoff_skill('claude', '/agent-handoff'))
    if not (target / '.codex/skills/agent-handoff/SKILL.md').exists():
        put('.codex/skills/agent-handoff/SKILL.md', _handoff_skill('codex', '$agent-handoff'))


def _stage_hooks_and_commands(put, stage, target, current_kit, mode, agent, detected):
    command_path = stage / 'agentic/kit/config/allowed-commands.json'
    # Generate project commands on the first install only. Upgrades preserve
    # explicitly reviewed commands, including exact preview target arguments.
    if not current_kit.exists():
        command_path.write_text(json.dumps({'commands': detected['commands']}, indent=2) + '\n', encoding='utf-8', newline='\n')
    if mode == 'local-harness' and agent == 'claude':
        relative = '.claude/settings.json'
        current = json.loads((target / relative).read_text(encoding='utf-8')) if (target / relative).exists() else {}
        template = json.loads((stage / 'agentic/kit/config/hooks.json').read_text(encoding='utf-8'))
        put(relative, json.dumps(merge_hooks(current, template), indent=2) + '\n')


def _replace_files(target, stage, changed, backup, installed):
    """Move each staged path into target, backing up whatever it replaces.

    Appends (relative, existed) to `installed` as each succeeds, so a caller can
    roll back exactly what was actually swapped in if a later step fails --
    including a raise partway through this loop itself.
    """
    for relative in changed:
        destination = target / relative
        if destination.is_symlink():
            raise ValueError('Refusing to replace a symlink: ' + relative)
        if not destination.resolve().is_relative_to(target):
            raise ValueError('Installation path escapes host project: ' + relative)
        saved = backup / relative
        existed = destination.exists()
        if existed:
            saved.parent.mkdir(parents=True, exist_ok=True)
            if destination.is_dir():
                shutil.copytree(destination, saved)
            else:
                shutil.copy2(destination, saved)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.is_dir():
            # Move the old tree out before installing the validated tree.
            moved = backup / 'replaced-kit'
            os.replace(destination, moved)
        installed.append((relative, existed))
        os.replace(stage / relative, destination)


def _rollback(target, backup, installed):
    for relative, existed in reversed(installed):
        destination = target / relative
        if destination.is_dir():
            shutil.rmtree(destination)
        else:
            destination.unlink(missing_ok=True)
        if existed:
            saved = backup / relative
            if saved.is_dir():
                shutil.copytree(saved, destination)
            else:
                shutil.copy2(saved, destination)


def install(target, project, project_type, mode, agent, upgrade=False, discard_kit_edits=False):
    target = Path(target).resolve()
    if target == ROOT:
        raise ValueError('Install into a host project; use doctor to inspect this kit checkout')
    if target == Path(target.anchor) or target == Path.home():
        raise ValueError('Choose a project directory, not a filesystem or home root')
    if (target / 'agentic/kit').exists() and upgrade:
        if unfinished_runs(target) or (target / ACTIVE_TASK_POINTER_REL).exists() \
                or (target / '.agent/runtime/active-task.json').exists():
            raise ValueError('Finish or cancel governed work before upgrading pinned kit files')
    target.mkdir(parents=True, exist_ok=True)
    source = ROOT / 'agentic'
    existing_install = target / 'agentic/data/project-context/installation.json'
    previous = json.loads(existing_install.read_text(encoding='utf-8')) if existing_install.exists() else {}
    mode, agent = _resolve_mode_agent(target, mode, agent, previous)
    notes = []
    if upgrade and (target / 'agentic/kit').exists():
        edits = host_kit_edits(target / 'agentic/kit', previous.get('kit_files'))
        if edits is None:
            notes.append('No kit baseline recorded by the previous install; host edits to kit files (if any) '
                         'are only in the backup. Upstream generic changes into the kit.')
        elif edits and not discard_kit_edits:
            raise ValueError('Kit files were edited in this project and an upgrade would replace them: '
                             + ', '.join(edits) + '. Upstream the generic changes into the kit (host-only rules '
                             'belong outside the AGENTS.md managed block or under agentic/data/), then rerun; '
                             'or pass --discard-kit-edits (they stay in the backup).')
        elif edits:
            notes.append('Discarded host edits (kept in backup): ' + ', '.join(edits))
    with tempfile.TemporaryDirectory(prefix='agentic-stage-', dir=target.parent) as temporary:
        stage = Path(temporary)
        changed = []

        def put(relative, content):
            path = stage / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding='utf-8', newline='\n')
            changed.append(relative)

        current_kit = _stage_kit(put, changed, stage, target, source, upgrade, notes)
        _stage_docs_and_instructions(put, stage, target, source, upgrade)
        _scaffold_project_context(put, target, source, project, project_type)
        _scaffold_handoff(put, target)

        detected = detect_project(target)
        _stage_hooks_and_commands(put, stage, target, current_kit, mode, agent, detected)
        put('agentic/data/project-context/installation.json', json.dumps({
            'mode': mode, 'agent': agent, 'frameworks': detected['frameworks'],
            'unknowns': detected['unknowns'],
            # Baseline for detecting host edits to kit files on the next upgrade.
            'kit_files': kit_hashes(stage / 'agentic/kit'),
        }, indent=2) + '\n')

        # Preserve optional root README in the host-specific manifest.
        if (target / 'README.md').exists():
            shutil.copy2(target / 'README.md', stage / 'README.md')
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
        validate_env = dict(env, AGENTIC_HOST_ROOT=str(target))
        for command in [
            [sys.executable, 'agentic/kit/scripts/validate_structure.py', '--write-manifests'],
            [sys.executable, 'agentic/kit/examples/runtime-demo.py'],
        ]:
            result = subprocess.run(command, cwd=stage, env=validate_env, capture_output=True, text=True, timeout=60, encoding='utf-8', errors='replace')
            if result.returncode:
                raise ValueError('Staged validation failed: ' + result.stderr + result.stdout)
        changed.append('agentic/MANIFEST.md')

        # Backups live outside the packaged tree and remain available after success.
        backup = target / 'agentic-backups' / uuid.uuid4().hex
        installed = []
        try:
            _replace_files(target, stage, changed, backup, installed)
            if mode == 'local-harness':
                result = subprocess.run([sys.executable, 'agentic/kit/runtime/python/agentic_runtime/cli.py', 'init'],
                                        cwd=target, env=env, capture_output=True, text=True, timeout=30, encoding='utf-8', errors='replace')
                if result.returncode:
                    raise ValueError(result.stderr)
            report = diagnose(target)
            if not report['ok']:
                raise ValueError('Installed doctor failed: ' + json.dumps(report))
        except BaseException:
            _rollback(target, backup, installed)
            raise
        if (target / LEGACY_RUNS_DIR_REL.parent).is_dir():
            notes.append('Previous .agent/runtime/ layout found; convert it to the append-only .agent/state/ '
                         'layout with `python3 agentic/kit/runtime/python/agentic_runtime/cli.py migrate-state`')
        return {'ok': True, 'mode': mode, 'agent': agent,
                'backup': str(backup) if backup.exists() else None, 'notes': notes, 'doctor': report}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', type=Path, required=True)
    parser.add_argument('--project', required=True)
    parser.add_argument('--type', choices=['greenfield', 'brownfield'], required=True)
    parser.add_argument('--mode', choices=['instruction-only', 'local-harness'])
    parser.add_argument('--agent', choices=['cli', 'claude', 'codex'])
    parser.add_argument('--upgrade', '--force', action='store_true', dest='upgrade',
                        help='Install new kit code with backups, preserving project configuration')
    parser.add_argument('--discard-kit-edits', action='store_true',
                        help='Upgrade even though kit files were edited in this project (edits stay in the backup)')
    args = parser.parse_args(argv)
    try:
        result = install(args.target, args.project, args.type, args.mode, args.agent, args.upgrade,
                         args.discard_kit_edits)
        print(json.dumps(result, indent=2))
        return 0
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
