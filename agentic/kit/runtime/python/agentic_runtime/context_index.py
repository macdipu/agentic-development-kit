"""Read-only freshness check for `agentic/data/project-context/context-index.yaml`.

A module marked AVAILABLE is only reusable while the evidence behind it still exists
and still matches. Nothing re-verified that after the fact, so an entry could say
AVAILABLE while every file it hashed had been moved away. This check reports such
entries; it never rewrites the index or marks anything fresh -- refreshing context
means re-reviewing it (project-discovery-agent / baseline-verifier).
"""
import json
from pathlib import Path

from .context import file_hash, posix_key

INDEX = Path('agentic/data/project-context/context-index.yaml')
REUSABLE = {'AVAILABLE', 'READY', 'APPROVED', 'TECHNICAL_READY'}


def _scalar(text):
    text = text.split(' #', 1)[0].strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in '"\'':
        return text[1:-1]
    return text


def parse_index(text):
    """Nested mappings of scalars from the YAML subset the index uses. Lists, block
    scalars (`>-`, `|`) and comments are skipped; they carry notes, not status."""
    root, stack, skip_deeper = {}, [(-1, None)], None
    stack[0] = (-1, root)
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith('#'):
            continue
        indent = len(raw) - len(raw.lstrip(' '))
        if skip_deeper is not None:
            if indent > skip_deeper:
                continue
            skip_deeper = None
        if stripped.startswith('- ') or stripped == '-' or ':' not in stripped:
            continue
        key, _, value = stripped.partition(':')
        key, value = _scalar(key), value.strip()
        while stack and stack[-1][0] >= indent:
            stack.pop()
        parent = stack[-1][1]
        if not isinstance(parent, dict):
            continue
        if not value:
            child = {}
            parent[key] = child
            stack.append((indent, child))
        elif value in ('>', '>-', '|', '|-', '>+', '|+'):
            parent[key] = ''
            skip_deeper = indent
        elif value in ('{}', '[]'):
            parent[key] = {} if value == '{}' else []
        else:
            parent[key] = _scalar(value)
    return root


def _entries(index):
    if isinstance(index.get('system'), dict):
        yield 'system', index['system']
    for section in ('modules', 'features', 'project_docs'):
        for name, entry in (index.get(section) or {}).items() if isinstance(index.get(section), dict) else []:
            if isinstance(entry, dict):
                yield f'{section}.{name}', entry


def check(repo_root):
    """{'ok': bool, 'entries': [...]} -- each reusable entry with its evidence state."""
    root = Path(repo_root).resolve()
    path = root / INDEX
    if not path.is_file():
        return {'ok': True, 'entries': [], 'note': 'no context-index.yaml'}
    report = []
    for name, entry in _entries(parse_index(path.read_text(encoding='utf-8'))):
        status = str(entry.get('status', '')).upper()
        if status not in REUSABLE:
            continue
        target = entry.get('context_file') or entry.get('path')
        item = {'entry': name, 'status': status, 'file': target, 'state': 'AVAILABLE', 'problems': []}
        if not target:
            item['state'], item['problems'] = 'UNVERIFIABLE', ['no context_file/path recorded']
        elif not (root / posix_key(target)).exists():
            item['state'], item['problems'] = 'STALE', [f'{target} is missing']
        elif target.endswith('.json') and (root / posix_key(target)).is_file():
            try:
                recorded = (json.loads((root / posix_key(target)).read_text(encoding='utf-8')).get('freshness') or {}).get('files') or {}
            except ValueError as exc:
                recorded, item['problems'] = {}, [f'{target} is not valid JSON: {exc}']
            for source, digest in recorded.items():
                candidate = root / posix_key(source)
                if not candidate.is_file():
                    item['problems'].append(f'{source} missing')
                elif file_hash(str(candidate)) != digest:
                    item['problems'].append(f'{source} changed')
            if item['problems']:
                item['state'] = 'STALE'
        report.append(item)
    return {'ok': all(i['state'] == 'AVAILABLE' for i in report), 'entries': report}
