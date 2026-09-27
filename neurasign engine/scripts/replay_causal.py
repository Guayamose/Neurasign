#!/usr/bin/env python3
"""Replay real recorded raw samples through the same incoming-block engine."""
import argparse
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import joblib
import numpy as np
from threadpoolctl import threadpool_limits
from neurasign_engine.causal import CausalStream, CHANNELS, FEATURES, extract_window, json_ready
from neurasign_engine.causal_data import source_manifest, read_segment
from neurasign_engine.streaming import dispatch


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--participant", default="UN_101")
    parser.add_argument("--session", default="Lab1", choices=["Lab1", "Lab2", "Wild"])
    parser.add_argument("--segment", default="n_back_easy")
    parser.add_argument("--seconds", type=int, default=180)
    parser.add_argument("--features-only", action="store_true")
    parser.add_argument("--write-events", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    split = json.loads((ROOT / "experiments/split-v1.json").read_text())
    if args.participant not in split["development"]:
        raise SystemExit("Replay verification uses development participants only")
    if Path(args.segment).name != args.segment:
        raise SystemExit("Segment must be one folder name")
    source, manifest = source_manifest(ROOT)
    segment = source / "UNIVERSE" / args.participant / args.session / "Labeled" / args.segment
    traces, provenance = read_segment(segment, source, manifest)
    stream = CausalStream()
    model = None if args.features_only else joblib.load(ROOT / "models/causal-v3.joblib")
    horizon = min(args.seconds, int(traces["bvp"].times[-1]))
    events_file = None
    if args.write_events:
        args.write_events.parent.mkdir(parents=True, exist_ok=True)
        events_file = args.write_events.open("w")
    outputs, timings = [], []
    with threadpool_limits(limits=2):
        for end in range(1, horizon + 1):
            for channel, trace in traces.items():
                mask = (trace.times >= end - 1) & (trace.times < end) & np.isfinite(trace.values)
                if not mask.any():
                    continue
                event = {"type": "samples", "channel": channel, "sample_rate_hz": trace.rate,
                         "unit": trace.unit, "timestamps": trace.times[mask].tolist(), "values": trace.values[mask].tolist()}
                dispatch(stream, event)
                if events_file:
                    events_file.write(json.dumps(event) + "\n")
            if end % 10:
                continue
            event = {"type": "watermark", "timestamp": float(end)}
            started = time.perf_counter()
            results = dispatch(stream, event, model=model)
            elapsed = time.perf_counter() - started
            if events_file:
                events_file.write(json.dumps(event) + "\n")
            for result in results:
                reference = extract_window(traces, result["window_end"])
                actual = [np.nan if result["features"][key] is None else result["features"][key] for key in FEATURES]
                np.testing.assert_allclose(actual, [reference["features"][key] for key in FEATURES], equal_nan=True)
                outputs.append({**result, "input_kind": "recording_replay", "source": provenance})
                timings.append(elapsed * 1000.)
    if events_file:
        events_file.close()
    payload = {"input_kind": "recording_replay", "participant": args.participant, "session": args.session,
               "segment": args.segment, "replayed_seconds": horizon, "outputs": len(outputs),
               "first_output_after_seconds": outputs[0]["window_end"] if outputs else None,
               "p50_compute_ms": float(np.median(timings)) if timings else None,
               "p95_compute_ms": float(np.quantile(timings, .95)) if timings else None,
               "prefix_equivalence_checked": True, "predictions": outputs}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(json_ready(payload), indent=2, allow_nan=False) + "\n")
    print(json.dumps({key: value for key, value in payload.items() if key != "predictions"}, indent=2))
