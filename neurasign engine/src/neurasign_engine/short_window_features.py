"""Experiment 011: matched raw features confined to each 1- or 60-second window.

No filter state, padding, earlier window, beat detection, or device heart rate is
used. E4's supplied heart rate already averages ten seconds. ``extract_short_window``
returns features, per-channel quality, status/reasons, and evidence boundaries.
Invalid channels retain NaN features; they do not remove the paired evaluation row.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from .causal import CHANNELS, Trace, validate_trace
from .causal_data import read_segment, source_manifest
from .data import parse_labels, verified_bytes

STATS = ["mean", "std", "range", "slope_per_second", "last_third_minus_first_third"]
SHORT_FEATURES = [f"{channel}_{stat}" for channel in ("bvp", "eda", "temperature", "motion")
                  for stat in STATS] + ["motion_enmo_mean_g", "motion_jerk_rms_g_s", "acc_clipped_fraction"]
RAW_CHANNELS = ("bvp", "eda", "temperature", "acc_x", "acc_y", "acc_z")
METADATA = ["row_id", "participant", "session", "unit_id", "window_end", "source_end",
            "mental_demand", "mental_effort"]


def _statistics(times, values, start, end):
    result = {name: np.nan for name in STATS}
    if not len(values):
        return result
    result["mean"] = float(values.mean())
    if len(values) < 2:
        return result
    centered = times - times.mean()
    denominator = float(np.dot(centered, centered))
    result.update(std=float(values.std()), range=float(np.quantile(values, .9)-np.quantile(values, .1)))
    if denominator > 0:
        result["slope_per_second"] = float(np.dot(centered, values-values.mean())/denominator)
    third = (end-start)/3
    first, last = values[times < start+third], values[times >= end-third]
    if len(first) and len(last):
        result["last_third_minus_first_third"] = float(last.mean()-first.mean())
    return result


def _samples(trace, start, end):
    validate_trace(trace)
    left, right = np.searchsorted(trace.times, [start, end], side="left")
    times, values = trace.times[left:right], trace.values[left:right]
    finite = np.isfinite(values)
    times, values = times[finite], values[finite]
    cadence = float(np.median(abs(np.diff(times)*trace.rate-1))) if len(times) > 1 else None
    quality = {"samples": len(values), "coverage": min(1., len(values)/((end-start)*trace.rate)),
               "max_gap_seconds": float(np.diff(np.r_[start, times, end]).max()),
               "cadence_relative_error": cadence}
    quality["accepted"] = bool(quality["coverage"] >= .95 and
        quality["max_gap_seconds"] <= max(.5, 2.5/trace.rate) and (cadence is None or cadence <= .1))
    return times, values, quality


def extract_short_window(traces: dict[str, Trace], end: float, width: float):
    """Extract only timestamps in [end-width, end), including at most 23 features.

    Means require one finite sample; variability/trends require at least two.
    The change feature also requires samples in both the first and last thirds.
    Coverage, gaps and cadence use the established raw-channel quality thresholds.
    A single sample at a declared 1-Hz rate supports its one-second mean, but not
    variability or a cadence check. HR is ignored, including its quality/status.
    """
    if isinstance(width, bool) or not isinstance(width, (int, float, np.number)) or not math.isfinite(width) or width <= 0:
        raise ValueError("Evidence width must be finite and positive")
    if isinstance(end, bool) or not isinstance(end, (int, float, np.number)) or not math.isfinite(end):
        raise ValueError("Window end must be finite")
    start = float(end-width)
    if not math.isfinite(start) or start >= end:
        raise ValueError("Evidence boundaries must be finite and distinct")
    features = {name: np.nan for name in SHORT_FEATURES}
    quality, accepted, reasons = {}, {}, []
    for channel in RAW_CHANNELS:
        trace = traces.get(channel)
        if trace is None:
            quality[channel] = {"samples": 0, "coverage": 0., "max_gap_seconds": float(width),
                                "cadence_relative_error": None, "accepted": False}
            reasons.append("missing_"+channel)
            continue
        if trace.unit != CHANNELS[channel][1]:
            raise ValueError("Short-window extraction requires canonical raw-channel units")
        times, values, current = _samples(trace, start, float(end))
        quality[channel] = current
        if not current["accepted"]:
            reasons.append("incomplete_"+channel)
            continue
        if channel == "eda" and np.any((values < 0) | (values > 100)):
            current["accepted"] = False
            reasons.append("invalid_eda_range")
            continue
        if channel == "temperature" and np.any((values < 10) | (values > 45)):
            current["accepted"] = False
            reasons.append("temperature_outside_sensor_profile")
            continue
        accepted[channel] = (times, values)
        if channel in ("bvp", "eda", "temperature"):
            features.update({channel+"_"+name: value for name, value in _statistics(times, values, start, end).items()})
    if all(channel in accepted for channel in ("acc_x", "acc_y", "acc_z")):
        times = accepted["acc_x"][0]
        if not all(np.array_equal(times, accepted[channel][0]) for channel in ("acc_y", "acc_z")):
            reasons.append("misaligned_acceleration_axes")
        else:
            axes = np.column_stack([accepted[channel][1] for channel in ("acc_x", "acc_y", "acc_z")])
            magnitude = np.linalg.norm(axes, axis=1)
            features.update({"motion_"+name: value for name, value in _statistics(times, magnitude, start, end).items()})
            features["motion_enmo_mean_g"] = float(np.maximum(magnitude-1, 0).mean())
            features["acc_clipped_fraction"] = float((np.abs(axes) >= 1.98).any(axis=1).mean())
            if len(times) >= 2:
                features["motion_jerk_rms_g_s"] = float(np.sqrt(np.mean((np.diff(magnitude)/np.diff(times))**2)))
    return {"features": features, "channel_quality": quality, "reasons": reasons,
            "status": "features_ready" if not reasons else "insufficient_data",
            "window_start": start, "window_end": float(end), "window_seconds": float(width)}


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _paired_metadata(root):
    """Recover the same experiment-010 endpoints with both original target values."""
    prepared = root/"data/prepared/personalization-v1"
    audit_path = prepared/"audit.json"
    audit = json.loads(audit_path.read_text())
    source = root/"data/prepared/transfer-v1/universe.csv.gz"
    if _sha(source) != audit["input_sha256"]:
        raise ValueError("Experiment 010 source table changed")
    original = pd.read_csv(source)
    original["row_id"] = original.index
    identifiers, hashes, target_rows = set(), {str(source.relative_to(root)): _sha(source),
        str(audit_path.relative_to(root)): _sha(audit_path)}, {}
    for target in ("mental_demand", "mental_effort"):
        target_rows[target] = {}
        for session in ("lab1", "lab2"):
            path = prepared/(target+"-"+session+".csv.gz")
            if _sha(path) != audit["files"][path.name]:
                raise ValueError("Experiment 010 prepared rows changed")
            frame = pd.read_csv(path)
            if frame.row_id.duplicated().any() or not set(frame.session) <= {session.capitalize()}:
                raise ValueError("Invalid experiment 010 row/session binding")
            reference = original.loc[frame.row_id, [*METADATA[:6], target]].reset_index(drop=True)
            pd.testing.assert_frame_equal(frame[[*METADATA[:6], target]].reset_index(drop=True), reference)
            identifiers.update(frame.row_id.tolist())
            target_rows[target][session] = frame.row_id.tolist()
            hashes[str(path.relative_to(root))] = _sha(path)
    return original.loc[sorted(identifiers), METADATA].reset_index(drop=True), hashes, target_rows


def prepare(root):
    """Write a new paired dataset; never alter previous datasets or experiments.

    Both widths retain every experiment-010 union row, including rows with missing
    new features. The target/session row-ID lists preserve each target's original
    eligibility; the union itself is not a new target eligibility decision.
    """
    root = Path(root).resolve()
    frame, inputs, target_rows = _paired_metadata(root)
    split_path = root/"experiments/split-v1.json"
    split = json.loads(split_path.read_text())
    if not set(frame.participant) <= set(split["development"]) or not set(frame.session) <= {"Lab1", "Lab2"}:
        raise ValueError("Only original development Lab1/Lab2 rows may enter experiment 011")
    provenance_path = root/"data/prepared/causal-v3/provenance.json"
    provenance = json.loads(provenance_path.read_text())
    mapping = {row["unit_id"]: row for row in provenance}
    if len(mapping) != len(provenance) or not set(frame.unit_id) <= set(mapping):
        raise ValueError("Causal source mapping is ambiguous or incomplete")
    source, manifest = source_manifest(root)
    manifest_path = root/"data/universe/manifest.json"
    for path in (split_path, provenance_path, manifest_path, Path(__file__)):
        inputs[str(path.relative_to(root))] = _sha(path)
    labels, source_files = {}, {}
    output = {width: [] for width in (1, 60)}
    counts = {width: Counter() for width in output}
    channel_counts = {width: Counter() for width in output}
    for unit_id, group in frame.groupby("unit_id", sort=False):
        entry = mapping[unit_id]
        if set(group.participant) != {entry["participant"]} or set(group.session) != {entry["session"]}:
            raise ValueError("Prepared row disagrees with raw-source identity")
        segment = source/entry["segment"]
        if segment.name not in labels.get(entry["label_source"], {}):
            path = source/entry["label_source"]
            labels[entry["label_source"]] = parse_labels(path, verified_bytes(path, source, manifest), Counter())
            source_files[entry["label_source"]] = manifest[entry["label_source"]]["sha256"]
        targets = labels[entry["label_source"]][segment.name]["targets"]
        traces, raw = read_segment(segment, source, manifest)
        if raw["sources"] != entry["sources"] or raw["origin"] != entry["origin"]:
            raise ValueError("Raw source no longer matches frozen causal provenance")
        source_files.update({item["member"]: item["sha256"] for item in raw["sources"]})
        for row in group.to_dict("records"):
            if not np.isclose(row["source_end"], raw["origin"]+row["window_end"], rtol=0, atol=1e-6):
                raise ValueError("Raw source endpoint does not match prepared row")
            for target in ("mental_demand", "mental_effort"):
                expected = targets[target]
                if not ((pd.isna(row[target]) and expected is None) or row[target] == expected):
                    raise ValueError("Prepared label does not match original questionnaire")
            for width in output:
                result = extract_short_window(traces, row["window_end"], width)
                output[width].append({**result["features"], **row})
                counts[width][result["status"]] += 1
                counts[width].update(result["reasons"])
                channel_counts[width].update(channel for channel, quality in result["channel_quality"].items() if quality["accepted"])
        print(json.dumps({"short_window_prepared_unit": unit_id, "rows": len(group)}), flush=True)
    destination = root/"data/prepared/short-window-v1"
    destination.mkdir(parents=True, exist_ok=True)
    audit = {"experiment": "011-short-window", "features": SHORT_FEATURES, "widths_seconds": [1, 60],
             "rows": len(frame), "units": int(frame.unit_id.nunique()), "input_sha256": inputs,
             "source_files_sha256": source_files, "source_manifest_sha256": _sha(manifest_path),
             "target_session_row_ids": target_rows, "original_test_excluded": split["test"],
             "row_policy": "Experiment 010 target/session union; preserve each original target/session row-ID list",
             "missingness_policy": "Retain paired rows; quality-failed channels and unsupported statistics remain NaN",
             "device_heart_rate": "Excluded from both profiles because vendor HR averages ten seconds",
             "window_policy": "Only [end-width,end); no padding, filters, beat or spectral features, or past references",
             "files": {}, "quality": {}}
    for width, rows in output.items():
        data = pd.DataFrame(rows)[[*SHORT_FEATURES, *METADATA]].sort_values("row_id").reset_index(drop=True)
        pd.testing.assert_frame_equal(data[METADATA], frame)
        path = destination/f"window-{width}.csv.gz"
        data.to_csv(path, index=False, compression={"method": "gzip", "mtime": 0})
        audit["files"][path.name] = _sha(path)
        audit["quality"][str(width)] = {"counts": dict(counts[width]),
            "accepted_rows_by_channel": dict(channel_counts[width]),
            "finite_rows_by_feature": {feature: int(np.isfinite(data[feature]).sum()) for feature in SHORT_FEATURES}}
    (destination/"audit.json").write_text(json.dumps(audit, indent=2, allow_nan=False)+"\n")
    return audit
