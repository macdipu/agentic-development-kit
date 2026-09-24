"""Host instruction merging and read-only installation state inspection."""
import copy
import json
from pathlib import Path

BEGIN = '<!-- agentic-kit:start -->'
END = '<!-- agentic-kit:end -->'


def managed_text(existing, addition):
    block = BEGIN + '\n' + addition.rstrip() + '\n' + END
    if BEGIN in existing or END in existing:
        if existing.count(BEGIN) != 1 or existing.count(END) != 1 or existing.index(BEGIN) > existing.index(END):
            raise ValueError('Malformed managed instruction block; preserve and repair it before installing')
        before, rest = existing.split(BEGIN, 1)
        _, after = rest.split(END, 1)
        return before + block + after
    return existing + ('\n\n' if existing and not existing.endswith('\n\n') else '') + block + '\n'


def merge_hooks(existing, template):
    result = copy.deepcopy(existing)
    hooks = result.setdefault('hooks', {})
    if not isinstance(hooks, dict):
        raise ValueError('Existing hooks must be an object')
    for event, entries in template['hooks'].items():
        current = hooks.setdefault(event, [])
        if not isinstance(current, list):
            raise ValueError('Existing hook event must be an array: ' + event)
        for entry in entries:
            if entry not in current:
                current.append(copy.deepcopy(entry))
    return result


def install_claude_hooks(repo, template_path):
    settings = Path(repo) / '.claude/settings.json'
    current = json.loads(settings.read_text()) if settings.exists() else {}
    merged = merge_hooks(current, json.loads(Path(template_path).read_text()))
    changed = merged != current
    if changed:
        settings.parent.mkdir(parents=True, exist_ok=True)
        settings.write_text(json.dumps(merged, indent=2) + '\n')
    return {'settings': str(settings), 'changed': changed}


def unfinished_runs(root):
    runs_dir = Path(root) / 'agentic/data/runtime/state/runs'
    if not runs_dir.is_dir():
        return []
    unfinished = []
    for path in runs_dir.glob('*.json'):
        try:
            run = json.loads(path.read_text()).get('run')
        except (OSError, ValueError):
            continue
        if run and run.get('status') in ('RUNNING', 'BLOCKED'):
            unfinished.append(run['run_id'])
    return unfinished
