"""Development-only signal audit and fixed-model ablations; no runtime changes.

Relaxed pulse gates are diagnostic counterfactuals, not validated measurements.
All variants use identical participant folds and repeated questionnaire labels.
"""
import hashlib
import json
from pathlib import Path
import time

import numpy as np
import pandas as pd
from scipy.signal import find_peaks, sosfilt, sosfilt_zi
from threadpoolctl import threadpool_limits

from .causal import FEATURES, WINDOW, pulse_filter, window_samples, json_ready
from .causal_data import build_causal_dataset, read_segment, source_manifest
from .causal_training import make_estimator, thin_training, window_metrics
from .schema import TARGETS, SEED
from .training import save_json, weights
from .tuning import paired_change, person_folds

PULSE = [name for name in FEATURES if name.startswith("pulse_") and
         name != "pulse_valid_interval_fraction"]
GROUPS = {
    "eda": [name for name in FEATURES if name.startswith("eda_")],
    "temperature": [name for name in FEATURES if name.startswith("temperature_")],
    "motion": [name for name in FEATURES if name.startswith(("motion_", "acc_"))],
    "device_hr": [name for name in FEATURES if name.startswith("heart_rate_")] +
                 ["pulse_rate_device_difference_bpm"],
    "pulse_wave": [name for name in FEATURES if name.startswith(("bvp_", "pulse_"))],
    "pulse_intervals": PULSE,
}
VARIANTS = ["v3_gates", "all_training_windows", "relax_motion", "relax_motion_periodicity"] + [
    "without_" + name for name in GROUPS]
MODELS = [
    {"name": "constant_mean", "kind": "constant", "strategy": "mean"},
    {"name": "constant_median", "kind": "constant", "strategy": "median"},
    {"name": "ridge_100", "kind": "ridge", "alpha": 100.},
    {"name": "boost_squared_7", "kind": "boost", "loss": "squared_error", "leaves": 7},
]


def union_seconds(intervals):
    """Duration without counting overlapping windows or duplicate intervals twice."""
    total, left, right = 0., None, None
    for start, end in sorted(intervals):
        if not np.isfinite([start, end]).all() or end < start:
            raise ValueError("Invalid time interval")
        if left is None:
            left, right = start, end
        elif start <= right:
            right = max(right, end)
        else:
            total += right - left
            left, right = start, end
    return total + (0. if left is None else right - left)


def covered_hours(rows):
    return sum(union_seconds(zip(group.source_end - WINDOW, group.source_end))
               for _, group in rows.groupby(["participant", "session"])) / 3600.


def pulse_diagnostics(trace, end, device_hr):
    """Reproduce v3 beat extraction, exposing results before its two artifact gates."""
    bt, bvp, _ = window_samples(trace, end - WINDOW, end)
    sos = pulse_filter(trace.rate)
    filtered, _ = sosfilt(sos, bvp, zi=sosfilt_zi(sos) * bvp[0])
    settle = int(2 * trace.rate)
    filtered, bt = filtered[settle:], bt[settle:]
    peaks, _ = find_peaks(filtered, distance=max(1, int(.3 * trace.rate)),
                         prominence=max(filtered.std() * .3, 1e-9))
    intervals = np.diff(bt[peaks]) * 1000.
    valid = (intervals >= 300) & (intervals <= 2000)
    fraction = float(valid.mean()) if len(valid) else 0.
    basic = valid.sum() >= 20 and fraction >= .8
    result = {key: np.nan for key in PULSE}
    if basic:
        rr = intervals[valid]
        result.update(pulse_rate_bpm=60000. / np.median(rr), pulse_interval_mean_ms=rr.mean(),
                      pulse_interval_sdnn_ms=rr.std(ddof=1),
                      pulse_interval_iqr_ms=np.quantile(rr, .75) - np.quantile(rr, .25))
        differences = np.diff(intervals)[valid[1:] & valid[:-1]]
        if len(differences) >= 10:
            result.update(pulse_interval_rmssd_ms=np.sqrt(np.mean(differences ** 2)),
                          pulse_interval_pnn50=np.mean(abs(differences) > 50))
        if np.isfinite(device_hr):
            result["pulse_rate_device_difference_bpm"] = abs(result["pulse_rate_bpm"] - device_hr)
    return {**result, "basic_pulse_ok": bool(basic), "detected_peaks": len(peaks),
            "valid_intervals": int(valid.sum()), "valid_fraction": fraction}


def extract_diagnostics(root, data, audit):
    destination = root / "results/information-v4"
    destination.mkdir(parents=True, exist_ok=True)
    path, metadata = destination / "diagnostics.csv.gz", destination / "extraction.json"
    code_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    identity = {"code_sha256": code_hash, "input_sha256": audit["dataset_sha256"]}
    if path.exists() and metadata.exists():
        saved = json.loads(metadata.read_text())
        if all(saved.get(k) == v for k, v in identity.items()) and saved["output_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest():
            return pd.read_csv(path), saved
        raise ValueError("Audit cache changed; version or explicitly remove only the v4 audit outputs")
    provenance = json.loads((root / "data/prepared/causal-v3/provenance.json").read_text())
    source, manifest = source_manifest(root)
    rows, segment_durations, equality_checks = [], [], 0
    for index, info in enumerate(provenance):
        if info["participant"] not in audit["development"]:
            raise ValueError("Original test participant entered audit")
        selected = data[data.unit_id == info["unit_id"]]
        if selected.empty:
            continue
        traces, current = read_segment(source / info["segment"], source, manifest)
        if current != {k: info[k] for k in ("clock", "origin", "sources")}:
            raise ValueError("Raw source provenance changed")
        start = info["origin"] + traces["bvp"].times[0]
        stop = info["origin"] + traces["bvp"].times[-1] + 1 / traces["bvp"].rate
        segment_durations.append({"participant": info["participant"], "session": info["session"],
                                  "unit_id": info["unit_id"], "start": start, "end": stop})
        for row_id, window in selected.iterrows():
            d = pulse_diagnostics(traces["bvp"], window.window_end, window.heart_rate_median)
            d.update(row_id=row_id, motion_gate=bool(window.motion_std > .2 or window.acc_clipped_fraction > .05),
                     clipping_gate=bool(window.acc_clipped_fraction > .05),
                     dynamic_motion_gate=bool(window.motion_std > .2),
                     periodicity_gate=bool(window.bvp_periodicity < .2))
            for name, limits in (("temperature", (30., 40.)), ("eda", (.05, 60.))):
                _, values, _ = window_samples(traces[name], window.window_end - WINDOW, window.window_end)
                d[name + "_outside_reference_fraction"] = float(((values < limits[0]) | (values > limits[1])).mean())
                d[name + "_flat"] = bool(np.ptp(values) <= .001)
            available = np.isfinite(window.pulse_rate_bpm)
            expected = d["basic_pulse_ok"] and not d["motion_gate"] and not d["periodicity_gate"]
            if available != expected:
                raise ValueError("Auditor does not reproduce v3 gate decisions")
            if available:
                np.testing.assert_allclose([d[k] for k in PULSE], window[PULSE].to_numpy(float), equal_nan=True,
                                           rtol=1e-8, atol=1e-8)
                equality_checks += 1
            rows.append(d)
        if (index + 1) % 25 == 0:
            print(f"Raw audit: {index + 1}/{len(provenance)} intervals, {len(rows)} windows", flush=True)
    frame = pd.DataFrame(rows).set_index("row_id").sort_index()
    if not frame.index.equals(data.index):
        raise ValueError("Diagnostic rows do not exactly cover the development data")
    frame.to_csv(path, index=False, compression={"method": "gzip", "mtime": 0})
    summary = {**identity, "output_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
               "verified_unmasked_windows": equality_checks, "segment_durations": segment_durations}
    save_json(metadata, summary)
    return frame, summary


def variant_data(data, diagnostics, variant):
    result, columns = data.copy(), list(FEATURES)
    if variant.startswith("without_"):
        columns = [key for key in columns if key not in GROUPS[variant.removeprefix("without_")]]
    if variant.startswith("relax_"):
        usable = diagnostics.basic_pulse_ok.to_numpy(bool, copy=True)
        if variant == "relax_motion":
            usable &= ~diagnostics.periodicity_gate.to_numpy(bool)
        result.loc[usable, PULSE] = diagnostics.loc[usable, PULSE].to_numpy()
    return result, columns


def quality_summary(data, diagnostic, extraction):
    ready = data.pulse_rate_bpm.notna()
    groups = {"v3_retained": ready, "recover_motion_only": ~ready & diagnostic.basic_pulse_ok & ~diagnostic.periodicity_gate,
              "recover_after_both_gates": ~ready & diagnostic.basic_pulse_ok,
              "still_fails_beat_checks": ~diagnostic.basic_pulse_ok}
    summary = {}
    for name, mask in groups.items():
        difference = diagnostic.loc[mask, "pulse_rate_device_difference_bpm"].dropna()
        summary[name] = {"windows": int(mask.sum()), "fraction": float(mask.mean()),
                         "device_hr_disagreement_median_bpm": float(difference.median()),
                         "device_hr_disagreement_p90_bpm": float(difference.quantile(.9)),
                         "within_10_bpm_fraction": float((difference <= 10).mean()) if len(difference) else None}
    gates = {name: int(diagnostic[name].sum()) for name in
             ("motion_gate", "clipping_gate", "dynamic_motion_gate", "periodicity_gate", "temperature_flat", "eda_flat")}
    gates["temperature_majority_outside_30_40"] = int((diagnostic.temperature_outside_reference_fraction > .5).sum())
    gates["eda_majority_outside_005_60"] = int((diagnostic.eda_outside_reference_fraction > .5).sum())
    segments = pd.DataFrame(extraction["segment_durations"])
    hours = sum(union_seconds(zip(g.start, g.end)) for _, g in segments.groupby(["participant", "session"])) / 3600
    fitting = thin_training(data)
    counts = {"windows": len(data), "intervals": data.unit_id.nunique(), "participants": data.participant.nunique(),
              "development_labeled_signal_hours": hours, "window_union_hours": covered_hours(data),
              "naive_sum_overlapping_window_hours": len(data) / 60,
              "v3_fitting_windows_before_target_mask": len(fitting),
              "v3_fitting_window_union_hours_before_target_mask": covered_hours(fitting),
              "by_session": {name: {"window_union_hours": covered_hours(g), "windows": len(g),
                                     "pulse_available_fraction": float(g.pulse_rate_bpm.notna().mean())}
                             for name, g in data.groupby("session")}}
    labels = {}
    for target in TARGETS:
        valid = data[data[target].notna()]
        varying = valid.groupby("unit_id")[target].nunique()
        if (varying > 1).any():
            raise ValueError("Reference label changed inside a task")
        units = valid.drop_duplicates("unit_id")
        labels[target] = {"windows": len(valid), "intervals": len(units), "hours": covered_hours(valid),
                          "per_person_distinct_ratings": units.groupby("participant")[target].nunique().to_dict()}
    return json_ready({"counts": counts, "pulse_groups": summary, "gate_counts": gates, "labels": labels,
                       "cautions": ["Flags are heuristic checks, not proof of unusable data.",
                         "Device HR and detected pulse share an optical source; agreement is not independent ECG validation.",
                         "Recovered groups overlap; they must not be summed.",
                         "Hours are the union of source-clock intervals within participant/session, not independent labels."]})


def evaluate(root, data, diagnostics, protocol):
    output = root / "results/information-v4"
    report = {"targets": {}, "purpose": "fixed ablation diagnostics, no model selection or production promotion"}
    with threadpool_limits(limits=2):
        for target in TARGETS:
            valid = data[target].notna()
            result = {}
            for variant in VARIANTS:
                rows, features = variant_data(data, diagnostics, variant)
                rows = rows.loc[valid].reset_index(drop=True)
                configs = MODELS if variant == "v3_gates" else MODELS[2:]
                for config in configs:
                    predictions = np.full(len(rows), np.nan)
                    for train_ids, validation_ids in protocol["folds"]:
                        training = rows[rows.participant.isin(train_ids)]
                        thinned = thin_training(training)
                        fit = training if variant == "all_training_windows" else thinned
                        mask = rows.participant.isin(validation_ids).to_numpy()
                        # Keep total weight unchanged when including more windows, so
                        # sample count does not silently alter L2 regularization strength.
                        weight = weights(fit)
                        weight *= len(thinned) / weight.sum()
                        estimator = make_estimator(config)
                        parameter = f"{estimator.steps[-1][0]}__sample_weight" if hasattr(estimator, "steps") else "sample_weight"
                        low, high = TARGETS[target]["range"]
                        estimator.fit(fit[features], (fit[target] - low) / (high - low), **{parameter: weight})
                        predictions[mask] = np.clip(estimator.predict(rows.loc[mask, features]), 0, 1) * (high - low) + low
                    key = variant + "/" + config["name"]
                    score = window_metrics(rows, target, predictions)
                    if variant != "v3_gates":
                        score["change_from_same_model_v3_gates"] = paired_change(result["v3_gates/" + config["name"]], score)
                    result[key] = score
                    saved = rows[["participant", "session", "unit_id", "source_end", target]].copy()
                    saved["prediction"] = predictions
                    saved.to_csv(output / f"{target}__{variant}__{config['name']}.csv.gz", index=False,
                                 compression={"method": "gzip", "mtime": 0})
                print(f"Ablation: {target}, {variant}", flush=True)
            report["targets"][target] = result
            save_json(output / "ablation.json", report)
    return report


def run_audit(root):
    started = time.monotonic()
    data, audit = build_causal_dataset(root)
    protocol = {"version": "information-v4", "seed": SEED, "dataset_sha256": audit["dataset_sha256"],
                "source_extractor_sha256": audit["extractor_sha256"], "development": audit["development"],
                "excluded_original_test": audit["original_test_excluded"], "folds": person_folds(audit["development"], 5),
                "variants": VARIANTS, "removed_feature_groups": GROUPS, "models": MODELS,
                "reference": "Each window inherits its task questionnaire rating, unchanged from v3.",
                "metric": "Mean window absolute error within interval, then person, then all people.",
                "training": "20 evenly spaced windows per interval, except all_training_windows; total sample weight fixed to the thinned count.",
                "relaxation": "Diagnostic only: ignore motion, then motion plus periodicity; keep >=20 valid intervals and >=80% interval validity.",
                "scope": "Exploratory development audit. Fixed settings; no best-variant model selected or deployed. No independent test claims."}
    frozen = root / "experiments/004-information-protocol.json"
    if frozen.exists() and json.loads(frozen.read_text()) != json.loads(json.dumps(protocol)):
        raise ValueError("Frozen information audit protocol changed")
    save_json(frozen, protocol)
    diagnostics, extraction = extract_diagnostics(root, data, audit)
    quality = quality_summary(data, diagnostics, extraction)
    save_json(root / "results/information-v4/quality.json", quality)
    print(json.dumps(quality["counts"], indent=2), flush=True)
    ablation = evaluate(root, data, diagnostics, protocol)
    result = {"protocol": protocol, "quality": quality, "ablation": ablation,
              "elapsed_seconds": time.monotonic() - started, "original_test_evaluated": False,
              "code_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    save_json(root / "results/information-v4/report.json", result)
    return result
