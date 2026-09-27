#!/usr/bin/env python3
"""Run the registered anonymous workload research experiment 021."""
from pathlib import Path
import argparse
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))

from neurasign_engine import workload_improvement as experiment

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('stage', choices=['prepare', 'run', 'report', 'verify'])
    args = parser.parse_args()
    if args.stage in ('prepare', 'run'):
        getattr(experiment, args.stage)(ROOT)
    else:
        from neurasign_engine import workload_improvement_report
        getattr(workload_improvement_report, args.stage)(ROOT)
