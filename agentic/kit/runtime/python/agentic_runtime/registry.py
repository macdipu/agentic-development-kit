import hashlib
import json
import re
from pathlib import Path

from .context import normalized_bytes


class SkillRegistry:
    def __init__(self, skills_dir, config_path=None):
        self.skills_dir = Path(skills_dir)
        self.config_path = Path(config_path) if config_path else self.skills_dir.parent / 'config' / 'skill-registry.json'

    def discover(self):
        config = json.loads(self.config_path.read_text(encoding='utf-8'))
        items = {}
        for path in sorted(self.skills_dir.glob('*/SKILL.md')):
            text = path.read_text(encoding='utf-8')
            name = re.search(r'^name:\s*(.+)$', text, re.M)
            desc = re.search(r'^description:\s*(.+)$', text, re.M)
            if not name or name.group(1).strip() != path.parent.name:
                raise ValueError('Skill name must match its directory: ' + str(path))
            name = name.group(1).strip()
            files = sorted(p for p in path.parent.rglob('*') if p.is_file())
            shared = self.skills_dir / 'RESULT-CONTRACT.md'
            if shared.exists():
                files.append(shared)
            items[name] = {'path': str(path), 'description': desc.group(1).strip() if desc else '',
                           'revision': self._digest(files), 'legacy_revisions': self._legacy_digests(files),
                           'stages': config.get('eligibility', {}).get(name, [])}
        return items

    def _digest(self, files):
        """Portable revision: '/' paths and LF-normalized text, identical on every OS checkout."""
        digest = hashlib.sha256()
        for source in files:
            digest.update(source.relative_to(self.skills_dir).as_posix().encode())
            digest.update(b'\0' + normalized_bytes(source.read_bytes()))
        return digest.hexdigest()

    def _legacy_digests(self, files):
        """Pre-portable revisions (native separator, raw bytes) of the same content, for both
        separators. `migrate-pins` accepts a recorded pin only if it equals one of these, which
        proves the skill content itself is unchanged."""
        results = set()
        for sep in ('/', '\\'):
            digest = hashlib.sha256()
            for source in files:
                digest.update(sep.join(source.relative_to(self.skills_dir).parts).encode())
                digest.update(b'\0' + source.read_bytes())
            results.add(digest.hexdigest())
        return sorted(results)

    def eligible(self, stage):
        return [name for name, item in self.discover().items() if stage in item['stages']]


class ToolRegistry:
    def __init__(self):
        self.tools = {}

    def register(self, name, handler, capability='L0', side_effecting=False, permission=None):
        if name in self.tools or capability not in {'L0', 'L1', 'L2', 'L3', 'L4', 'L5', 'L6'}:
            raise ValueError('Duplicate tool or unsupported capability')
        if not callable(handler):
            raise ValueError('Tool handler must be callable')
        if permission is not None and permission not in {'read', 'write_artifact', 'modify_code', 'run_check', 'preview'}:
            raise ValueError('Unknown tool permission')
        self.tools[name] = {'handler': handler, 'capability': capability, 'side_effecting': side_effecting, 'permission': permission}

    def allowed(self, name, ceiling, permissions=()):
        if name in self.tools and self.tools[name]['permission'] is not None:
            return self.tools[name]['permission'] in permissions
        return name in self.tools and ceiling in {'L0', 'L1', 'L2', 'L3', 'L4', 'L5', 'L6'} and int(self.tools[name]['capability'][1:]) <= int(ceiling[1:])
