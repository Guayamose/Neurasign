#!/usr/bin/env python3
"""Convert real UNIVERSE Empatica E4 sessions or explicit feature CSVs to replay.

Standard-library only. Raw Empatica CSV timestamps and sample rates are honored;
60-second trailing windows become features, then each worker's own calibration
segment supplies their baseline. No workload labels are treated as ground truth
for the app's inferred readiness, fatigue, or interruption cost.
"""
from __future__ import annotations

import argparse
from bisect import bisect_left
import csv
from dataclasses import dataclass
import json
import math
from pathlib import Path
from statistics import fmean, pstdev

ROOT = Path(__file__).resolve().parents[1]
FEATURES = ("heart_rate", "hrv", "eda", "temperature", "movement")
# Engineering noise floors prevent nearly constant calibration from exploding
# z-scores. These are not universal physiological or diagnostic thresholds.
STD_FLOORS = {"heart_rate": 3.0, "hrv": 8.0, "eda": 0.10, "temperature": 0.3, "movement": 0.02}
SOURCE_URL = "https://zenodo.org/records/10371068"


@dataclass
class RegularSignal:
    start: float
    rate: float
    samples: list[list[float]]

    @property
    def end(self) -> float:
        return self.start + len(self.samples) / self.rate

    def window(self, start: float, end: float) -> list[list[float]]:
        left = max(0, math.ceil((start - self.start) * self.rate - 1e-6))
        right = max(0, min(len(self.samples), math.ceil((end - self.start) * self.rate - 1e-6)))
        return self.samples[left:right]


def read_regular(path: Path, dimensions: int = 1) -> RegularSignal:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = csv.reader(handle)
        start = float(next(rows)[0])
        rate = float(next(rows)[0])
        if not math.isfinite(start) or not math.isfinite(rate) or rate <= 0:
            raise ValueError(f"Invalid Empatica timestamp/sample rate: {path}")
        samples = []
        for row in rows:
            if not row:
                continue
            if len(row) != dimensions:
                raise ValueError(f"Expected {dimensions} channel(s): {path}")
            # Keep non-finite rows in their temporal positions; feature extraction
            # rejects them instead of shifting every later sample in time.
            samples.append([float(value) for value in row])
    if not samples:
        raise ValueError(f"Empty Empatica recording: {path}")
    return RegularSignal(start, rate, samples)


def read_ibi(path: Path) -> list[tuple[float, float]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = csv.reader(handle)
        start = float(next(rows)[0])
        samples = [(start + float(row[0]), float(row[1])) for row in rows if row]
    if not math.isfinite(start) or any(not math.isfinite(t) for t, _ in samples):
        raise ValueError(f"Invalid IBI timestamps: {path}")
    if any(samples[index][0] < samples[index - 1][0] for index in range(1, len(samples))):
        raise ValueError(f"Non-monotonic IBI timestamps: {path}")
    return samples


def rmssd(ibi: list[tuple[float, float]]) -> tuple[float | None, int]:
    squared = []
    for (before_time, before), (after_time, after) in zip(ibi, ibi[1:]):
        if not all(math.isfinite(value) and 0.3 <= value <= 2.0 for value in (before, after)):
            continue
        # E4 drops unreliable beats. Do not bridge arbitrary missing intervals.
        if 0 < after_time - before_time <= max(2.5, after * 1.5):
            squared.append(((after - before) * 1000) ** 2)
    return (math.sqrt(fmean(squared)) if len(squared) >= 10 else None, len(squared))


def window_features(signals: dict[str, RegularSignal], ibi: list[tuple[float, float]], ibi_times: list[float], start: float, end: float) -> dict:
    values = {}
    coverage = []
    ranges = {"heart_rate": (30, 220), "eda": (0, 100), "temperature": (10, 45)}
    for feature, (low, high) in ranges.items():
        signal = signals[feature]
        observed = [row[0] for row in signal.window(start, end) if math.isfinite(row[0]) and low < row[0] < high]
        values[feature] = fmean(observed) if observed else None
        coverage.append(min(1.0, len(observed) / ((end - start) * signal.rate)))
    acc = signals["movement"]
    magnitudes = [math.sqrt(sum((axis / 64) ** 2 for axis in row)) for row in acc.window(start, end) if all(math.isfinite(axis) for axis in row)]
    values["movement"] = pstdev(magnitudes) if len(magnitudes) >= 2 else None
    coverage.append(min(1.0, len(magnitudes) / ((end - start) * acc.rate)))
    left, right = bisect_left(ibi_times, start), bisect_left(ibi_times, end)
    values["hrv"], ibi_pairs = rmssd(ibi[left:right])
    quality = min(0.85, fmean(coverage) * (0.85 if ibi_pairs >= 25 else 0.65))
    if values["hrv"] is None:
        quality = min(quality, 0.35)
    return {"features": values, "quality": round(quality, 3)}


def fit_baseline(windows: list[dict]) -> dict:
    baseline = {}
    for feature in FEATURES:
        observed = [item["features"].get(feature) for item in windows]
        observed = [value for value in observed if value is not None and math.isfinite(value)]
        if len(observed) < 3:
            raise ValueError(f"Calibration has fewer than three usable {feature} windows; adjust --start-seconds or --baseline-seconds")
        baseline[feature] = {"mean": round(fmean(observed), 6), "std": round(max(STD_FLOORS[feature], pstdev(observed)), 6)}
    return baseline


def finalize_windows(worker_id: str, windows: list[dict], first_timestamp: float) -> list[dict]:
    result = []
    for window in windows:
        missing = [feature for feature in FEATURES if window["features"].get(feature) is None]
        result.append({
            "worker_id": worker_id,
            "timestamp": round(window["timestamp"] - first_timestamp, 3),
            "features": {
                feature: round(window["features"][feature], 6)
                for feature in FEATURES if feature not in missing
            },
            "quality": min(window["quality"], 0.35) if missing else window["quality"],
            **({"missing_features": missing, "missing_handling": "Omitted measurement; inference uses neutral baseline and reduced confidence"} if missing else {}),
        })
    return result


def locate_session(root: Path, participant: str, session: str) -> Path:
    for path in (root / "UNIVERSE" / participant / session / "Raw" / "Empatica", root / participant / session / "Raw" / "Empatica"):
        if path.is_dir():
            return path
    raise ValueError(f"Cannot find {participant}/{session}/Raw/Empatica under {root}")


def import_empatica(root: Path, mapping: dict[str, str], session: str, start_seconds: int, baseline_seconds: int, duration: int, window_seconds: int, step_seconds: int) -> dict:
    baselines, all_windows, recordings = {}, [], {}
    for worker_id, participant in mapping.items():
        directory = locate_session(root, participant, session)
        signals = {
            "heart_rate": read_regular(directory / "HR.csv"),
            "eda": read_regular(directory / "EDA.csv"),
            "temperature": read_regular(directory / "TEMP.csv"),
            "movement": read_regular(directory / "ACC.csv", dimensions=3),
        }
        ibi = read_ibi(directory / "IBI.csv")
        ibi_times = [timestamp for timestamp, _ in ibi]
        origin = max(signal.start for signal in signals.values())
        end = min(signal.end for signal in signals.values())
        calibration_start = origin + start_seconds
        calibration_end = calibration_start + baseline_seconds
        playback_start = calibration_end + window_seconds
        if playback_start + duration > end:
            raise ValueError(f"{participant} is too short for requested calibration and replay duration")
        calibration = [window_features(signals, ibi, ibi_times, timestamp - window_seconds, timestamp) for timestamp in range(int(calibration_start + window_seconds), int(calibration_end) + 1, step_seconds)]
        baseline = fit_baseline(calibration)
        baselines[worker_id] = baseline
        recording = []
        for offset in range(0, duration + 1, step_seconds):
            timestamp = playback_start + offset
            window = window_features(signals, ibi, ibi_times, timestamp - window_seconds, timestamp)
            window["timestamp"] = offset
            recording.append(window)
        output = finalize_windows(worker_id, recording, 0)
        all_windows.extend(output)
        recordings[worker_id] = {
            "participant": participant,
            "session": session,
            "sensor": "Empatica E4",
            "calibration_seconds_from_common_start": [start_seconds, start_seconds + baseline_seconds],
            "replay_seconds_from_common_start": [start_seconds + baseline_seconds + window_seconds, start_seconds + baseline_seconds + window_seconds + duration],
            "windows_with_missing_features": sum(bool(item.get("missing_features")) for item in output),
        }
    return {
        "metadata": {
            "kind": "universe",
            "name": "UNIVERSE recorded signals",
            "description": "Two real UNIVERSE Empatica recordings. Fictional worker identities; cognitive scores are unvalidated relative heuristics.",
            "source_url": SOURCE_URL,
            "doi": "10.5281/zenodo.10371068",
            "license": "CC-BY-4.0",
            "attribution": "Christoph Anders, Sidratul Moontaha, Samik Real, and Bert Arnrich. UNIVERSE, 2023. Derived features created for NEURASIGN.",
            "descriptor": "https://doi.org/10.1038/s41597-024-03738-7",
            "window_seconds": window_seconds,
            "step_seconds": step_seconds,
            "duration_seconds": duration,
            "recordings": recordings,
            "baseline_method": "Separate initial recording segment, per-person mean and population SD of overlapping windows with documented engineering SD floors; not a verified resting baseline.",
            "feature_method": "Mean HR (bpm), RMSSD of contiguous IBI pairs (ms), mean EDA (microSiemens), mean temperature (C), SD of acceleration magnitude (g). Trailing windows; no workload labels used.",
            "quality_method": "Heuristic completeness/reliable IBI-pair score, capped 0.85. Missing features are explicitly omitted and quality capped 0.35; inference uses neutral baseline when unavailable. Not calibrated prediction confidence.",
            "limitations": "No clinical or occupational validity; no artifact-removal model; pulse-derived HRV is not ECG HRV; physiology does not identify mental workload uniquely. Real participants do not represent fictional workers or incident outcomes.",
        },
        "baselines": baselines,
        "windows": sorted(all_windows, key=lambda item: (item["timestamp"], item["worker_id"])),
    }


def import_csv(path: Path, baseline_seconds: int, window_seconds: int, kind: str, source_url: str | None) -> dict:
    grouped: dict[str, list[dict]] = {"alex": [], "aoi": []}
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = csv.DictReader(handle)
        required = {"worker_id", "timestamp", *FEATURES}
        if not required.issubset(rows.fieldnames or []):
            raise ValueError(f"CSV must contain: {', '.join(sorted(required))}")
        for row in rows:
            worker_id = row["worker_id"]
            if worker_id not in grouped:
                raise ValueError("CSV worker_id must be alex or aoi")
            timestamp = float(row["timestamp"])
            features = {key: float(row[key]) if row[key].strip() else None for key in FEATURES}
            quality = float(row.get("quality") or "0.75")
            if not math.isfinite(timestamp) or timestamp < 0 or not math.isfinite(quality) or not 0 <= quality <= 1:
                raise ValueError("CSV timestamp must be nonnegative and finite; quality must be finite in 0..1")
            if any(value is not None and not math.isfinite(value) for value in features.values()):
                raise ValueError("CSV features must be finite numbers or blank for missing measurements")
            grouped[worker_id].append({"timestamp": timestamp, "features": features, "quality": quality})
    baselines, windows = {}, []
    for worker_id, recording in grouped.items():
        recording.sort(key=lambda item: item["timestamp"])
        if not recording or len({item["timestamp"] for item in recording}) != len(recording):
            raise ValueError(f"CSV requires unique timestamps and both workers; invalid {worker_id}")
        first = recording[0]["timestamp"]
        calibration = [item for item in recording if item["timestamp"] < first + baseline_seconds]
        playback = [item for item in recording if item["timestamp"] >= first + baseline_seconds]
        if not playback:
            raise ValueError(f"No {worker_id} playback remains after the calibration segment")
        baseline = fit_baseline(calibration)
        baselines[worker_id] = baseline
        windows.extend(finalize_windows(worker_id, playback, playback[0]["timestamp"]))
    return {
        "metadata": {
            "kind": kind,
            "name": "Imported UNIVERSE feature CSV" if kind == "universe" else "Imported synthetic feature CSV",
            "description": "User-supplied feature CSV; provenance asserted by importer. Relative inference is unvalidated.",
            "source_url": source_url,
            "window_seconds": window_seconds,
            "duration_seconds": max(item["timestamp"] for item in windows),
            "baseline_method": f"First {baseline_seconds} seconds per worker, excluded from playback; engineering SD floors applied.",
        },
        "baselines": baselines,
        "windows": sorted(windows, key=lambda item: (item["timestamp"], item["worker_id"])),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "data" / "universe" / "raw", help="Extracted UNIVERSE root containing UNIVERSE/UN_101/... or UN_101/...")
    parser.add_argument("--participants", nargs=2, default=["UN_101", "UN_103"], metavar=("ALEX_ID", "AOI_ID"))
    parser.add_argument("--session", choices=["Lab1", "Lab2"], default="Lab1")
    parser.add_argument("--csv", type=Path, help="Use canonical feature CSV instead of raw Empatica files")
    parser.add_argument("--kind", choices=["fixture", "universe"], default="fixture", help="CSV provenance only; raw UNIVERSE import always records kind=universe")
    parser.add_argument("--source-url", help="Required citation when importing a CSV with --kind universe")
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "universe" / "replay.json")
    parser.add_argument("--window-seconds", type=int, default=60)
    parser.add_argument("--step-seconds", type=int, default=10)
    parser.add_argument("--start-seconds", type=int, default=600, help="Discard initial interval before calibration; default600 chosen for E4 IBI completeness")
    parser.add_argument("--baseline-seconds", type=int, default=300)
    parser.add_argument("--duration-seconds", type=int, default=1800)
    args = parser.parse_args()
    if min(args.window_seconds, args.step_seconds, args.baseline_seconds, args.duration_seconds) <= 0 or args.start_seconds < 0:
        parser.error("Durations must be positive; --start-seconds may be zero")
    if args.csv and args.kind == "universe" and not args.source_url:
        parser.error("--source-url is required to declare a CSV as real UNIVERSE data")
    try:
        if args.csv:
            payload = import_csv(args.csv, args.baseline_seconds, args.window_seconds, args.kind, args.source_url)
        else:
            if args.participants[0] == args.participants[1]:
                raise ValueError("Choose two different participants")
            payload = import_empatica(args.input, dict(zip(("alex", "aoi"), args.participants)), args.session, args.start_seconds, args.baseline_seconds, args.duration_seconds, args.window_seconds, args.step_seconds)
            manifest = args.input / "manifest.json"
            if manifest.is_file():
                payload["metadata"]["download_manifest"] = json.loads(manifest.read_text())
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")
        temporary.replace(args.output)
        print(f"Wrote {args.output}: {len(payload['windows'])} windows, provenance={payload['metadata']['kind']}.")
        for worker_id in payload["baselines"]:
            missing = sum(bool(window.get("missing_features")) for window in payload["windows"] if window["worker_id"] == worker_id)
            print(f"{worker_id}: {missing} windows contain explicitly marked missing features (omitted, not fabricated).")
    except (OSError, ValueError, KeyError, StopIteration) as error:
        parser.exit(1, f"Import stopped: {error}\nExisting replay/fixtures were left unchanged.\n")


if __name__ == "__main__":
    main()
