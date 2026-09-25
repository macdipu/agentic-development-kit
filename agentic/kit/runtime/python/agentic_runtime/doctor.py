"""Installation diagnostics; all execution probes use disposable copies."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from .paths import ACTIVE_TASK_POINTER_REL, LEGACY_RUNS_DIR_REL, RUNS_DIR_REL


# Build output, dependencies, platform shells, and kit/agent folders never hold a project root.
_SKIP_DIRS = {'node_modules', '.git', '.next', 'build', 'dist', 'out', 'target', '.dart_tool', 'vendor',
              '.gradle', '.venv', 'venv', '__pycache__', '.idea', 'agentic', 'agentic-backups', '.agent',
              '.claude', '.codex'}
_MANIFESTS = ('pubspec.yaml', 'package.json', 'pom.xml', 'build.gradle', 'build.gradle.kts', 'Cargo.toml',
              'go.mod', 'pyproject.toml', 'requirements.txt')
_SCRIPT_WORDS = ('verify', 'test', 'check', 'lint')


def _project_dirs(root, depth=2):
    """Root plus subdirectories (<= depth) holding a build manifest, outermost first.
    A directory inside one already found for the same manifest (a Maven module under
    its aggregator pom) is left to that parent."""
    found, frontier = [], [root]
    for level in range(depth + 1):
        next_frontier = []
        for directory in frontier:
            manifests = {name for name in _MANIFESTS if (directory / name).is_file()}
            owned = any(directory.is_relative_to(parent) and parent != directory and manifests & kinds
                        for parent, kinds in found)
            if manifests and not owned:
                found.append((directory, manifests))
            # A Flutter/Dart package owns its platform folders (android/ gradle, web/, ...).
            if level < depth and 'pubspec.yaml' not in manifests:
                try:
                    children = sorted(p for p in directory.iterdir() if p.is_dir())
                except OSError:
                    children = []
                next_frontier += [c for c in children if c.name not in _SKIP_DIRS and not c.name.startswith('.')]
        frontier = next_frontier
    return found


def detect_project(root):
    """Allowlist candidates for every sub-project in a (mono)repo. Commands run from the
    repo root, and a governed Bash call cannot `cd`, so sub-projects use each tool's own
    directory flag; tools without one get a wrapper-script suggestion instead."""
    root = Path(root)
    frameworks, commands, unknowns = [], [], []
    def add(argv, permission='run_check'):
        rule = {'argv': argv, 'permission': permission}
        if rule not in commands:
            commands.append(rule)
    add(['git', 'status', '--short'], 'read')
    add(['git', 'diff', '--check'], 'read')
    for directory, manifests in _project_dirs(root):
        rel = directory.relative_to(root).as_posix()
        at_root = rel == '.'
        label = lambda name: name if at_root else f'{name}:{rel}'
        if 'pubspec.yaml' in manifests:
            flutter = 'flutter:' in (directory / 'pubspec.yaml').read_text(encoding='utf-8', errors='replace')
            frameworks.append(label('flutter' if flutter else 'dart'))
            prefix = ['fvm', 'flutter'] if flutter and (directory / '.fvmrc').exists() else ['flutter' if flutter else 'dart']
            if at_root:
                add(prefix + ['analyze'])
                add(prefix + ['test'])
            else:
                unknowns.append(f'{" ".join(prefix)} has no directory flag for {rel}: register a reviewed wrapper '
                                f'script (e.g. scripts/verify-{directory.name}.sh) as a run_check rule')
            if flutter:
                add(prefix + ['devices'], 'read')
                unknowns.append('Preview needs an exact reviewed device/variant command with permission preview')
        if 'package.json' in manifests:
            frameworks.append(label('node'))
            try:
                package = json.loads((directory / 'package.json').read_text(encoding='utf-8'))
            except ValueError:
                package = {}
            manager = 'pnpm' if (directory / 'pnpm-lock.yaml').exists() else 'yarn' if (directory / 'yarn.lock').exists() else 'npm'
            where = [] if at_root else {'npm': ['--prefix', rel], 'pnpm': ['--dir', rel], 'yarn': ['--cwd', rel]}[manager]
            for name in ('test', 'lint', 'build', 'typecheck'):
                if name in package.get('scripts', {}):
                    add([manager, *where, 'run', name])
        if 'pom.xml' in manifests:
            frameworks.append(label('maven'))
            add(['mvn', '-B', 'verify'] if at_root else ['mvn', '-B', '-f', f'{rel}/pom.xml', 'verify'])
        if manifests & {'build.gradle', 'build.gradle.kts'}:
            frameworks.append(label('gradle'))
            wrapper = (directory / 'gradlew').exists()
            add(['./gradlew', 'test'] if at_root and wrapper else ['gradle', 'test'] if at_root else ['gradle', '-p', rel, 'test'])
        if 'go.mod' in manifests:
            frameworks.append(label('go'))
            add(['go', 'test', './...'] if at_root else ['go', '-C', rel, 'test', './...'])
        if 'Cargo.toml' in manifests:
            frameworks.append(label('rust'))
            manifest = [] if at_root else ['--manifest-path', f'{rel}/Cargo.toml']
            add(['cargo', 'test', *manifest])
            add(['cargo', 'check', *manifest])
        if manifests & {'pyproject.toml', 'requirements.txt'}:
            frameworks.append(label('python'))
            unknowns.append(f'Select the Python environment for {rel} and register its exact test command')
    scripts = root / 'scripts'
    candidates = [f'sh scripts/{s.name}' for s in sorted(scripts.glob('*.sh')) if scripts.is_dir()
                  and any(word in s.stem for word in _SCRIPT_WORDS)] if scripts.is_dir() else []
    if candidates:
        # A name is not a review: suggest, never allowlist a script nobody read.
        unknowns.append('Review and, if they only verify, allowlist these wrapper scripts as run_check rules: '
                        + ', '.join(candidates))
    if not frameworks:
        unknowns.append('Framework not detected; register reviewed project build/test commands')
    return {'frameworks': frameworks, 'commands': commands, 'unknowns': unknowns}


def _assert_pretooluse_denies_source_write(hook, root):
    denied = hook('pretooluse_gate.py', {'tool_name': 'Write', 'tool_input': {'file_path': str(root / 'source.py')}})
    if denied['hookSpecificOutput']['permissionDecision'] != 'deny':
        raise ValueError('Hook permitted an unauthorized source write')


def _assert_pretooluse_denies_untasked_write(hook, root):
    # The run stays RUNNING with no active task: code writes must not slip through.
    verdict = hook('pretooluse_gate.py', {'tool_name': 'Edit', 'tool_input': {'file_path': str(root / 'source.py')}})
    if verdict['hookSpecificOutput'].get('permissionDecision') != 'deny':
        raise ValueError('Hook permitted a code write while a run was open with no active task')


def _assert_pretooluse_allows_artifact_write(hook, root):
    allowed = hook('pretooluse_gate.py', {'tool_name': 'Write', 'tool_input': {'file_path': str(root / 'agentic/data/artifacts/result.md')}})
    if allowed['hookSpecificOutput']['permissionDecision'] != 'allow':
        raise ValueError('Hook denied a permitted document write')


def _assert_session_start_identifies_run(hook, run):
    session = hook('session_start_check.py')
    if run.run_id not in session['hookSpecificOutput']['additionalContext']:
        raise ValueError('Session hook did not identify the active run')


def _assert_precompact_persists_checkpoint(hook, runs_dir, run):
    hook('precompact_checkpoint.py')
    from .store import RuntimeStore
    audit_events = RuntimeStore(str(runs_dir)).ledger(run.run_id).get('audit_events', [])
    if not any(e['event'] == 'precompact_checkpoint' for e in audit_events):
        raise ValueError('Compaction hook did not persist its checkpoint')


def probe_hooks(kit):
    from .markers import activate
    from .orchestrator import Orchestrator
    from .store import RuntimeStore
    with tempfile.TemporaryDirectory(prefix='agentic-doctor-') as temporary:
        root = Path(temporary)
        copy = root / 'agentic/kit'
        for name in ('runtime', 'config', 'skills'):
            shutil.copytree(kit / name, copy / name, ignore=shutil.ignore_patterns('__pycache__', '.pytest_cache'))
        runs_dir = root / RUNS_DIR_REL
        store = RuntimeStore(str(runs_dir))
        orch = Orchestrator(store, copy)
        run = orch.start('doctor-fixture', 'discovery', 'Check hook enforcement', repo=root)
        task, _ = orch.start_task(run.run_id, 'prompt-intake-adapter')
        marker = root / ACTIVE_TASK_POINTER_REL
        activate(marker, runs_dir, run.run_id, task['id'])
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
        def hook(name, payload=None):
            result = subprocess.run([sys.executable, str(copy / 'runtime/hooks' / name)],
                                    input=json.dumps(payload or {}), capture_output=True, text=True,
                                    cwd=root, env=env, timeout=15, encoding='utf-8', errors='replace')
            if result.returncode:
                raise ValueError(result.stderr)
            return json.loads(result.stdout)
        _assert_pretooluse_denies_source_write(hook, root)
        _assert_pretooluse_allows_artifact_write(hook, root)
        _assert_session_start_identifies_run(hook, run)
        _assert_precompact_persists_checkpoint(hook, runs_dir, run)
        marker.unlink()
        _assert_pretooluse_denies_untasked_write(hook, root)


def diagnose(root):
    root = Path(root).resolve()
    kit = root / 'agentic/kit'
    checks, warnings = [], []
    def check(name, operation):
        try:
            operation()
            checks.append({'check': name, 'ok': True})
        except Exception as exc:
            checks.append({'check': name, 'ok': False, 'reason': str(exc)})
    def require(condition, message):
        if not condition:
            raise ValueError(message)
    record = root / 'agentic/data/project-context/installation.json'
    try:
        installation = json.loads(record.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        return {'ok': False, 'checks': [{'check': 'installation record', 'ok': False, 'reason': str(exc)}]}
    mode, agent = installation.get('mode'), installation.get('agent')
    check('mode', lambda: require(mode in {'instruction-only', 'local-harness'} and agent in {'cli', 'claude', 'codex'}, 'Unknown mode or agent'))
    for name in ('README.md', 'SKILL-CATALOG.md', 'ADOPTION.md'):
        check(name, lambda name=name: require((root / 'agentic' / name).is_file(), 'Missing packaged document'))
    check('instructions', lambda: require('<!-- agentic-kit:start -->' in (root / 'AGENTS.md').read_text(encoding='utf-8'), 'Managed instructions missing'))
    def config():
        from .orchestrator import Orchestrator
        from .store import RuntimeStore
        with tempfile.TemporaryDirectory(prefix='agentic-storage-probe-') as temporary:
            store = RuntimeStore(str(Path(temporary) / 'runs'))
            Orchestrator(store, kit)
            with store.transaction():
                store.audit('doctor', 'PROBE', {}, 'fixture')
            require(any(store.store_dir.glob('*/events/*.json')), 'Storage commit failed')
    check('configuration and storage execution', config)
    if mode == 'local-harness':
        runs_dir = root / RUNS_DIR_REL
        def database():
            require(runs_dir.is_dir(), 'Runtime store not initialized')
            require(not (root / LEGACY_RUNS_DIR_REL).is_dir(),
                    'Previous .agent/runtime/ layout present; run `cli.py migrate-state`')
            for path in runs_dir.glob('*/events/*.json'):
                try:
                    json.loads(path.read_text(encoding='utf-8'))['ops']
                except (OSError, ValueError, KeyError) as exc:
                    raise ValueError(f'Corrupt run event {path.parent.parent.name}/{path.name}: {exc}')
        check('installed database', database)
        check('isolated hook execution', lambda: probe_hooks(kit))
        if agent == 'claude':
            def wiring():
                configured = json.loads((root / '.claude/settings.json').read_text(encoding='utf-8'))
                template = json.loads((kit / 'config/hooks.json').read_text(encoding='utf-8'))
                require(configured.get('disableAllHooks') is not True, 'Hooks are disabled by host settings')
                for event, entries in template['hooks'].items():
                    for entry in entries:
                        require(entry in configured.get('hooks', {}).get(event, []), 'Missing exact hook configuration: ' + event)
            check('Claude hook wiring', wiring)
            warnings.append('Hook probes run isolated code; verify invocation in one real Claude session')
        else:
            warnings.append('CLI mode requires task-start/call-tool/task-finish; native agent tools are not intercepted')
        marker = root / ACTIVE_TASK_POINTER_REL
        if marker.exists():
            def active_state():
                pointer = json.loads(marker.read_text(encoding='utf-8'))
                from .markers import store_dir_of
                pointer_dir = store_dir_of(marker, pointer)
                from .store import RuntimeStore
                run = RuntimeStore(str(pointer_dir)).get_run(pointer['run_id'])
                active = run.metadata.get('active_task') if run else None
                require(active and active['id'] == pointer['task_id'], 'Marker and database task disagree; recover explicitly')
            check('active task consistency', active_state)
    try:
        rules = json.loads((kit / 'config/allowed-commands.json').read_text(encoding='utf-8'))['commands']
        import shlex
        for rule in rules:
            argv = shlex.split(rule) if isinstance(rule, str) else rule['argv']
            executable = argv[0]
            available = (root / executable).is_file() if '/' in executable else shutil.which(executable)
            if not available:
                warnings.append('Command executable unavailable: ' + executable)
    except (OSError, ValueError, KeyError, IndexError) as exc:
        checks.append({'check': 'project commands', 'ok': False, 'reason': str(exc)})
    warnings.extend(installation.get('unknowns', []))
    try:
        tracked = subprocess.run(['git', 'ls-files', '--', '.agent/local'], cwd=root, capture_output=True, text=True,
                                 timeout=15, encoding='utf-8', errors='replace').stdout.split()
        if tracked:
            checks.append({'check': 'machine-local state untracked', 'ok': False,
                           'reason': '.agent/local/ is committed (' + ', '.join(tracked[:3]) + '); every clone would '
                                     'share one clone id. `git rm -r --cached .agent/local` and ignore /.agent/local/'})
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        from .context_index import check as context_check
        for entry in context_check(root)['entries']:
            if entry['state'] != 'AVAILABLE':
                warnings.append(f"Project context {entry['entry']} is marked {entry['status']} but is {entry['state']} "
                                f"({'; '.join(entry['problems'][:3])}); re-verify it before reuse (cli.py context-check)")
    except (OSError, ValueError) as exc:
        warnings.append('Could not check project-context freshness: ' + str(exc))
    return {'ok': all(c['ok'] for c in checks), 'mode': mode, 'agent': agent,
            'checks': checks, 'warnings': sorted(set(warnings))}
