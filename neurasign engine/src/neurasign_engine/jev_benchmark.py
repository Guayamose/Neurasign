"""Frozen, participant-separated Jev experiment on research data only.

No app integration, synthetic predictions, credential logging or local fallback.
Requests contain an explicit feature allow-list and optional training examples.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import shlex
import time
import urllib.error
import urllib.request

import numpy as np
import pandas as pd

from .causal import FEATURES
from .schema import TARGETS, SEED
from .training import save_json, weights

MODEL = "jev-1.13.0"
ENDPOINT = "https://api.typesafe.ai/v1/systemone"
MODES = ("zero_shot", "eight_shot")
SWELL_FEATURES = ["HR", "RMSSD", "SCL", "HR_minus_prior_rest", "RMSSD_minus_prior_rest", "SCL_minus_prior_rest"]
KEYS = ["participant", "unit_id", "window_end"]
NAMES = {"mental_effort": "mental effort", "mental_demand": "mental demand",
         "physical_demand": "physical demand", "temporal_demand": "time pressure",
         "perceived_performance": "recorded self-rated performance", "effort": "general effort"}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def rank_key(text):
    return hashlib.sha256(f"{SEED}:{text}".encode()).hexdigest()


def numeric(value):
    return round(float(value), 6) if pd.notna(value) and math.isfinite(float(value)) else None


def features(row, dataset):
    return {name: numeric(row[name]) for name in (FEATURES if dataset == "universe" else SWELL_FEATURES)}


def grid(dataset, target):
    if dataset == "universe":
        return list(range(1, 6)) if target == "mental_effort" else list(range(0, 101, 10))
    return list(range(16)) if target == "mental_effort" else list(range(11))


def questions(dataset):
    result = {}
    for target, name in NAMES.items():
        values = grid(dataset, target)
        levels = ["negligible", "very low", "low", "moderately low", "moderate", "moderately high", "high", "very high", "extremely high"]
        criteria = {}
        for i, value in enumerate(values):
            level = levels[round(i * (len(levels)-1) / (len(values)-1))]
            criteria[f"rating_{value}"] = f"{level.capitalize()} {name}: closest recorded rating is {value} on the stated scale."
        result[target] = {"type": "choice", "instructions": (
            f"Estimate the {name} questionnaire rating for state.current using its physiological measurements. "
            f"Choose the closest rating category on {values[0]} to {values[-1]}. "
            "Use state.labeled_reference_examples, when present, as examples from different people; "
            "their ratings do not describe state.current. Missing measurements are unknown, not zero. "
            "This is a forced-choice research benchmark: make your best estimate even when evidence is weak, "
            "and distribute probability across plausible categories. No medical diagnosis, emotion, "
            "fatigue, work assignment or objective productivity judgment is requested. "
            + ("For this source the numeric performance direction is unverified: preserve the recorded rating convention without claiming that higher means better. "
               if target == "perceived_performance" and dataset == "universe" else "")
            + ("Higher performance means better self-rated performance, not objective productivity. "
               if target == "perceived_performance" and dataset == "swell" else "")
            + ("Mental effort here is the exported RSME value, not a five-level category. "
               if target == "mental_effort" and dataset == "swell" else "")), "criteria": criteria}
    return result


def payload(row, dataset, examples):
    metadata = (
        "One trailing 60-second wrist window. EDA in microsiemens; skin temperature in degrees Celsius; "
        "heart rate in bpm; acceleration/motion in g; pulse intervals in milliseconds; pulse wave in arbitrary units. "
        "range means 90th minus 10th percentile; slope is per second; last20_minus_first20 is the difference "
        "between the last and first 20-second means. Pulse variability was masked when motion or pulse quality failed. "
        "No personal resting baseline is available. Questionnaire labels summarize a task, not an instantaneous state."
        if dataset == "universe" else
        "One precomputed minute from chest ECG and finger skin conductance, not wrist sensors. "
        "HR is bpm. RMSSD and SCL retain native exported units; their conversion to canonical units is unverified. "
        "The suffix minus_prior_rest is a difference from that person's preceding relaxation median, when available. "
        "Missing values remain null. Five demand/effort/performance ratings use 0-10; mental effort uses exported "
        "RSME units with a 0-15 benchmark grid. These are block questionnaire ratings, not instantaneous truth.")
    state = {"measurement_context": metadata, "current": features(row, dataset)}
    if examples:
        state["labeled_reference_examples"] = [
            {"measurements": features(e, dataset), "ratings": {t: numeric(e[t]) for t in TARGETS}}
            for e in examples]
    return {"model": MODEL, "state": state, "questions": questions(dataset)}


def choose_examples(rows, excluded):
    """Eight different fitting people, with label-independent row selection."""
    fitting = rows[~rows.participant.isin(excluded)]
    people = sorted(fitting.participant.unique(), key=rank_key)[:8]
    selected = []
    for person in people:
        group = fitting[fitting.participant == person]
        index = min(group.index, key=lambda i: rank_key(f"{group.loc[i, 'unit_id']}:{group.loc[i, 'window_end']}"))
        selected.append(group.loc[index].to_dict())
    if len(selected) != 8 or {x["participant"] for x in selected} & set(excluded):
        raise ValueError("Eight disjoint reference participants are required")
    return selected


def prepare(root):
    output = root / "results/jev-v1"
    output.mkdir(parents=True, exist_ok=True)
    protocol_path = output / "protocol.json"
    if protocol_path.exists():
        saved = json.loads(protocol_path.read_text())
        if saved["benchmark_code_sha256"] != digest(__file__):
            raise ValueError("Frozen benchmark changed; create a new experiment version")
        for relative, expected in saved["input_sha256"].items():
            if digest(root / relative) != expected:
                raise ValueError("Frozen benchmark input changed")
        if digest(output / "requests.jsonl") != saved["requests_sha256"]:
            raise ValueError("Frozen request manifest changed")
        for relative, expected in saved["prepared_sha256"].items():
            if digest(output / relative) != expected:
                raise ValueError("Frozen prepared artifact changed")
        return saved
    u = pd.read_csv(root / "data/prepared/causal-v3/windows.csv.gz")
    s = pd.read_csv(root / "data/prepared/swell-v1/minutes.csv.gz")
    ur = json.loads((root / "results/causal-v3/report.json").read_text())
    sr = json.loads((root / "results/swell-v1/report.json").read_text())
    # Choose the temporal middle observation by index, never by label/quality/value.
    u_sample = u.loc[[g.sort_values("window_end").index[(len(g)-1)//2]
                     for _, g in u.groupby(["participant", "unit_id"], sort=True)]]
    s_sample = s[s.participant.isin(sr["protocol"]["split"]["test"])].sort_values(KEYS)
    folds = ur["targets"]["mental_demand"]["folds"]
    assert all([f["validation"] for f in z["folds"]] == [f["validation"] for f in folds]
               for z in ur["targets"].values())
    reference_sets, requests, records = {}, [], []
    input_paths = ["data/prepared/causal-v3/windows.csv.gz", "data/prepared/swell-v1/minutes.csv.gz",
                   "results/causal-v3/report.json", "results/swell-v1/report.json"]
    for dataset, sample, all_rows in (("universe", u_sample, u), ("swell", s_sample, s)):
        sample.to_csv(output / f"{dataset}-sample.csv.gz", index=False)
        for number, (_, row) in enumerate(sample.iterrows()):
            excluded = (next(f["validation"] for f in folds if row.participant in f["validation"])
                        if dataset == "universe" else sr["protocol"]["split"]["test"])
            reference_id = dataset + ":" + ",".join(excluded)
            if reference_id not in reference_sets:
                reference_sets[reference_id] = choose_examples(all_rows, excluded)
            for mode in MODES:
                request_id = f"{dataset}:{number:04}:{mode}"
                body = payload(row, dataset, reference_sets[reference_id] if mode == "eight_shot" else [])
                requests.append({"request_id": request_id, "body": body})
                records.append({"request_id": request_id, "dataset": dataset, "mode": mode,
                                "reference_id": reference_id, **{k: row[k] for k in KEYS}})
        for target in TARGETS:
            if dataset == "universe":
                relative = f"results/causal-v3/{target}-predictions.csv.gz"
                input_paths.append(relative)
                prior = pd.read_csv(root / relative)
                joined = sample[KEYS + [target]].dropna(subset=[target]).merge(
                    prior[KEYS + ["selected", "learned", "constant"]], on=KEYS, validate="one_to_one")
                assert len(joined) == sample[target].notna().sum()
                joined.to_csv(output / f"{dataset}-{target}-local.csv.gz", index=False)
            else:
                joined = sample[KEYS + [target]].copy()
                for mode in ("selected", "learned", "constant", "native_learned", "prior_rest_learned"):
                    relative = f"results/swell-v1/{target}__{mode}.csv.gz"
                    input_paths.append(relative)
                    prior = pd.read_csv(root / relative)
                    joined = joined.merge(prior[KEYS + ["prediction"]].rename(columns={"prediction": mode}),
                                          on=KEYS, validate="one_to_one")
                assert len(joined) == len(sample)
                joined.to_csv(output / f"{dataset}-{target}-local.csv.gz", index=False)
    (output / "requests.jsonl").write_text("".join(json.dumps(x, allow_nan=False) + "\n" for x in requests))
    pd.DataFrame(records).to_csv(output / "request-index.csv", index=False)
    save_json(output / "reference-audit.json", {
        k: [{name: numeric(row[name]) if name == "window_end" else row[name] for name in KEYS} for row in values]
        for k, values in reference_sets.items()})
    protocol = {"experiment": "006-jev-v1", "created_utc": datetime.now(timezone.utc).isoformat(),
        "model": MODEL, "endpoint": ENDPOINT, "modes": list(MODES), "seed": SEED,
        "requests": len(requests), "universe_rows": len(u_sample), "swell_rows": len(s_sample),
        "benchmark_code_sha256": digest(__file__), "requests_sha256": digest(output / "requests.jsonl"),
        "input_sha256": {p: digest(root / p) for p in input_paths},
        "prepared_sha256": {p.name: digest(p) for p in output.iterdir() if p.name != "requests.jsonl"},
        "sampling": "UNIVERSE: one middle available window per questionnaire interval, 19 development people. SWELL: all 431 held-out minutes, five people.",
        "examples": "Eight label-independently selected windows from eight other training people. Entire outer fold excluded for UNIVERSE; entire test excluded for SWELL.",
        "selection": "Both prompts fixed before scoring. No test-driven prompt tuning, response replacement, fine-tuning or weight training.",
        "questions": {d: questions(d) for d in ("universe", "swell")},
        "output": "Choice categories, no interpolation: UNIVERSE effort 1..5, TLX 0..100 step10; SWELL TLX 0..10 step1, RSME 0..15 step1.",
        "scoring": "Error per observation, average within block then person then people. UNIVERSE mental effort exact rounded level; other outputs within10. SWELL within1 native point.",
        "failures": "Report coverage and paired complete-case metrics; failed API answers never replaced by local estimates. No confidence filtering of primary metrics.",
        "transport": "Pinned HTTPS host, no redirects; four workers; at most three attempts for 429/5xx/network errors, 30s timeout. No resampling of valid answers.",
        "limitations": ["Previously inspected research benchmarks, not a fresh validation cohort.",
                       "Repeated task/block labels do not validate instantaneous states.",
                       "UNIVERSE performance scale direction unverified; rate numeric convention only.",
                       "SWELL sensor placement and unverified RMSSD/SCL native units limit wrist transfer.",
                       "Provider pretraining exposure to these public datasets cannot be excluded.",
                       "Jev internal confidence is not calibrated accuracy for physiological estimates."]}
    save_json(protocol_path, protocol)
    save_json(root / "experiments/006-jev-protocol.json", protocol)
    return protocol


def read_key(root):
    names = ("JEV_API_key", "JEV_API_KEY", "TYPESAFE_API_KEY")
    for name in names:
        if os.getenv(name):
            return os.environ[name]
    values = {}
    path = root.parent / "neurasign_server_dashboard/.env"
    if path.exists():
        for line in path.read_text().splitlines():
            key, sep, value = line.removeprefix("export ").partition("=")
            if sep and key.strip() in names:
                parts = shlex.split(value, comments=True)
                if len(parts) == 1:
                    values[key.strip()] = parts[0]
    for name in names:
        if values.get(name):
            return values[name]
    raise RuntimeError("Jev key unavailable; no requests made")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def call(item, key):
    started = time.monotonic()
    attempts = []
    for attempt in range(3):
        request = urllib.request.Request(ENDPOINT, data=json.dumps(item["body"], allow_nan=False).encode(),
            headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
        try:
            with urllib.request.build_opener(NoRedirect).open(request, timeout=30) as response:
                body = json.load(response)
            return {"request_id": item["request_id"], "status": "received", "response": body,
                    "attempts": attempts + [{"http_status": 200}], "elapsed_seconds": time.monotonic()-started}
        except urllib.error.HTTPError as error:
            attempts.append({"http_status": error.code})
            if error.code != 429 and error.code < 500:
                break
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as error:
            attempts.append({"error_type": type(error).__name__})
        if attempt < 2:
            time.sleep(2 ** attempt)
    return {"request_id": item["request_id"], "status": "failed", "attempts": attempts,
            "elapsed_seconds": time.monotonic()-started}


def run(root):
    protocol = prepare(root)
    output = root / "results/jev-v1"
    key = read_key(root)
    completed = {}
    path = output / "responses.jsonl"
    if path.exists():
        completed = {x["request_id"]: x for x in map(json.loads, path.read_text().splitlines())}
    requests = [json.loads(line) for line in (output / "requests.jsonl").read_text().splitlines()]
    pending = [x for x in requests if x["request_id"] not in completed]
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=4) as pool, path.open("a") as log:
        for offset in range(0, len(pending), 4):
            batch = list(pool.map(lambda item: call(item, key), pending[offset:offset+4]))
            for result in batch:
                log.write(json.dumps(result, allow_nan=False) + "\n")
                completed[result["request_id"]] = result
            log.flush()
            if any(a.get("http_status") in (401, 402, 403, 422) for x in batch for a in x["attempts"]):
                raise RuntimeError("Provider rejected request; sanitized attempt status saved. No fallback.")
            if len(completed) % 100 < 4 or len(completed) == len(requests):
                print(json.dumps({"completed": len(completed), "total": len(requests),
                                  "elapsed_seconds": round(time.monotonic()-started, 1)}), flush=True)
    save_json(output / "run.json", {"requests": len(completed), "elapsed_seconds_this_run": time.monotonic()-started,
              "completed_utc": datetime.now(timezone.utc).isoformat(), "protocol_sha256": digest(output / "protocol.json"),
              "responses_sha256": digest(path), "all_requests_attempted": len(completed) == protocol["requests"]})


def parse_answer(response, dataset, target):
    if response.get("model") != MODEL:
        raise ValueError("Unexpected model version")
    answer = response["answers"][target]
    values = {f"rating_{x}": x for x in grid(dataset, target)}
    if answer.get("type") != "choice" or answer.get("choice") not in values:
        raise ValueError("Invalid choice")
    confidence = float(answer["confidence"])
    probabilities = answer["probabilities"]
    if not math.isfinite(confidence) or not 0 <= confidence <= 1 or set(probabilities) != set(values):
        raise ValueError("Invalid confidence or probability categories")
    probs = [float(p) for p in probabilities.values()]
    if not all(math.isfinite(p) and 0 <= p <= 1 for p in probs) or abs(sum(probs)-1) > .02:
        raise ValueError("Invalid probability distribution")
    return values[answer["choice"]], confidence


def metrics(rows, target, predictions, dataset):
    error = np.abs(rows[target].to_numpy() - np.asarray(predictions))
    if not np.isfinite(error).all() or not len(rows):
        raise ValueError("Nonfinite or empty scoring rows")
    w = weights(rows)
    agreement = (np.floor(np.asarray(predictions)+.5) == rows[target].to_numpy()
                 if dataset == "universe" and target == "mental_effort" else error <= (10 if dataset == "universe" else 1))
    return {"mae": float(np.average(error, weights=w)), "agreement_percent": float(np.average(agreement, weights=w)*100),
            "rows": len(rows), "blocks": rows.unit_id.nunique(), "participants": rows.participant.nunique()}
