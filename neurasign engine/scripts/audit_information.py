#!/usr/bin/env python3
"""Audit retained raw information and test fixed signal ablations on development people."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from neurasign_engine.information_audit import run_audit
from neurasign_engine.information_report import write_information_report

if __name__ == "__main__":
    report = run_audit(ROOT)
    write_information_report(ROOT, report)
    print(f"Completed information audit in {report['elapsed_seconds']:.1f} seconds.")
