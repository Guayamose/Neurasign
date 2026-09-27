#!/usr/bin/env python3
"""Run the fixed development-only nested multi-output improvement experiment."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from neurasign_engine.tuning import run_tuning

if __name__ == "__main__":
    report = run_tuning(ROOT)
    print(f"Completed in {report['elapsed_seconds']} seconds; original test excluded.")
