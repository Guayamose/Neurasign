#!/usr/bin/env python3
"""Run the bounded, development-only PaPaGei experiment."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('stage', choices=['extract', 'train', 'report', 'verify'])
    args = parser.parse_args()
    if args.stage == 'extract':
        from neurasign_engine.papagei import extract
        extract(ROOT)
    elif args.stage == 'verify':
        from neurasign_engine.papagei_verification import verify
        verify(ROOT)
    else:
        from neurasign_engine import papagei_training
        getattr(papagei_training, args.stage)(ROOT)
