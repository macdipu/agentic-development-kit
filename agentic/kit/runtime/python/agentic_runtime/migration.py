"""One-time move from the previous `.agent/` layout to the append-only one.

Previous: `.agent/runtime/runs/<RUN>.json` (one file rewritten on every save),
`.agent/runtime/active-task.json` and `route-cache.json`, and a committed
`.agent/HANDOFF.md` -- all tracked on branches, so two machines conflicted.

Now: `.agent/state/runs/<RUN>/events/*.json` (append-only, conflict-free),
`.agent/state/handoffs/*.md`, and machine-local files under `.agent/local/`.

Each old run becomes one snapshot event (terminal runs compacted). Old files are
removed from the index and disk; new files and the .gitignore lines are staged.
Nothing is committed: the operator reviews `git status` and commits.
"""
import json
import shutil
import subprocess
from pathlib import Path

from .paths import LEGACY_RUNS_DIR_REL

IGNORE_LINES = ['/.agent/local/', '/.agent/HANDOFF.md', '/.agent/state/**/.lock', '/.agent/state/**/.cache.json',
                '/.agent/state/**/*.tmp']


def _git(repo, *args):
    return subprocess.run(['git', *args], cwd=repo, capture_output=True, text=True, timeout=120,
                          encoding='utf-8', errors='replace')


def ensure_ignore(repo):
    path = Path(repo) / '.gitignore'
    lines = path.read_text(encoding='utf-8').splitlines() if path.exists() else []
    missing = [line for line in IGNORE_LINES if line not in lines]
    if missing:
        path.write_text('\n'.join(lines + missing) + '\n', encoding='utf-8', newline='\n')
    return missing


def migrate(repo, store):
    repo = Path(repo)
    legacy = repo / LEGACY_RUNS_DIR_REL
    runtime = legacy.parent
    if not runtime.is_dir():
        return {'migrated': False, 'reason': 'no .agent/runtime/ to migrate'}
    runs = sorted(legacy.glob('*.json')) if legacy.is_dir() else []
    for path in runs:
        state = json.loads(path.read_text(encoding='utf-8'))
        run = state.get('run') or {}
        if (run.get('metadata') or {}).get('active_task'):
            raise ValueError(f"Run {run.get('run_id')} has an active task; finish or recover it before migrating")
    converted, compacted = [], []
    for path in runs:
        state = json.loads(path.read_text(encoding='utf-8'))
        run_id = (state.get('run') or {}).get('run_id') or path.stem
        if store.run_ids() and run_id in store.run_ids():
            continue  # already migrated
        # metadata.repo stays valid: .agent/runtime/runs and .agent/state/runs are equally deep.
        store.import_state(run_id, state)
        converted.append(run_id)
        if (state.get('run') or {}).get('status') in ('COMPLETED', 'CANCELLED'):
            store.compact(run_id)
            compacted.append(run_id)
    local = repo / '.agent/local'
    local.mkdir(parents=True, exist_ok=True)
    moved = []
    if (runtime / 'route-cache.json').exists():
        shutil.move(str(runtime / 'route-cache.json'), str(local / 'route-cache.json'))
    pointer = runtime / 'active-task.json'
    if pointer.exists():
        # Its store path was relative to the old folder; rewrite it for the new one, or
        # drop a pointer whose task no longer exists (it would deny every tool call).
        try:
            data = json.loads(pointer.read_text(encoding='utf-8'))
            run = store.get_run(data.get('run_id', ''))
            active = (run.metadata.get('active_task') or {}) if run else {}
        except (OSError, ValueError):
            data, active = {}, {}
        if data.get('task_id') and active.get('id') == data['task_id']:
            from .markers import activate
            activate(local / 'active-task.json', store.store_dir, data['run_id'], data['task_id'])
            moved.append('active-task.json')
        pointer.unlink()
    for leftover in [p for p in runtime.iterdir() if p.name != 'runs']:
        # logs/, recovered-marker backups: machine-local history, kept, not deleted.
        target = local / ('legacy-' + leftover.name)
        shutil.move(str(leftover), str(target))
        moved.append(target.relative_to(repo).as_posix())
    handoff = repo / '.agent/HANDOFF.md'
    handoffs = repo / '.agent/state/handoffs'
    if handoff.exists() and not any(handoffs.glob('*.md')):
        handoffs.mkdir(parents=True, exist_ok=True)
        shutil.copy2(handoff, handoffs / '00000000T000000000000Z-migrated.md')
    ignored = ensure_ignore(repo)
    tracked = bool(_git(repo, 'rev-parse', '--is-inside-work-tree').returncode == 0)
    if tracked:
        _git(repo, 'rm', '-r', '--cached', '--quiet', '--ignore-unmatch', '--', str(LEGACY_RUNS_DIR_REL.parent.as_posix()),
             '.agent/HANDOFF.md')
    shutil.rmtree(runtime)
    if tracked:
        _git(repo, 'add', '-A', '--', '.agent/state', '.agent/sessions', '.gitignore')
    return {'migrated': True, 'runs': converted, 'compacted': compacted, 'gitignore_added': ignored, 'kept_local': moved,
            'next': ['Review `git status` (old .agent/runtime/ removed, .agent/state/ added), then commit, e.g. '
                     '`agentic_runtime.cli commit --type chore --scope agent --subject "move agent state to '
                     'append-only layout" --trigger user-request`, and push',
                     'Other clones: commit or discard their own .agent/ changes, `git pull`, then run '
                     '`agentic_runtime.cli migrate-state` once to move their local pointer/cache']}
