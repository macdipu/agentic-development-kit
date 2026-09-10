#!/usr/bin/env python3
import argparse, json, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from agentic_runtime.store import RuntimeStore
from agentic_runtime.orchestrator import Orchestrator

ROOT = HERE.parents[3]
DB = ROOT / "runtime" / "state" / "agentic.db"

def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init")
    s = sub.add_parser("start"); s.add_argument("--project", required=True); s.add_argument("--type", required=True); s.add_argument("--title", required=True); s.add_argument("--dry-run", action="store_true")
    l = sub.add_parser("list")
    a = sub.add_parser("approve"); a.add_argument("run_id"); a.add_argument("--gate", required=True); a.add_argument("--by", required=True); a.add_argument("--comment", default="")
    t = sub.add_parser("transition"); t.add_argument("run_id"); t.add_argument("stage")
    args = p.parse_args(); store = RuntimeStore(str(DB)); orch = Orchestrator(store)
    from datetime import datetime, timezone
    if args.cmd == "init": print(DB)
    elif args.cmd == "start": print(json.dumps(orch.start(args.project,args.type,args.title,args.dry_run).to_dict(), indent=2))
    elif args.cmd == "list": print(json.dumps(store.list_runs(), indent=2))
    elif args.cmd == "approve": store.approval(args.run_id,args.gate,args.by,"APPROVED",args.comment,datetime.now(timezone.utc).isoformat()); print("approved")
    elif args.cmd == "transition": print(json.dumps(orch.transition(args.run_id,args.stage).to_dict(), indent=2))
if __name__ == "__main__": main()
