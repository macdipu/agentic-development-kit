#!/usr/bin/env python3
"""One-shot, idempotent activation entry point for the agentic development kit.

Copies the kit into a target project (if it isn't already there), sets project
identity, and runs the same validation/init steps documented in ADOPTION.md and
runtime/README.md -- then reports, per layer, whether the kit is actually active
rather than just present. Never overwrites AGENTS.md/CLAUDE.md/.gitignore
content; those need a human merge decision. Re-running is safe: existing
project-context files and an existing agentic/ tree are left alone unless
--force is passed.
"""
import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

KIT_REPO_ROOT = Path(__file__).resolve().parents[2]
KIT_SOURCE = KIT_REPO_ROOT / 'agentic'
EXCLUDE_DIR_NAMES = {'state', 'artifacts', '__pycache__'}
GITIGNORE_LINES = ['/agentic/runtime/state/', '/agentic/artifacts/', '__pycache__/', '*.py[cod]']


def log(message):
    print(message)


def copy_kit_tree(target_kit_dir, force):
    if target_kit_dir.exists():
        if not force:
            log(f'SKIP  agentic/ already present at {target_kit_dir}; pass --force to overwrite (backs up first)')
            return
        backup = target_kit_dir.with_name('agentic.bak-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
        shutil.move(str(target_kit_dir), str(backup))
        log(f'BACKUP existing agentic/ moved to {backup.name}')

    def ignore(_dir, names):
        return [n for n in names if n in EXCLUDE_DIR_NAMES]

    shutil.copytree(KIT_SOURCE, target_kit_dir, ignore=ignore)
    log(f'COPY  agentic/ -> {target_kit_dir}')


def copy_skill(target_root, force):
    source = KIT_REPO_ROOT / '.claude/skills/agentic-init'
    dest = target_root / '.claude/skills/agentic-init'
    if not source.is_dir():
        return
    if dest.exists() and not force:
        log('KEEP  .claude/skills/agentic-init already present; pass --force to refresh from this kit revision')
        return
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(source, dest)
    log('COPY  .claude/skills/agentic-init (so this project can re-run activation on its own)')


def copy_if_absent(name, target_root):
    source = KIT_REPO_ROOT / name
    dest = target_root / name
    if not source.is_file():
        return
    if dest.exists():
        log(f'KEEP  {name} already exists; merge the kit copy in manually (kit source: {source})')
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, dest)
    log(f'COPY  {name}')


def merge_hook_settings(target_root):
    source = json.loads((KIT_REPO_ROOT / '.claude/settings.json').read_text())
    dest_path = target_root / '.claude/settings.json'
    dest = json.loads(dest_path.read_text()) if dest_path.exists() else {}
    dest.setdefault('hooks', {})
    added_events = []
    for event, source_entries in source['hooks'].items():
        dest_entries = dest['hooks'].setdefault(event, [])
        existing = {(entry.get('matcher'), h.get('type'), h.get('command')) for entry in dest_entries for h in entry.get('hooks', [])}
        added = False
        for entry in source_entries:
            key = (entry.get('matcher'), entry['hooks'][0].get('type'), entry['hooks'][0].get('command'))
            if key not in existing:
                dest_entries.append(entry)
                added = True
        if added:
            added_events.append(event)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    dest_path.write_text(json.dumps(dest, indent=2) + '\n')
    log(f"MERGE .claude/settings.json ({', '.join(added_events)} hook(s))" if added_events else 'KEEP  .claude/settings.json already has all kit hooks')


def merge_gitignore(target_root):
    path = target_root / '.gitignore'
    existing = path.read_text().splitlines() if path.exists() else []
    missing = [line for line in GITIGNORE_LINES if line not in existing]
    if not missing:
        log('KEEP  .gitignore already covers kit state/caches')
        return
    with path.open('a') as handle:
        if existing and existing[-1] != '':
            handle.write('\n')
        handle.write('\n'.join(missing) + '\n')
    log(f'MERGE .gitignore (+{len(missing)} lines)')


def _is_unset_template(path):
    """True for the kit's own placeholder project.yaml (project: CHANGE_ME), never for a real project's context."""
    if not path.exists():
        return True
    first_line = path.read_text().splitlines()[0] if path.read_text().strip() else ''
    return first_line.strip() == 'project: CHANGE_ME'


def write_project_identity(target_kit_dir, project, project_type):
    path = target_kit_dir / 'project-context/project.yaml'
    if not _is_unset_template(path):
        log(f'KEEP  {path.relative_to(target_kit_dir.parent)} already set; not overwriting discovered context')
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f'project: {project}\n'
        f'project_type: {project_type}\n'
        'context_status: MISSING\n'
        'repositories: []\n'
        'modules: []\n'
        'integrations: []\n'
        'last_indexed_revision: null\n'
    )
    log(f'WRITE {path.relative_to(target_kit_dir.parent)} (project={project}, type={project_type})')
    index_path = target_kit_dir / 'project-context/context-index.yaml'
    if not index_path.exists():
        index_path.write_text('system:\n  status: MISSING\nmodules: {}\nfeatures: {}\n')
        log(f'WRITE {index_path.relative_to(target_kit_dir.parent)}')


def run(cmd, cwd):
    log('RUN   ' + ' '.join(str(c) for c in cmd))
    result = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)
    return result.returncode == 0


def verify(target_root):
    target_kit_dir = target_root / 'agentic'
    checks = []
    checks.append(('agentic/ present', target_kit_dir.is_dir()))
    checks.append(('AGENTS.md present', (target_root / 'AGENTS.md').is_file()))
    hook_wired = False
    session_start_wired = False
    precompact_wired = False
    settings_path = target_root / '.claude/settings.json'
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text())
            hook_wired = any('Bash' in (entry.get('matcher') or '') for entry in settings.get('hooks', {}).get('PreToolUse', []))
            session_start_wired = any(
                'session_start_check.py' in h.get('command', '')
                for entry in settings.get('hooks', {}).get('SessionStart', [])
                for h in entry.get('hooks', [])
            )
            precompact_wired = any(
                'precompact_checkpoint.py' in h.get('command', '')
                for entry in settings.get('hooks', {}).get('PreCompact', [])
                for h in entry.get('hooks', [])
            )
        except (ValueError, OSError):
            hook_wired = False
            session_start_wired = False
            precompact_wired = False
    checks.append(('PreToolUse gate hook wired in .claude/settings.json', hook_wired))
    checks.append(('gate hook script present', (target_kit_dir / 'runtime/hooks/pretooluse_gate.py').is_file()))
    checks.append(('SessionStart midflight-check hook wired in .claude/settings.json', session_start_wired))
    checks.append(('midflight-check script present', (target_kit_dir / 'runtime/hooks/session_start_check.py').is_file()))
    checks.append(('PreCompact checkpoint hook wired in .claude/settings.json', precompact_wired))
    checks.append(('precompact-checkpoint script present', (target_kit_dir / 'runtime/hooks/precompact_checkpoint.py').is_file()))
    checks.append(('runtime db initialized', (target_kit_dir / 'runtime/state/agentic.db').is_file()))
    checks.append(('/agentic-init skill available for re-runs', (target_root / '.claude/skills/agentic-init/SKILL.md').is_file()))
    log('')
    log('Activation status:')
    ok = True
    for label, passed in checks:
        log(('  PASS  ' if passed else '  FAIL  ') + label)
        ok = ok and passed
    return ok


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', type=Path, default=Path.cwd(), help='Host project root (default: current directory)')
    parser.add_argument('--project', required=True, help='Project name recorded in project.yaml')
    parser.add_argument('--type', choices=['greenfield', 'brownfield'], required=True)
    parser.add_argument('--force', action='store_true', help='Back up and overwrite an existing agentic/ tree')
    args = parser.parse_args(argv)
    target_root = args.target.resolve()
    target_kit_dir = target_root / 'agentic'

    if target_root == KIT_REPO_ROOT:
        log('Target is the kit repository itself; skipping file copy, running identity + validation only.')
    else:
        target_root.mkdir(parents=True, exist_ok=True)
        copy_kit_tree(target_kit_dir, args.force)
        copy_if_absent('AGENTS.md', target_root)
        copy_if_absent('CLAUDE.md', target_root)
        merge_hook_settings(target_root)
        merge_gitignore(target_root)
        copy_skill(target_root, args.force)

    write_project_identity(target_kit_dir, args.project, args.type)

    ok = run([sys.executable, str(target_kit_dir / 'scripts/validate_structure.py'), '--write-manifests'], target_root)
    ok = run(['sh', str(target_kit_dir / 'scripts/validate-kit.sh')], target_root) and ok
    ok = run([sys.executable, str(target_kit_dir / 'runtime/python/agentic_runtime/cli.py'), 'init'], target_root) and ok

    active = verify(target_root)
    if not (ok and active):
        log('\nActivation incomplete -- fix FAIL rows above before trusting this project as governed.')
        return 1
    log('\nAgentic kit is active for this project.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
