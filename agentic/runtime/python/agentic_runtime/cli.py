#!/usr/bin/env python3
import argparse
import json
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from agentic_runtime.orchestrator import Orchestrator
from agentic_runtime.policy import PLANNING, STAGES, WORK_TYPES
from agentic_runtime.store import RuntimeStore

KIT = HERE.parents[2]
DB = KIT / 'runtime/state/agentic.db'


def main(argv=None):
    parser = argparse.ArgumentParser(description='Local governed workflow runtime (trusted operator)')
    parser.add_argument('--db', type=Path, default=DB)
    sub = parser.add_subparsers(dest='cmd', required=True)
    sub.add_parser('init')
    sub.add_parser('list')
    start = sub.add_parser('start')
    start.add_argument('--project', required=True)
    start.add_argument('--type', choices=sorted(WORK_TYPES), required=True)
    start.add_argument('--title', required=True)
    start.add_argument('--repo', type=Path, default=KIT.parent)
    start.add_argument('--planning', choices=sorted(PLANNING), default='NO_REPLAN')
    start.add_argument('--dry-run', action='store_true')
    for name in ('show', 'eligible', 'cancel'):
        sub.add_parser(name).add_argument('run_id')
    transition = sub.add_parser('transition')
    transition.add_argument('run_id')
    transition.add_argument('stage', choices=sorted(STAGES))
    approval = sub.add_parser('approve')
    approval.add_argument('run_id')
    approval.add_argument('--gate', choices=['technical', 'release', 'uat'], required=True)
    approval.add_argument('--by', required=True)
    approval.add_argument('--decision', choices=['APPROVED', 'REJECTED'], default='APPROVED')
    approval.add_argument('--comment', default='')
    context = sub.add_parser('context')
    context.add_argument('run_id')
    context.add_argument('paths', nargs='+', help='Reviewed scope files, relative to --repo from start')
    result = sub.add_parser('result')
    result.add_argument('run_id')
    result.add_argument('--skill', required=True)
    result.add_argument('--file', type=Path, required=True)
    for name in ('reopen', 'recover'):
        command = sub.add_parser(name)
        command.add_argument('run_id')
        command.add_argument('--reason', required=True)
    args = parser.parse_args(argv)
    store = None
    try:
        store = RuntimeStore(str(args.db))
        orch = Orchestrator(store, KIT)
        if args.cmd == 'init':
            output = {'db': str(args.db.resolve())}
        elif args.cmd == 'list':
            output = store.list_runs()
        elif args.cmd == 'start':
            output = orch.start(args.project, args.type, args.title, args.dry_run, args.repo, args.planning)
        elif args.cmd == 'show':
            output = store.get_run(args.run_id)
            if output is None:
                raise ValueError('Unknown run')
        elif args.cmd == 'eligible':
            output = orch.eligible_skills(args.run_id)
        elif args.cmd == 'transition':
            output = orch.transition(args.run_id, args.stage)
        elif args.cmd == 'approve':
            output = orch.approve(args.run_id, args.gate, args.by, args.decision, args.comment)
        elif args.cmd == 'context':
            output = orch.record_context(args.run_id, args.paths)
        elif args.cmd == 'result':
            submitted = json.loads(args.file.read_text())
            output = orch.execute(args.run_id, args.skill, lambda context, call_tool: submitted)
        elif args.cmd in {'reopen', 'recover'}:
            output = getattr(orch, args.cmd)(args.run_id, args.reason)
        else:
            output = orch.cancel(args.run_id)
        print(json.dumps(output.to_dict() if hasattr(output, 'to_dict') else output, indent=2))
        return 0
    except (ValueError, OSError, RuntimeError, sqlite3.Error) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    finally:
        if store:
            store.conn.close()


if __name__ == '__main__':
    raise SystemExit(main())
