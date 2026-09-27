#!/usr/bin/env python3
"""Run the isolated anonymous public-data self-report benchmark."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('stage', choices=['prepare', 'select', 'evaluate', 'report', 'verify'])
    args = parser.parse_args()
    from neurasign_engine import stress_benchmark
    getattr(stress_benchmark, args.stage)(ROOT)
