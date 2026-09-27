#!/usr/bin/env python3
"""Explicit selection/evaluation stages keep Lab2 outside all model choices."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('stage', choices=['prepare', 'select', 'evaluate', 'report', 'verify'])
    args = parser.parse_args()
    if args.stage in ('prepare', 'select', 'evaluate'):
        from neurasign_engine import personalization as implementation
    else:
        from neurasign_engine import personalization_report as implementation
    getattr(implementation, args.stage)(ROOT)
