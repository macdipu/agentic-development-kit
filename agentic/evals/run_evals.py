#!/usr/bin/env python3
import json
from pathlib import Path

def main():
    cases = list((Path(__file__).parent / "cases").glob("*.json"))
    failed = 0
    for p in cases:
        case = json.loads(p.read_text())
        required = {"name","input","expected"}
        if not required.issubset(case):
            print(f"FAIL {p.name}: missing fields"); failed += 1
        else: print(f"PASS {case['name']}")
    raise SystemExit(1 if failed else 0)
if __name__ == "__main__": main()
