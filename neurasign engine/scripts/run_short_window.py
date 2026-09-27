#!/usr/bin/env python3
"""Run the separate one-second evidence experiment without overwriting prior runs."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('stage', choices=['prepare', 'select', 'evaluate', 'report', 'verify'])
    args = parser.parse_args()
    if args.stage == 'prepare':
        from neurasign_engine import short_window_features as implementation
    elif args.stage in ('select', 'evaluate'):
        from neurasign_engine import short_window as implementation
    else:
        from neurasign_engine import short_window_report as implementation
    getattr(implementation, args.stage)(ROOT)
