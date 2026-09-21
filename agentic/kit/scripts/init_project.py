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
from agentic_runtime.installation import managed_text, merge_hooks, unfinished_runs
from agentic_runtime import handoff

DOCS = ['README.md', 'ADOPTION.md', 'SKILL-CATALOG.md']
IGNORE = ['/agentic/data/runtime/state/', '/agentic/data/runtime/logs/',
          '/agentic/data/artifacts/', '/agentic-backups/', '__pycache__/', '*.py[cod]']

HANDOFF_SKILL = """---
name: agent-handoff
description: Read and write this project's cross-agent-platform handoff notes ({invoke})
---

Before starting work, read `.agent/HANDOFF.md` and the most recent file under
`.agent/sessions/` (or run `python3 agentic/kit/runtime/python/agentic_runtime/cli.py pickup`)
to pick up where the last agent -- on this platform or another -- left off.

When you finish a work session, record it so a different agent/platform can
continue from git alone:

```
python3 agentic/kit/runtime/python/agentic_runtime/cli.py close-session \\
  --agent {agent} --task "what this run is for" --completed "what you did" \\
  --changed-files path/one path/two --tests "npm test passes" \\
  --blockers "..." --decisions "..." --next-action "what to do next"
```

`--changed-files`, `--tests`, `--blockers`, and `--decisions` are optional;
`--agent`, `--task`, and `--completed` are not. Structured fields, not one
free-form summary, so the next agent can read a specific field instead of
parsing prose.

This writes `.agent/HANDOFF.md` and a new `.agent/sessions/<timestamp>-{agent}.md`
record, both git-tracked (unlike this kit's own local run store under
`agentic/data/runtime/state/`, which stays out of git). Never overwrite another
agent's uncommitted changes without explicit user approval.
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


def _stage_kit(put, changed, stage, target, source, upgrade):
    """Copy the kit tree into stage; upgrades preserve existing config/*.json."""
    kit_relative = 'agentic/kit'
    current_kit = target / kit_relative
    kit_source = current_kit if current_kit.exists() and not upgrade else source / 'kit'
    shutil.copytree(kit_source, stage / kit_relative, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    if upgrade and current_kit.exists():
        # Preserve project configuration. New configuration files are supplied
        # by the new kit; existing policy choices are never silently replaced.
        for file in (current_kit / 'config').glob('*.json'):
            shutil.copy2(file, stage / kit_relative / 'config' / file.name)
    if not current_kit.exists() or upgrade:
        changed.append(kit_relative)
    return current_kit


def _stage_docs_and_instructions(put, stage, target, source):
    for name in DOCS:
        relative = 'agentic/' + name
        current = target / relative
        put(relative, current.read_text() if current.exists() else (source / name).read_text())
    fragment = (stage / 'agentic/kit/config/AGENTS.fragment.md').read_text()
    for name, addition in [('AGENTS.md', fragment), ('CLAUDE.md', '@AGENTS.md\n')]:
        current = (target / name).read_text() if (target / name).exists() else ''
        put(name, managed_text(current, addition))
    ignore = (target / '.gitignore').read_text() if (target / '.gitignore').exists() else ''
    additions = [line for line in IGNORE if line not in ignore.splitlines()]
    put('.gitignore', ignore.rstrip('\n') + '\n' + '\n'.join(additions) + ('\n' if additions else ''))


def _scaffold_project_context(put, target, source, project, project_type):
    for relative in ['README.md', 'project-context/README.md', 'project-context/features/README.md']:
        dest = 'agentic/data/' + relative
        if not (target / dest).exists():
            put(dest, (source / 'data' / relative).read_text())
    identity = 'agentic/data/project-context/project.yaml'
    if not (target / identity).exists():
        put(identity, 'project: ' + json.dumps(project) + '\nproject_type: ' + project_type +
            '\ncontext_status: MISSING\nmodules: []\nintegrations: []\n')
    index = 'agentic/data/project-context/context-index.yaml'
    if not (target / index).exists():
        put(index, 'system:\n  status: MISSING\nmodules: {}\nproject_docs: {}\nfeatures: {}\n')


def _scaffold_handoff(put, target):
    """Cross-agent-platform handoff notes (agent-handoff compatible, git-tracked
    unlike agentic/data/runtime/state/): scaffold once, never clobber live notes."""
    if not (target / '.agent').exists():
        put('.agent/sessions/.gitkeep', '')
        put('.agent/HANDOFF.md', handoff.render_handoff(
            last_agent='claude', operator=handoff.git_user(target), status='NOT_STARTED',
            task='(not started)', completed='Project scaffolded; no session has run yet.',
            changed_files=[], tests='', blockers='',
            decisions='', next_action='Start the first governed run or work item.',
            git_snapshot_text=handoff.git_snapshot(target)))
    if not (target / '.claude/skills/agent-handoff/SKILL.md').exists():
        put('.claude/skills/agent-handoff/SKILL.md', _handoff_skill('claude', '/agent-handoff'))
    if not (target / '.codex/skills/agent-handoff/SKILL.md').exists():
        put('.codex/skills/agent-handoff/SKILL.md', _handoff_skill('codex', '$agent-handoff'))


def _stage_hooks_and_commands(put, stage, target, current_kit, mode, agent, detected):
    command_path = stage / 'agentic/kit/config/allowed-commands.json'
    # Generate project commands on the first install only. Upgrades preserve
    # explicitly reviewed commands, including exact preview target arguments.
    if not current_kit.exists():
        command_path.write_text(json.dumps({'commands': detected['commands']}, indent=2) + '\n')
    if mode == 'local-harness' and agent == 'claude':
        relative = '.claude/settings.json'
        current = json.loads((target / relative).read_text()) if (target / relative).exists() else {}
        template = json.loads((stage / 'agentic/kit/config/hooks.json').read_text())
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


def install(target, project, project_type, mode, agent, upgrade=False):
    target = Path(target).resolve()
    if target == ROOT:
        raise ValueError('Install into a host project; use doctor to inspect this kit checkout')
    if target == Path(target.anchor) or target == Path.home():
        raise ValueError('Choose a project directory, not a filesystem or home root')
    if (target / 'agentic/kit').exists() and upgrade:
        if unfinished_runs(target) or (target / 'agentic/data/runtime/state/active-task.json').exists():
            raise ValueError('Finish or cancel governed work before upgrading pinned kit files')
    target.mkdir(parents=True, exist_ok=True)
    source = ROOT / 'agentic'
    existing_install = target / 'agentic/data/project-context/installation.json'
    previous = json.loads(existing_install.read_text()) if existing_install.exists() else {}
    mode, agent = _resolve_mode_agent(target, mode, agent, previous)
    with tempfile.TemporaryDirectory(prefix='agentic-stage-', dir=target.parent) as temporary:
        stage = Path(temporary)
        changed = []

        def put(relative, content):
            path = stage / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding='utf-8')
            changed.append(relative)

        current_kit = _stage_kit(put, changed, stage, target, source, upgrade)
        _stage_docs_and_instructions(put, stage, target, source)
        _scaffold_project_context(put, target, source, project, project_type)
        _scaffold_handoff(put, target)

        detected = detect_project(target)
        _stage_hooks_and_commands(put, stage, target, current_kit, mode, agent, detected)
        put('agentic/data/project-context/installation.json', json.dumps({
            'mode': mode, 'agent': agent, 'frameworks': detected['frameworks'],
            'unknowns': detected['unknowns'],
        }, indent=2) + '\n')

        # Preserve optional root README in the host-specific manifest.
        if (target / 'README.md').exists():
            shutil.copy2(target / 'README.md', stage / 'README.md')
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
        for command in [
            [sys.executable, 'agentic/kit/scripts/validate_structure.py', '--write-manifests'],
            [sys.executable, 'agentic/kit/examples/runtime-demo.py'],
        ]:
            result = subprocess.run(command, cwd=stage, env=env, capture_output=True, text=True, timeout=60)
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
                                        cwd=target, env=env, capture_output=True, text=True, timeout=30)
                if result.returncode:
                    raise ValueError(result.stderr)
            report = diagnose(target)
            if not report['ok']:
                raise ValueError('Installed doctor failed: ' + json.dumps(report))
        except BaseException:
            _rollback(target, backup, installed)
            raise
        return {'ok': True, 'mode': mode, 'agent': agent,
                'backup': str(backup) if backup.exists() else None, 'doctor': report}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', type=Path, required=True)
    parser.add_argument('--project', required=True)
    parser.add_argument('--type', choices=['greenfield', 'brownfield'], required=True)
    parser.add_argument('--mode', choices=['instruction-only', 'local-harness'])
    parser.add_argument('--agent', choices=['cli', 'claude', 'codex'])
    parser.add_argument('--upgrade', '--force', action='store_true', dest='upgrade',
                        help='Install new kit code with backups, preserving project configuration')
    args = parser.parse_args(argv)
    try:
        result = install(args.target, args.project, args.type, args.mode, args.agent, args.upgrade)
        print(json.dumps(result, indent=2))
        return 0
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
