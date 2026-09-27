"""Verified, unfiltered labeled sensor samples; no published feature tables."""
from collections import Counter
import hashlib
import io
import json
from pathlib import Path

import numpy as np
import pandas as pd
from pandas.compat.pickle_compat import Unpickler

from .causal import CHANNELS, FEATURES, PIPELINE, STEP, WINDOW, Trace, extract_window, validate_trace
from .data import FeatureUnpickler, parse_labels, verified_bytes
from .schema import TARGETS
from .training import save_json

DATETIME_GLOBALS = {
    ("pandas.core.indexes.datetimes", "_new_DatetimeIndex"),
    ("pandas.core.indexes.datetimes", "DatetimeIndex"),
    ("pandas._libs.arrays", "__pyx_unpickle_NDArrayBacked"),
    ("pandas.core.arrays.datetimes", "DatetimeArray"),
}
SOURCE_CHANNELS = {"bvp": "BVP", "eda": "EDA", "temperature": "TEMP",
                   "acc_x": "ACC_X", "acc_y": "ACC_Y", "acc_z": "ACC_Z", "heart_rate": "HR"}


class RawSignalUnpickler(FeatureUnpickler):
    def find_class(self, module, name):
        if (module, name) in DATETIME_GLOBALS:
            return Unpickler.find_class(self, module, name)
        return super().find_class(module, name)


def source_manifest(root):
    source = root / "data/universe"
    document = json.loads((source / "manifest.json").read_text())
    if document["summary"]["status"] != "complete":
        raise ValueError("Source download must be verified")
    return source / "extracted", {row["member"]: row for row in document["files"]}


def read_segment(segment: Path, source: Path, manifest):
    traces, provenance = {}, []
    clock_kind = None
    for name, filename in SOURCE_CHANNELS.items():
        path = segment / f"e4_{filename}.pickle"
        if not path.exists():
            continue
        table = RawSignalUnpickler(io.BytesIO(verified_bytes(path, source, manifest))).load()
        if not isinstance(table, pd.Series) or not len(table):
            raise ValueError("Raw channel must be a nonempty timestamped series")
        if isinstance(table.index, pd.DatetimeIndex):
            times = table.index.as_unit("ns").asi8.astype(float) / 1e9
            kind = "source_datetime"
        elif table.index.dtype.kind in "iu":
            # Authors retain row indices of the 64-Hz joined Empatica grid.
            times = table.index.to_numpy(dtype=float) / 64.
            kind = "empatica_grid_index_64hz"
        else:
            raise ValueError("Unknown source timestamp representation")
        if clock_kind is not None and clock_kind != kind:
            raise ValueError("Mixed timestamp representations cannot be aligned")
        clock_kind = kind
        rate, unit = CHANNELS[name]
        values = table.to_numpy(dtype=float)
        if name.startswith("acc_"):
            # Empatica info.txt: counts are 1/64 g, not m/s² or arbitrary units.
            values = values / 64.
        trace = Trace(times, values, rate, unit)
        validate_trace(trace)
        if len(times) < rate * WINDOW:
            raise ValueError("Source channel shorter than one evidence window")
        if abs(np.median(np.diff(times)) * rate - 1) > .1:
            raise ValueError("Source index does not match its declared native cadence")
        traces[name] = trace
        provenance.append({"member": path.relative_to(source).as_posix(),
                           "sha256": manifest[path.relative_to(source).as_posix()]["sha256"]})
    if "bvp" not in traces:
        raise ValueError("Source segment has no raw pulse wave")
    origin = float(traces["bvp"].times[0])
    return {name: Trace(trace.times - origin, trace.values, trace.rate, trace.unit)
            for name, trace in traces.items()}, {"clock": clock_kind, "origin": origin, "sources": provenance}


def build_causal_dataset(root: Path, rebuild=False):
    destination = root / "data/prepared/causal-v3"
    data_path, audit_path = destination / "windows.csv.gz", destination / "audit.json"
    split = json.loads((root / "experiments/split-v1.json").read_text())
    code_hash = hashlib.sha256((Path(__file__).read_bytes() +
        Path(__file__).with_name("causal.py").read_bytes())).hexdigest()
    if not rebuild and data_path.exists() and audit_path.exists():
        audit = json.loads(audit_path.read_text())
        if (audit["extractor_sha256"] == code_hash and audit["development"] == split["development"] and
                hashlib.sha256(data_path.read_bytes()).hexdigest() == audit["dataset_sha256"]):
            return pd.read_csv(data_path), audit
        raise ValueError("Causal cache changed; explicitly rebuild it")
    source, manifest = source_manifest(root)
    counts, rows, provenance, exclusions = Counter(), [], [], []
    by_participant = Counter()
    for participant in split["development"]:
        for label_path in sorted((source / "UNIVERSE" / participant).glob("*/Task_Labels.csv")):
            session = label_path.parent.name
            labels = parse_labels(label_path, verified_bytes(label_path, source, manifest), counts)
            for segment_name, match in sorted(labels.items()):
                segment = label_path.parent / "Labeled" / segment_name
                if not segment.is_dir() or not any(v is not None for v in match["targets"].values()):
                    counts["missing_labeled_segment"] += 1
                    continue
                counts["segments_considered"] += 1
                try:
                    traces, info = read_segment(segment, source, manifest)
                except (ValueError, TypeError) as error:
                    counts["segments_rejected"] += 1
                    exclusions.append({"segment": segment.relative_to(source).as_posix(), "reason": str(error)})
                    continue
                unit = hashlib.sha256(f"{participant}/{session}/{segment_name}".encode()).hexdigest()[:20]
                stop = traces["bvp"].times[-1] + 1 / traces["bvp"].rate
                accepted = 0
                for end in np.arange(WINDOW, stop + 1e-5, STEP):
                    counts["windows_considered"] += 1
                    row = extract_window(traces, float(end))
                    for flag in row["quality_flags"]:
                        counts[flag] += 1
                    if row["status"] != "features_ready":
                        counts["windows_rejected"] += 1
                        for reason in row["reasons"]:
                            counts[f"rejection:{reason}"] += 1
                        continue
                    rows.append({**row["features"], "participant": participant, "session": session,
                                 "unit_id": unit, "window_end": float(end),
                                 "source_end": info["origin"] + float(end),
                                 **{name: np.nan if value is None else value for name, value in match["targets"].items()}})
                    accepted += 1
                by_participant[participant] += accepted
                provenance.append({"unit_id": unit, "participant": participant, "session": session,
                                   "segment": segment.relative_to(source).as_posix(), "accepted_windows": accepted,
                                   "label_source": label_path.relative_to(source).as_posix(), **info})
        print(f"{participant}: {by_participant[participant]} causal windows", flush=True)
    data = pd.DataFrame(rows)
    if data.empty:
        raise ValueError("No raw causal windows passed quality checks")
    # A repeated recording instant must not count twice under different labels.
    duplicate = data.duplicated(["participant", "session", "source_end"], keep=False)
    counts["duplicate_instants_removed"] = int(duplicate.sum())
    data = data.loc[~duplicate].reset_index(drop=True)
    if set(data.participant) - set(split["development"]):
        raise ValueError("Original test participants entered causal training")
    destination.mkdir(parents=True, exist_ok=True)
    data.to_csv(data_path, index=False, compression={"method": "gzip", "mtime": 0})
    audit = {
        "pipeline": PIPELINE, "extractor_sha256": code_hash,
        "dataset_sha256": hashlib.sha256(data_path.read_bytes()).hexdigest(),
        "development": split["development"], "original_test_excluded": split["test"],
        "features": FEATURES, "window_seconds": WINDOW, "step_seconds": STEP,
        "windows": len(data), "units": data.unit_id.nunique(),
        "participants": sorted(data.participant.unique()), "counts": dict(counts),
        "coverage": {target: {"windows": int(data[target].notna().sum()),
                               "units": data.loc[data[target].notna(), "unit_id"].nunique()}
                     for target in TARGETS},
        "limitations": [
            "Labels are task/questionnaire ratings copied as weak supervision, not moment-by-moment ground truth.",
            "Recorded replay validates causal computation, not Bluetooth delivery or cross-device physiological accuracy.",
            "Empatica labeled raw samples retain source alignment; source sampling clocks were synchronized offline by the authors.",
            "Each labeled segment starts with an empty buffer; no future segment statistics or task identity enter features.",
            "Pulse-interval variability is not ECG HRV; quality thresholds are engineering checks, not clinical validation.",
        ],
    }
    save_json(audit_path, audit)
    save_json(destination / "provenance.json", provenance)
    save_json(destination / "exclusions.json", exclusions)
    return data, audit
