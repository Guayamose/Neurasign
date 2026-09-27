"""Build a masked multi-output table from verified published wrist features."""
from __future__ import annotations

from collections import Counter, defaultdict
import csv
import hashlib
import io
import json
from pathlib import Path

import numpy as np
import pandas as pd
from pandas.compat.pickle_compat import Unpickler

from .schema import FEATURE_GROUPS, FEATURES, TARGETS, EXCLUDED_TARGETS, WINDOW_SECONDS, STEP_SECONDS, PIPELINE_ID, normalize_likert

ALLOWED_GLOBALS = {
    ("pandas.core.frame", "DataFrame"), ("pandas.core.series", "Series"),
    ("pandas.core.internals.managers", "BlockManager"),
    ("pandas.core.internals.managers", "SingleBlockManager"),
    ("pandas._libs.internals", "_unpickle_block"),
    ("pandas.core.indexes.base", "_new_Index"), ("pandas.core.indexes.base", "Index"),
    ("pandas.core.indexes.range", "RangeIndex"),
    ("pandas.core.indexes.numeric", "Int64Index"),
    ("pandas.core.indexes.numeric", "Float64Index"),
    ("numpy", "ndarray"), ("numpy", "dtype"), ("builtins", "slice"),
    ("numpy.core.multiarray", "_reconstruct"), ("numpy._core.multiarray", "_reconstruct"),
    ("numpy.core.multiarray", "scalar"), ("numpy._core.multiarray", "scalar"),
    ("numpy.core.numeric", "_frombuffer"), ("numpy._core.numeric", "_frombuffer"),
}


class FeatureUnpickler(Unpickler):
    def find_class(self, module, name):
        if (module, name) not in ALLOWED_GLOBALS:
            raise ValueError(f"Unexpected object in dataset: {module}.{name}")
        return super().find_class(module, name)


def verified_bytes(path: Path, root: Path, manifest: dict) -> bytes:
    member = path.relative_to(root).as_posix()
    if member not in manifest:
        raise ValueError(f"File is absent from the verified source manifest: {member}")
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != manifest[member]["sha256"]:
        raise ValueError(f"Source file changed since download: {member}")
    return data


def parse_labels(path: Path, data: bytes, audit: dict):
    reader = csv.reader(io.StringIO(data.decode("utf-8-sig")))
    columns = next(reader)
    session = path.parent.name
    key = "Labeled folder names" if session == "Wild" else "Task"
    labels = {}
    ambiguous = set()
    for line, cells in enumerate(reader, 2):
        audit["questionnaire_rows"] += 1
        if len(cells) != len(columns):
            audit["invalid_questionnaire_row_width"] += 1
            continue
        row = dict(zip(columns, cells))
        segment = row.get(key, "").strip()
        if not segment:
            audit["questionnaire_without_segment"] += 1
            continue
        if segment == "video_baseline":
            segment = "relaxation_video"
        # Invalid words in these expected rating fields indicate a shifted or
        # malformed row. Reading the stress field here checks structure only.
        malformed = any(row.get(col, "").strip() and normalize_likert(row[col]) is None
                        for col in ("Mental effort level", "Mental stress level"))
        if malformed:
            audit["malformed_questionnaire_rows"] += 1
            continue
        target_values = {}
        for name, spec in TARGETS.items():
            value = row.get(spec["column"], "").strip()
            if not value:
                target_values[name] = None
                audit[f"missing_label:{name}"] += 1
                continue
            try:
                number = normalize_likert(value) if spec["kind"] == "ordinal" else float(value)
                if number is None or not np.isfinite(number) or not spec["range"][0] <= number <= spec["range"][1]:
                    raise ValueError("Out-of-range rating")
                target_values[name] = float(number)
            except ValueError:
                target_values[name] = None
                audit[f"invalid_label:{name}"] += 1
        if segment in labels and labels[segment]["targets"] != target_values:
            ambiguous.add(segment)
            audit["conflicting_questionnaire_segments"] += 1
        labels[segment] = {"targets": target_values, "line": line}
    return {k: v for k, v in labels.items() if k not in ambiguous}


def build_dataset(engine_root: Path):
    source = engine_root / "data/universe"
    root = source / "extracted"
    document = json.loads((source/"manifest.json").read_text())
    if document["summary"]["status"] != "complete":
        raise ValueError("Complete dataset acquisition verification first")
    manifest = {row["member"]: row for row in document["files"]}
    audit = Counter()
    missing_segments = []
    provenance = []
    frames = []
    duplicate_fingerprints = defaultdict(list)
    for label_path in sorted((root/"UNIVERSE").glob("*/*/Task_Labels.csv")):
        participant = label_path.parent.parent.name
        session = label_path.parent.name
        labels = parse_labels(label_path, verified_bytes(label_path, root, manifest), audit)
        for segment in sorted((label_path.parent/"Features").glob("*")):
            if not segment.is_dir():
                continue
            audit["feature_segments_seen"] += 1
            match = labels.get(segment.name)
            if match is None or not any(value is not None for value in match["targets"].values()):
                audit["segments_without_usable_questionnaire"] += 1
                missing_segments.append(str(segment.relative_to(root)))
                continue
            tables = []
            sources = []
            for filename, expected_columns in FEATURE_GROUPS.items():
                path = segment/filename
                if not path.exists():
                    continue
                data = verified_bytes(path, root, manifest)
                table = FeatureUnpickler(io.BytesIO(data)).load()
                if not isinstance(table, pd.DataFrame) or list(table.columns) != expected_columns:
                    raise ValueError(f"Unexpected feature schema: {path}")
                if not table.index.equals(pd.RangeIndex(len(table))):
                    raise ValueError(f"Unverified window alignment: {path}")
                tables.append(table.apply(pd.to_numeric, errors="coerce"))
                sources.append({"member": str(path.relative_to(root)), "sha256": hashlib.sha256(data).hexdigest()})
            if len(tables) != len(FEATURE_GROUPS):
                audit["segments_missing_modality"] += 1
                continue
            # The authors generate the same 60-second, 12-second-step windows
            # for each modality. Never align differing row counts by truncation.
            if len({len(table) for table in tables}) != 1:
                audit["segments_with_misaligned_modalities"] += 1
                continue
            features = pd.concat(tables, axis=1)[FEATURES].replace([np.inf, -np.inf], np.nan)
            good = features.notna().sum(axis=1) >= 8
            for cols in FEATURE_GROUPS.values():
                good &= features[cols].notna().any(axis=1)
            audit["windows_rejected_missing_features"] += int((~good).sum())
            if not good.any():
                continue
            source_key = f"{participant}/{session}/{segment.name}"
            unit = hashlib.sha256(source_key.encode()).hexdigest()[:20]
            fingerprint = hashlib.sha256(features.fillna(-1e308).to_numpy(dtype="<f8").tobytes()).hexdigest()
            duplicate_fingerprints[fingerprint].append(unit)
            row = features.loc[good].copy()
            row["unit_id"] = unit
            row["participant"] = participant
            row["session"] = session
            row["window_index"] = features.index[good]
            row["window_end_seconds_in_segment"] = WINDOW_SECONDS + row["window_index"]*STEP_SECONDS
            for name, value in match["targets"].items():
                row[name] = np.nan if value is None else value
            frames.append(row)
            provenance.append({"unit_id": unit, "participant": participant, "session": session,
                               "segment": segment.name, "label_source": str(label_path.relative_to(root)),
                               "label_line": match["line"], "feature_sources": sources,
                               "retained_windows": len(row), "source_window_count": len(features)})
    if not frames:
        raise ValueError("No verified feature/label pairs")
    dataset = pd.concat(frames, ignore_index=True)
    # Exclude every ambiguous repeated feature sequence rather than allowing
    # copies to straddle participants or inflate evaluation counts.
    duplicate_units = {unit for units in duplicate_fingerprints.values() if len(units)>1 for unit in units}
    audit["duplicate_feature_segments_removed"] = len(duplicate_units)
    dataset = dataset[~dataset.unit_id.isin(duplicate_units)].reset_index(drop=True)
    units = dataset.drop_duplicates("unit_id")
    coverage = {}
    for name, spec in TARGETS.items():
        valid = units[units[name].notna()]
        coverage[name] = {"label_units": len(valid), "windows": int(dataset[name].notna().sum()),
                          "participants": valid.participant.nunique(), "range": spec["range"],
                          "sessions": valid.session.value_counts().to_dict()}
    output = engine_root/"data/prepared"
    output.mkdir(parents=True, exist_ok=True)
    path = output/"wrist_multioutput.csv.gz"
    dataset.to_csv(path, index=False, compression={"method":"gzip", "mtime":0})
    report = {
        "pipeline": PIPELINE_ID, "features": FEATURES, "targets": TARGETS,
        "excluded_targets": EXCLUDED_TARGETS, "window_seconds": WINDOW_SECONDS, "step_seconds": STEP_SECONDS,
        "participants": sorted(dataset.participant.unique()), "windows": len(dataset),
        "label_units": dataset.unit_id.nunique(), "coverage": coverage, "audit_counts": dict(audit),
        "unmatched_feature_segments": missing_segments, "duplicate_units_removed": sorted(duplicate_units),
        "dataset_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "limitations": [
            "Offline published features: upstream interpolation/backfill and segment-wise processing can use future samples. Not a causal real-time validation.",
            "Labels describe whole tasks/questionnaire intervals; adjacent windows are not independent labels.",
            "Feature tables cover a subset of recorded hours. No conversion of overlapping windows into independent recording hours.",
            "These features use pulse-derived HRV, EDA and temperature; no EEG, task IDs, participant IDs or questionnaire answers are model inputs.",
            "Only physiological feature missingness is imputed inside training folds; missing targets are never fabricated.",
        ],
    }
    (output/"audit.json").write_text(json.dumps(report,indent=2)+"\n")
    (output/"provenance.json").write_text(json.dumps(provenance,indent=2)+"\n")
    return dataset, report
