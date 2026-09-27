#!/usr/bin/env python3
"""Build causal sensor windows and evaluate all supported heads without test reuse."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from neurasign_engine.causal_data import build_causal_dataset
from neurasign_engine.causal_training import train_causal

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--rebuild-data", action="store_true")
    args = parser.parse_args()
    data, audit = build_causal_dataset(ROOT, rebuild=args.rebuild_data)
    report = train_causal(ROOT, data, audit)
    print(f"Completed causal training in {report['elapsed_seconds']} seconds.")
