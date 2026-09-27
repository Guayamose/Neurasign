#!/usr/bin/env python3
"""Independent checks of frozen inputs, example isolation and saved scores."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from neurasign_engine.causal import FEATURES
from neurasign_engine.schema import TARGETS
from neurasign_engine.jev_benchmark import read_key


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def close(a, b):
    assert abs(a-b) < 1e-8, (a, b)


def check_features(payload, row, names):
    assert set(payload) == set(names)
    for name in names:
        if pd.isna(row[name]):
            assert payload[name] is None
        else:
            close(payload[name], round(float(row[name]), 6))


def main():
    output = ROOT / "results/jev-v1"
    protocol = json.loads((output / "protocol.json").read_text())
    report = json.loads((output / "report.json").read_text())
    assert protocol == report["protocol"]
    assert sha(ROOT / "src/neurasign_engine/jev_benchmark.py") == protocol["benchmark_code_sha256"]
    assert sha(ROOT / "src/neurasign_engine/jev_report.py") == report["reporter_sha256"]
    for paths, base in ((protocol["input_sha256"], ROOT), (protocol["prepared_sha256"], output),
                        (report["historical_report_sha256"], ROOT)):
        for name, expected in paths.items():
            assert sha(base / name) == expected, name
    assert sha(output / "requests.jsonl") == protocol["requests_sha256"]
    assert sha(output / "responses.jsonl") == report["responses_sha256"]
    requests = [json.loads(x) for x in (output / "requests.jsonl").read_text().splitlines()]
    replies = [json.loads(x) for x in (output / "responses.jsonl").read_text().splitlines()]
    replies = {r["request_id"]: r for r in replies}
    index = pd.read_csv(output / "request-index.csv").set_index("request_id")
    assert len(requests) == len(replies) == len(index) == protocol["requests"]
    assert {r["request_id"] for r in requests} == set(replies) == set(index.index)
    source = {"universe": pd.read_csv(ROOT / "data/prepared/causal-v3/windows.csv.gz"),
              "swell": pd.read_csv(ROOT / "data/prepared/swell-v1/minutes.csv.gz")}
    references = json.loads((output / "reference-audit.json").read_text())
    keys = ["participant", "unit_id", "window_end"]
    folds = json.loads((ROOT / "results/causal-v3/report.json").read_text())["targets"]["mental_demand"]["folds"]
    swell_split = json.loads((ROOT / "results/swell-v1/report.json").read_text())["protocol"]["split"]
    tables = {d: frame.set_index(keys) for d, frame in source.items()}
    for item in requests:
        record = index.loc[item["request_id"]]
        dataset = record.dataset
        row = tables[dataset].loc[tuple(record[k] for k in keys)]
        names = FEATURES if dataset == "universe" else ["HR", "RMSSD", "SCL", "HR_minus_prior_rest", "RMSSD_minus_prior_rest", "SCL_minus_prior_rest"]
        state = item["body"]["state"]
        assert set(state) == {"measurement_context", "current"} | ({"labeled_reference_examples"} if record["mode"] == "eight_shot" else set())
        check_features(state["current"], row, names)
        assert item["body"]["model"] == protocol["model"]
        assert item["body"]["questions"] == protocol["questions"][dataset]
        if record["mode"] == "eight_shot":
            refs = references[record.reference_id]
            excluded = next(f["validation"] for f in folds if record.participant in f["validation"]) if dataset == "universe" else swell_split["test"]
            assert len(refs) == len(state["labeled_reference_examples"]) == 8
            assert len({r["participant"] for r in refs}) == 8
            assert not {r["participant"] for r in refs} & set(excluded)
            for metadata, example in zip(refs, state["labeled_reference_examples"]):
                original = tables[dataset].loc[tuple(metadata[k] for k in keys)]
                check_features(example["measurements"], original, names)
                assert set(example) == {"measurements", "ratings"}
                assert set(example["ratings"]) == set(TARGETS)
                for target in TARGETS:
                    if pd.isna(original[target]):
                        assert example["ratings"][target] is None
                    else:
                        close(example["ratings"][target], float(original[target]))
    checked = 0
    for dataset in ("universe", "swell"):
        for target in TARGETS:
            frame = pd.read_csv(output / f"{dataset}-{target}-predictions.csv.gz")
            for mode in ("zero_shot", "eight_shot"):
                request_index = index[(index.dataset == dataset) & (index["mode"] == mode)].reset_index().set_index(keys)
                for _, row in frame.iterrows():
                    request_id = request_index.loc[tuple(row[k] for k in keys), "request_id"]
                    if pd.notna(row[mode]):
                        response = replies[request_id]["response"]
                        assert response["model"] == protocol["model"]
                        answer = response["answers"][target]
                        close(float(answer["choice"].removeprefix("rating_")), float(row[mode]))
                        close(float(answer["confidence"]), float(row[mode+"_confidence"]))
            valid = frame.dropna(subset=["zero_shot", "eight_shot"])
            for method, result in report["datasets"][dataset][target]["metrics"].items():
                work = valid[keys].copy()
                work["error"] = abs(valid[target]-valid[method])
                work["agree"] = ((np.floor(valid[method]+.5) == valid[target]) if dataset == "universe" and target == "mental_effort"
                                 else work.error <= (10 if dataset == "universe" else 1))
                person = work.groupby(["participant", "unit_id"])[["error", "agree"]].mean().groupby("participant").mean()
                close(person.error.mean(), result["mae"])
                close(person.agree.mean()*100, result["agreement_percent"])
                assert result["rows"] == len(valid)
                checked += 2
    # Inspect only task artifacts for the in-memory secret; never print the value.
    key = read_key(ROOT).encode()
    scanned = 0
    for path in list(output.glob("*.json*")) + list((ROOT / "experiments").glob("006-*")):
        assert key not in path.read_bytes(), "Credential found in a benchmark artifact"
        scanned += 1
    result = {"passed": True, "requests_checked": len(requests), "replies_checked": len(replies),
              "scalar_metrics_recomputed": checked, "payload_and_reference_isolation": True,
              "frozen_input_hashes": True, "credential_artifacts_checked": scanned,
              "response_model_counts": dict(Counter(r.get("response", {}).get("model", "none") for r in replies.values())),
              "report_sha256": sha(output / "report.json")}
    (output / "verification.json").write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
