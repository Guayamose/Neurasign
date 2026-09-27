#!/usr/bin/env python3
"""Evaluate physiological features in the user-provided SWELL workbook."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from neurasign_engine.swell import run_swell
from neurasign_engine.swell_report import write_report

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--workbook", type=Path, default=ROOT / "Behavioral-features - per minute (1).xlsx")
    args = parser.parse_args()
    result = run_swell(ROOT, args.workbook)
    write_report(ROOT, result)
    print(f"Completed separate SWELL experiment in {result['elapsed_seconds']:.1f} seconds.")
