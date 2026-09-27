#!/usr/bin/env python3
"""Freeze the protocol and run real Jev calls; resume without replaying replies."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from neurasign_engine.jev_benchmark import prepare, run

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    if args.prepare_only:
        protocol = prepare(ROOT)
        print({key: protocol[key] for key in ("model", "requests", "universe_rows", "swell_rows")})
    else:
        run(ROOT)
