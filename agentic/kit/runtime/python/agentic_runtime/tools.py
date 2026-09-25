import shlex
import subprocess
from pathlib import Path

from .paths import PROTECTED_DIRS_REL
from .registry import ToolRegistry

UNSAFE_SHELL_CHARS = set(';&|`$<>\n\r')

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
    try:
        command_rule(command, [], allowed_commands)
        return True
    except (ValueError, PermissionError):
        return False


def split_command(command):
    """POSIX shell words; an unquoted Windows path (C:\\x\\python.exe) keeps its backslashes."""
    if '\\' in command and not any(q in command for q in '\'"'):
        return command.split()
    return shlex.split(command)


def command_rule(command, args, rules):
    """Match the entire argv; extra flags cannot broaden an approved command."""
    if not isinstance(command, str) or not command.strip() or any(c in command for c in UNSAFE_SHELL_CHARS):
        raise PermissionError('Shell expressions are not governed commands')
    if not isinstance(args, list) or any(not isinstance(a, str) for a in args):
        raise ValueError('args must be a list of strings')
    argv = split_command(command) + args
    for rule in rules:
        expected = split_command(rule) if isinstance(rule, str) else rule.get('argv')
        permission = 'run_check' if isinstance(rule, str) else rule.get('permission')
        if argv == expected and permission in {'read', 'run_check', 'preview'}:
            return argv, permission
    raise PermissionError('Full command and arguments are not allowlisted: ' + command)


def _resolve(root, path):
    root = Path(root).resolve()
    resolved = (root / path).resolve()
    if not resolved.is_relative_to(root):
        raise ValueError('Path escapes the project root: ' + str(path))
    return resolved


def validate_write(root, path, artifact_only=False):
    target = _resolve(root, path)
    relative = target.relative_to(Path(root).resolve())
    if '.git' in relative.parts:
        raise PermissionError('Direct writes to Git internals are denied')
    if any(relative.parts[:len(d.parts)] == d.parts for d in PROTECTED_DIRS_REL):
        raise PermissionError('Direct writes to the runtime ledger are denied; use the runtime CLI')
    if artifact_only:
        allowed = ('agentic/data/project-context/', 'agentic/data/work-items/', 'agentic/data/artifacts/')
        if not relative.as_posix().startswith(allowed) or target.suffix not in {'.md', '.json', '.yaml', '.yml', '.txt', '.csv'}:
            raise PermissionError('Artifact writes require a document under a project artifact directory')
    return target


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
        files = [target] if target.is_file() else target.rglob('*')
        for file in files:
            if len(matches) >= 200:
                break
            # Validate each candidate: an in-root directory may contain a file
            # symlink targeting a private file outside the project.
            try:
                _resolve(root, file)
            except (ValueError, OSError):
                continue
            if '.git' in file.relative_to(root).parts:
                continue
            if not file.is_file() or file.stat().st_size > 1_000_000:
                continue
            try:
                text = file.read_text(encoding='utf-8')
            except (UnicodeDecodeError, OSError):
                continue
            for lineno, line in enumerate(text.splitlines(), start=1):
                if expr.search(line):
                    matches.append(f'{file.relative_to(root).as_posix()}:{lineno}:{line.strip()}')
                    if len(matches) >= 200:
                        break
        return {'matches': matches}

    def write_file(path, content):
        target = validate_write(repo_root, path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding='utf-8')
        return {'path': str(path), 'bytes_written': len(content.encode('utf-8'))}

    def write_artifact(path, content):
        validate_write(repo_root, path, artifact_only=True)
        return write_file(path, content)

    def run_command(command, args=None):
        return execute_command(command, args, preview=False)

    def run_preview(command, args=None):
        return execute_command(command, args, preview=True)

    def execute_command(command, args, preview):
        extra = [] if args is None else args
        argv, permission = command_rule(command, extra, allowed_commands)
        if (permission == 'preview') != preview:
            raise PermissionError('Use the tool matching the command permission')
        # shell=False: extra args are literal argv entries, never shell-interpreted.
        result = subprocess.run(argv, shell=False, cwd=str(Path(repo_root).resolve()), capture_output=True, text=True, timeout=300, encoding='utf-8', errors='replace')
        return {'command': command, 'args': extra, 'returncode': result.returncode, 'stdout': result.stdout[-10000:], 'stderr': result.stderr[-10000:]}

    tools.register('read_file', read_file, 'L0', permission='read')
    tools.register('list_directory', list_directory, 'L0', permission='read')
    tools.register('search_text', search_text, 'L1', permission='read')
    tools.register('write_artifact', write_artifact, 'L2', side_effecting=True, permission='write_artifact')
    tools.register('write_file', write_file, 'L4', side_effecting=True, permission='modify_code')
    tools.register('run_command', run_command, 'L5', side_effecting=True, permission='run_check')
    tools.register('run_preview', run_preview, 'L5', side_effecting=True, permission='preview')
    return tools
