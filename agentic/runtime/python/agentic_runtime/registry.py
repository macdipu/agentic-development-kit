from pathlib import Path
import re

class SkillRegistry:
    def __init__(self, skills_dir: str):
        self.skills_dir = Path(skills_dir)
    def discover(self):
        items = {}
        for p in self.skills_dir.glob("*/SKILL.md"):
            text = p.read_text(encoding="utf-8")
            name = re.search(r"^name:\s*(.+)$", text, re.M)
            desc = re.search(r"^description:\s*(.+)$", text, re.M)
            if name:
                items[name.group(1).strip()] = {"path": str(p), "description": desc.group(1).strip() if desc else ""}
        return items

class ToolRegistry:
    def __init__(self): self.tools = {}
    def register(self, name, handler, capabilities=None): self.tools[name] = {"handler": handler, "capabilities": set(capabilities or [])}
    def allowed(self, name, required_capability): return name in self.tools and required_capability in self.tools[name]["capabilities"]
