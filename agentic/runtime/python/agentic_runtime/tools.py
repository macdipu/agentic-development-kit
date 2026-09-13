import shlex
import subprocess
from pathlib import Path

from .registry import ToolRegistry

UNSAFE_SHELL_CHARS = set(';&|`$<>\n')

NATIVE_TOOL_CAPABILITY = {
    'Read': ('L0', False),
    'Glob': ('L0', False),
    'Grep': ('L0', False),
    'Write': ('L4', True),
    'Edit': ('L4', True),
    'NotebookEdit': ('L4', True),
    'Bash': ('L5', True),
}


def bash_allowed(command, allowed_commands):
    """Prefix-allowlist a shell command string that a real shell will later execute.

    Rejects shell metacharacters outright: a prefix match alone would let an
    allowlisted command smuggle a trailing `; rm -rf ~` past the gate.
    """
    if not isinstance(command, str) or not command.strip():
        return False
    if any(ch in command for ch in UNSAFE_SHELL_CHARS):
        return False
    return any(command == c or command.startswith(c + ' ') for c in allowed_commands)


def _resolve(root, path):
    root = Path(root).resolve()
    resolved = (root / path).resolve()
    if not resolved.is_relative_to(root):
        raise ValueError('Path escapes the project root: ' + str(path))
    return resolved


def build_default_tools(repo_root, allowed_commands):
    """Real tool handlers for the call_tool gateway; every argument is attacker-controlled model output."""
    tools = ToolRegistry()

    def read_file(path):
        target = _resolve(repo_root, path)
        if not target.is_file():
            raise ValueError('Not a file: ' + str(path))
        return {'path': str(path), 'content': target.read_text(encoding='utf-8')}

    def list_directory(path='.'):
        target = _resolve(repo_root, path)
        if not target.is_dir():
            raise ValueError('Not a directory: ' + str(path))
        return {'path': str(path), 'entries': sorted(p.name + ('/' if p.is_dir() else '') for p in target.iterdir())}

    def search_text(pattern, path='.'):
        import re
        root = Path(repo_root).resolve()
        target = _resolve(repo_root, path)
        expr = re.compile(pattern)
        matches = []
        for file in sorted(target.rglob('*')):
            if len(matches) >= 200:
                break
            if not file.is_file() or file.stat().st_size > 1_000_000:
                continue
            try:
                text = file.read_text(encoding='utf-8')
            except (UnicodeDecodeError, OSError):
                continue
            for lineno, line in enumerate(text.splitlines(), start=1):
                if expr.search(line):
                    matches.append(f'{file.relative_to(root)}:{lineno}:{line.strip()}')
                    if len(matches) >= 200:
                        break
        return {'matches': matches}

    def write_file(path, content):
        target = _resolve(repo_root, path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding='utf-8')
        return {'path': str(path), 'bytes_written': len(content.encode('utf-8'))}

    def run_command(command, args=None):
        if command not in allowed_commands:
            raise PermissionError('Command not in the governed allowlist: ' + command)
        extra = args or []
        if not isinstance(extra, list) or any(not isinstance(a, str) for a in extra):
            raise ValueError('args must be a list of strings')
        argv = shlex.split(command) + extra
        # shell=False: extra args are literal argv entries, never shell-interpreted.
        result = subprocess.run(argv, shell=False, cwd=str(Path(repo_root).resolve()), capture_output=True, text=True, timeout=300)
        return {'command': command, 'args': extra, 'returncode': result.returncode, 'stdout': result.stdout[-10000:], 'stderr': result.stderr[-10000:]}

    tools.register('read_file', read_file, 'L0', side_effecting=False)
    tools.register('list_directory', list_directory, 'L0', side_effecting=False)
    tools.register('search_text', search_text, 'L1', side_effecting=False)
    tools.register('write_file', write_file, 'L4', side_effecting=True)
    tools.register('run_command', run_command, 'L5', side_effecting=True)
    return tools
