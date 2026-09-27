#!/usr/bin/env python3
"""Isolated WESAD wrist condition benchmark; never a production mental-state model."""
from pathlib import Path
import argparse
import resource
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('stage', choices=['freeze', 'download', 'prepare', 'run', 'verify'])
    args = parser.parse_args()
    from neurasign_engine import wesad_stress_022
    if args.stage == 'prepare':
        # Restrict memory and CPU before deserializing external numeric arrays.
        resource.setrlimit(resource.RLIMIT_AS, (8 * 1024 ** 3, 8 * 1024 ** 3))
        resource.setrlimit(resource.RLIMIT_CPU, (900, 900))
    getattr(wesad_stress_022, args.stage)(ROOT)
