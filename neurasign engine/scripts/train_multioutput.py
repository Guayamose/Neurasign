#!/usr/bin/env python3
"""Prepare and train the offline wrist-only multi-output research bundle."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))

from neurasign_engine.data import build_dataset
from neurasign_engine.training import train

if __name__ == "__main__":
    data,audit = build_dataset(ROOT)
    print(f"Prepared {len(data):,} windows from {audit['label_units']} labeled intervals",flush=True)
    report = train(ROOT,data,audit)
    print(json.dumps({"status":"complete","targets":list(report["targets"]),"elapsed_seconds":report["elapsed_seconds"]},indent=2))
