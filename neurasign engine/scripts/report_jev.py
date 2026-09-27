#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from neurasign_engine.jev_report import score

if __name__ == "__main__":
    report = score(ROOT)
    print({"requests": report["protocol"]["requests"], "invalid_answers": len(report["failures"]),
           "input_tokens": report["input_tokens"], "estimated_usd": report["estimated_list_price_usd"]})
