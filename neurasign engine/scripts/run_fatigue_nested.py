#!/usr/bin/env python3
"""Immutable nested DailySense development experiment, never old test scoring."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from neurasign_engine import fatigue_nested


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('prepare', 'run', 'verify', 'report'))
    parser.add_argument('--target', choices=fatigue_nested.KINDS)
    args = parser.parse_args()
    if args.action == 'prepare':
        print(json.dumps(fatigue_nested.prepare(ROOT)), flush=True)
    elif args.action == 'run':
        for kind in (args.target,) if args.target else fatigue_nested.KINDS:
            fatigue_nested.run(ROOT, kind)
    elif args.action == 'verify':
        from neurasign_engine.fatigue_nested_verify import verify
        print(json.dumps(verify(ROOT)), flush=True)
    else:
        fatigue_nested.report_markdown(ROOT)


if __name__ == '__main__':
    main()
