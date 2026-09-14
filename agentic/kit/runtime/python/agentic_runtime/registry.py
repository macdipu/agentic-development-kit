import hashlib
import json
import re
from pathlib import Path


class SkillRegistry:
    def __init__(self, skills_dir, config_path=None):
        self.skills_dir = Path(skills_dir)
        self.config_path = Path(config_path) if config_path else self.skills_dir.parent / 'config' / 'skill-registry.json'

    def discover(self):
        config = json.loads(self.config_path.read_text())
        items = {}
        for path in sorted(self.skills_dir.glob('*/SKILL.md')):
            text = path.read_text(encoding='utf-8')
            name = re.search(r'^name:\s*(.+)$', text, re.M)
            desc = re.search(r'^description:\s*(.+)$', text, re.M)
            if not name or name.group(1).strip() != path.parent.name:
                raise ValueError('Skill name must match its directory: ' + str(path))
            name = name.group(1).strip()
            digest = hashlib.sha256()
            files = sorted(p for p in path.parent.rglob('*') if p.is_file())
            shared = self.skills_dir / 'RESULT-CONTRACT.md'
            if shared.exists():
                files.append(shared)
            for source in files:
                digest.update(str(source.relative_to(self.skills_dir)).encode())
                digest.update(b'\0' + source.read_bytes())
            items[name] = {'path': str(path), 'description': desc.group(1).strip() if desc else '', 'revision': digest.hexdigest(), 'stages': config.get('eligibility', {}).get(name, [])}
        return items

    def eligible(self, stage):
        return [name for name, item in self.discover().items() if stage in item['stages']]


class ToolRegistry:
    def __init__(self):
        self.tools = {}

    def register(self, name, handler, capability='L0', side_effecting=False):
        if name in self.tools or capability not in {'L0', 'L1', 'L2', 'L3', 'L4', 'L5', 'L6'}:
            raise ValueError('Duplicate tool or unsupported capability')
        if not callable(handler):
            raise ValueError('Tool handler must be callable')
        self.tools[name] = {'handler': handler, 'capability': capability, 'side_effecting': side_effecting}

    def allowed(self, name, ceiling):
        return name in self.tools and ceiling in {'L0', 'L1', 'L2', 'L3', 'L4', 'L5', 'L6'} and int(self.tools[name]['capability'][1:]) <= int(ceiling[1:])
