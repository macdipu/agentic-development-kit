"""Host instruction merging and read-only installation state inspection."""
import copy
import json
from pathlib import Path
from .paths import RUNS_DIR_REL

BEGIN = '<!-- agentic-kit:start -->'
END = '<!-- agentic-kit:end -->'
IMPORT_AGENTS = '@AGENTS.md'


def managed_text(existing, addition):
    block = BEGIN + '\n' + addition.rstrip() + '\n' + END
    if BEGIN in existing or END in existing:
        if existing.count(BEGIN) != 1 or existing.count(END) != 1 or existing.index(BEGIN) > existing.index(END):
            raise ValueError('Malformed managed instruction block; preserve and repair it before installing')
        before, rest = existing.split(BEGIN, 1)
        _, after = rest.split(END, 1)
        return before + block + after
    return existing + ('\n\n' if existing and not existing.endswith('\n\n') else '') + block + '\n'


def claude_text(existing):
    """CLAUDE.md managed block importing AGENTS.md; a bare `@AGENTS.md` left outside the
    block (e.g. from a pre-kit CLAUDE.md) is dropped so the import is not doubled."""
    merged = managed_text(existing, IMPORT_AGENTS)
    before, rest = merged.split(BEGIN, 1)
    block, after = rest.split(END, 1)
    def drop(text):
        return '\n'.join(line for line in text.split('\n') if line.strip() != IMPORT_AGENTS)
    before = drop(before).strip('\n')
    return (before + '\n\n' if before else '') + BEGIN + block + END + drop(after)


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
    current = json.loads(settings.read_text(encoding='utf-8')) if settings.exists() else {}
    merged = merge_hooks(current, json.loads(Path(template_path).read_text(encoding='utf-8')))
    changed = merged != current
    if changed:
        settings.parent.mkdir(parents=True, exist_ok=True)
        settings.write_text(json.dumps(merged, indent=2) + '\n', encoding='utf-8', newline='\n')
    return {'settings': str(settings), 'changed': changed}


def unfinished_runs(root):
    from .paths import LEGACY_RUNS_DIR_REL
    from .store import RuntimeStore
    unfinished = []
    runs_dir = Path(root) / RUNS_DIR_REL
    if runs_dir.is_dir():
        unfinished += [r['run_id'] for r in RuntimeStore(str(runs_dir)).list_runs() if r.get('status') in ('RUNNING', 'BLOCKED')]
    legacy = Path(root) / LEGACY_RUNS_DIR_REL
    for path in legacy.glob('*.json') if legacy.is_dir() else []:
        try:
            run = json.loads(path.read_text(encoding='utf-8')).get('run')
        except (OSError, ValueError):
            continue
        if run and run.get('status') in ('RUNNING', 'BLOCKED'):
            unfinished.append(run['run_id'])
    return unfinished
