"""Installation diagnostics; all execution probes use disposable copies."""
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile


def detect_project(root):
    root = Path(root)
    frameworks, commands, unknowns = [], [], []
    def add(argv, permission='run_check'):
        commands.append({'argv': argv, 'permission': permission})
    add(['git', 'status', '--short'], 'read')
    add(['git', 'diff', '--check'], 'read')
    if (root / 'pubspec.yaml').exists():
        flutter = 'flutter:' in (root / 'pubspec.yaml').read_text()
        frameworks.append('flutter' if flutter else 'dart')
        prefix = ['fvm', 'flutter'] if flutter and (root / '.fvmrc').exists() else ['flutter' if flutter else 'dart']
        add(prefix + ['analyze'])
        add(prefix + ['test'])
        if flutter:
            add(prefix + ['devices'], 'read')
            unknowns.append('Preview needs an exact reviewed device/variant command with permission preview')
    if (root / 'package.json').exists():
        frameworks.append('node')
        package = json.loads((root / 'package.json').read_text())
        manager = 'pnpm' if (root / 'pnpm-lock.yaml').exists() else 'yarn' if (root / 'yarn.lock').exists() else 'npm'
        for name in ('test', 'lint', 'build', 'typecheck'):
            if name in package.get('scripts', {}):
                add([manager, 'run', name])
    if (root / 'pyproject.toml').exists() or (root / 'requirements.txt').exists():
        frameworks.append('python')
        unknowns.append('Select the project Python environment and register its exact test command')
    if (root / 'Cargo.toml').exists():
        frameworks.append('rust')
        add(['cargo', 'test'])
        add(['cargo', 'check'])
    if not frameworks:
        unknowns.append('Framework not detected; register reviewed project build/test commands')
    return {'frameworks': frameworks, 'commands': commands, 'unknowns': unknowns}


def probe_hooks(kit):
    from .markers import activate
    from .orchestrator import Orchestrator
    from .store import RuntimeStore
    with tempfile.TemporaryDirectory(prefix='agentic-doctor-') as temporary:
        root = Path(temporary)
        copy = root / 'agentic/kit'
        for name in ('runtime', 'config', 'skills'):
            shutil.copytree(kit / name, copy / name, ignore=shutil.ignore_patterns('__pycache__'))
        db = root / 'agentic/data/runtime/state/agentic.db'
        store = RuntimeStore(str(db))
        try:
            orch = Orchestrator(store, copy)
            run = orch.start('doctor-fixture', 'discovery', 'Check hook enforcement', repo=root)
            task, _ = orch.start_task(run.run_id, 'prompt-intake-adapter')
            marker = db.parent / 'active-task.json'
            activate(marker, db, run.run_id, task['id'])
            env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
            def hook(name, payload=None):
                result = subprocess.run([sys.executable, str(copy / 'runtime/hooks' / name)],
                                        input=json.dumps(payload or {}), capture_output=True, text=True,
                                        cwd=root, env=env, timeout=15)
                if result.returncode:
                    raise ValueError(result.stderr)
                return json.loads(result.stdout)
            denied = hook('pretooluse_gate.py', {'tool_name': 'Write', 'tool_input': {'file_path': str(root / 'source.py')}})
            if denied['hookSpecificOutput']['permissionDecision'] != 'deny':
                raise ValueError('Hook permitted an unauthorized source write')
            allowed = hook('pretooluse_gate.py', {'tool_name': 'Write', 'tool_input': {'file_path': str(root / 'agentic/data/artifacts/result.md')}})
            if allowed['hookSpecificOutput']['permissionDecision'] != 'allow':
                raise ValueError('Hook denied a permitted document write')
            session = hook('session_start_check.py')
            if run.run_id not in session['hookSpecificOutput']['additionalContext']:
                raise ValueError('Session hook did not identify the active run')
            hook('precompact_checkpoint.py')
            if not store.conn.execute("SELECT 1 FROM audit_events WHERE event='precompact_checkpoint'").fetchone():
                raise ValueError('Compaction hook did not persist its checkpoint')
        finally:
            store.conn.close()


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
        installation = json.loads(record.read_text())
    except (OSError, ValueError) as exc:
        return {'ok': False, 'checks': [{'check': 'installation record', 'ok': False, 'reason': str(exc)}]}
    mode, agent = installation.get('mode'), installation.get('agent')
    check('mode', lambda: require(mode in {'instruction-only', 'local-harness'} and agent in {'cli', 'claude'}, 'Unknown mode or agent'))
    for name in ('README.md', 'SKILL-CATALOG.md', 'ADOPTION.md'):
        check(name, lambda name=name: require((root / 'agentic' / name).is_file(), 'Missing packaged document'))
    check('instructions', lambda: require('<!-- agentic-kit:start -->' in (root / 'AGENTS.md').read_text(), 'Managed instructions missing'))
    def config():
        from .orchestrator import Orchestrator
        from .store import RuntimeStore
        with tempfile.TemporaryDirectory(prefix='agentic-storage-probe-') as temporary:
            store = RuntimeStore(str(Path(temporary) / 'probe.db'))
            try:
                Orchestrator(store, kit)
                with store.transaction():
                    store.audit('doctor', 'PROBE', {}, 'fixture')
                require(bool(store.conn.execute('SELECT 1 FROM audit_events').fetchone()), 'Storage commit failed')
            finally:
                store.conn.close()
    check('configuration and storage execution', config)
    if mode == 'local-harness':
        db = root / 'agentic/data/runtime/state/agentic.db'
        def database():
            require(db.is_file(), 'Runtime DB not initialized')
            with sqlite3.connect(db.as_uri() + '?mode=ro', uri=True) as conn:
                require(conn.execute('PRAGMA quick_check').fetchone()[0] == 'ok', 'Database integrity check failed')
        check('installed database', database)
        check('isolated hook execution', lambda: probe_hooks(kit))
        if agent == 'claude':
            def wiring():
                configured = json.loads((root / '.claude/settings.json').read_text())
                template = json.loads((kit / 'config/hooks.json').read_text())
                require(configured.get('disableAllHooks') is not True, 'Hooks are disabled by host settings')
                for event, entries in template['hooks'].items():
                    for entry in entries:
                        require(entry in configured.get('hooks', {}).get(event, []), 'Missing exact hook configuration: ' + event)
            check('Claude hook wiring', wiring)
            warnings.append('Hook probes run isolated code; verify invocation in one real Claude session')
        else:
            warnings.append('CLI mode requires task-start/call-tool/task-finish; native agent tools are not intercepted')
        marker = db.parent / 'active-task.json'
        if marker.exists():
            def active_state():
                pointer = json.loads(marker.read_text())
                pointer_db = Path(pointer['db']).resolve()
                with sqlite3.connect(pointer_db.as_uri() + '?mode=ro', uri=True) as conn:
                    row = conn.execute('SELECT metadata_json FROM workflow_runs WHERE run_id=?', (pointer['run_id'],)).fetchone()
                    active = json.loads(row[0]).get('active_task') if row else None
                    require(active and active['id'] == pointer['task_id'], 'Marker and database task disagree; recover explicitly')
            check('active task consistency', active_state)
    try:
        rules = json.loads((kit / 'config/allowed-commands.json').read_text())['commands']
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
    return {'ok': all(c['ok'] for c in checks), 'mode': mode, 'agent': agent,
            'checks': checks, 'warnings': sorted(set(warnings))}
