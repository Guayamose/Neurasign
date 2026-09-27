#!/usr/bin/env python3
"""Read ordered JSONL sample/observation events and emit causal engine outputs."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import joblib
from threadpoolctl import threadpool_limits
from neurasign_engine.causal import CausalStream
from neurasign_engine.streaming import ObservationBridge, dispatch


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, default=ROOT / "models/causal-v3.joblib")
    parser.add_argument("--features-only", action="store_true")
    parser.add_argument("--binding", type=Path, help="Trusted JSON with source_id and sample_rates keyed by metric ID")
    args = parser.parse_args()
    stream = CausalStream()
    model = None if args.features_only else joblib.load(args.model)
    bridge = None
    if args.binding:
        binding = json.loads(args.binding.read_text())
        bridge = ObservationBridge(stream, binding["source_id"], binding["sample_rates"])
    with threadpool_limits(limits=2):
        for number, line in enumerate(sys.stdin, 1):
            if not line.strip():
                continue
            try:
                for output in dispatch(stream, json.loads(line), model=model, bridge=bridge):
                    print(json.dumps(output, allow_nan=False), flush=True)
            except (ValueError, TypeError, KeyError) as error:
                print(json.dumps({"line": number, "error": str(error)}), file=sys.stderr, flush=True)
                raise SystemExit(2)
