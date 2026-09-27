"""Isolated SWELL workbook experiment using physiological columns only.

The workbook contains offline Mobi ECG/finger-EDA features, not wrist samples.
Questionnaire ratings, experimental conditions and identifiers are never inputs.
"""
import hashlib
import json
from pathlib import Path
import posixpath
import time
import xml.etree.ElementTree as ET
import zipfile

import joblib
import numpy as np
import pandas as pd
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import RobustScaler
from sklearn.svm import SVR
from threadpoolctl import threadpool_limits

from .causal import json_ready
from .schema import SEED
from .training import save_json, weights
from .tuning import person_folds, paired_change

FEATURES = ["HR", "RMSSD", "SCL"]
TARGETS = {"mental_effort": "MentalEffort", "mental_demand": "MentalDemand",
           "physical_demand": "PhysicalDemand", "temporal_demand": "TemporalDemand",
           "effort": "Effort", "perceived_performance": "Performance_rc"}
PROFILES = {"native": FEATURES, "prior_rest": FEATURES + [name + "_minus_prior_rest" for name in FEATURES]}
NAMESPACE = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
EXCLUDED = ["Stress", "Frustration", "NasaTLX", "Valence_rc", "Arousal_rc", "Dominance",
            "facial-expression features", "Kinect posture features", "computer-interaction features",
            "Condition", "Blok", "PP", "timestamp", "other questionnaire ratings"]


def read_workbook(path):
    """Read cached scalar cells without executing formulas, macros or links."""
    with zipfile.ZipFile(path) as archive:
        if sum(f.file_size for f in archive.infolist()) > 100_000_000:
            raise ValueError("Workbook exceeds the bounded research import size")
        strings = []
        if "xl/sharedStrings.xml" in archive.namelist():
            strings = ["".join(t.text or "" for t in node.findall(".//s:t", NAMESPACE))
                       for node in ET.fromstring(archive.read("xl/sharedStrings.xml")).findall("s:si", NAMESPACE)]
        relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        paths = {node.get("Id"): node.get("Target") for node in relationships
                 if node.get("TargetMode") != "External"}
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        sheets = {}
        for sheet in workbook.findall("s:sheets/s:sheet", NAMESPACE):
            rid = sheet.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
            target = paths[rid]
            member = target.lstrip("/") if target.startswith("/") else posixpath.normpath("xl/" + target)
            if not member.startswith("xl/worksheets/"):
                raise ValueError("Unexpected worksheet location")
            rows = []
            for node in ET.fromstring(archive.read(member)).findall("s:sheetData/s:row", NAMESPACE):
                row = {}
                for cell in node.findall("s:c", NAMESPACE):
                    if cell.find("s:f", NAMESPACE) is not None:
                        raise ValueError("Formula cells require an explicitly verified static export")
                    column = "".join(c for c in cell.get("r", "") if c.isalpha())
                    value = cell.find("s:v", NAMESPACE)
                    if cell.get("t") == "s" and value is not None:
                        text = strings[int(value.text)]
                    elif cell.get("t") == "inlineStr":
                        text = "".join(t.text or "" for t in cell.findall(".//s:t", NAMESPACE))
                    else:
                        text = value.text if value is not None else ""
                    row[column] = text
                rows.append(row)
            sheets[sheet.get("name")] = rows
    if "SWELLdata" not in sheets:
        raise ValueError("Expected SWELLdata sheet")
    table = sheets["SWELLdata"]
    header = table[0]
    if len(set(header.values())) != len(header):
        raise ValueError("Duplicate feature names")
    data = pd.DataFrame(table[1:]).rename(columns=header).replace({"NaN": np.nan, "": np.nan})
    return data, sheets


def prepare_frame(source):
    required = ["PP", "Blok", "Condition", "timestamp", *FEATURES, *TARGETS.values()]
    if not set(required).issubset(source):
        raise ValueError("Missing expected physiological, label or grouping columns")
    frame = source[required].copy()
    frame["time"] = pd.to_datetime(frame.timestamp, format="%Y%m%dT%H%M%S%f", errors="raise")
    if frame.duplicated(["PP", "time"]).any():
        raise ValueError("Duplicate participant minutes")
    if not set(frame.Condition).issubset({"R", "N", "I", "T"}):
        raise ValueError("Unknown experimental condition")
    for name in FEATURES + list(TARGETS.values()):
        original = frame[name]
        frame[name] = pd.to_numeric(original, errors="raise")
        if np.isinf(frame[name]).any():
            raise ValueError("Infinite physiological feature or rating")
    if (frame[FEATURES] < 0).any().any():
        raise ValueError("Negative physiological values require explicit review")
    for target, column in TARGETS.items():
        # The RSME export contains values above 10; do not silently clip or map
        # it to UNIVERSE's different five-level mental-effort questionnaire.
        if (frame[column] < 0).any() or (target != "mental_effort" and (frame[column] > 10).any()):
            raise ValueError("Rating outside its documented scale")
        frame[target] = frame[column]
    frame["participant"] = frame.PP
    frame["unit_id"] = frame.PP + "/" + frame.Blok.astype(str)
    frame["session"] = frame.Condition
    frame["window_end"] = frame.time.astype("int64") / 1e9
    reference_audit = []
    for column in FEATURES:
        frame[column + "_minus_prior_rest"] = np.nan
    for (person, block), group in frame.groupby(["PP", "Blok"], sort=True):
        work = group[group.Condition != "R"]
        if work.empty:
            continue
        if work.Condition.nunique() != 1 or (work[list(TARGETS)].nunique() > 1).any():
            raise ValueError("A participant/block has inconsistent conditions or labels")
        # No target, future resting sample, other block or other person enters
        # this reference. Partial references remain explicitly missing.
        rest = group[(group.Condition == "R") & (group.time < work.time.min())]
        counts = {}
        for column in FEATURES:
            valid = rest[column].dropna()
            counts[column] = len(valid)
            if len(valid) >= 3:
                frame.loc[work.index, column + "_minus_prior_rest"] = work[column] - valid.median()
        reference_audit.append({"participant": person, "block": str(block), "valid_reference_minutes": counts,
                                "reference_before_work": True})
    eligible = (frame.Condition != "R") & frame[FEATURES].notna().any(axis=1)
    data = frame.loc[eligible, ["participant", "unit_id", "session", "window_end", *PROFILES["prior_rest"], *TARGETS]].copy().reset_index(drop=True)
    audit = {"source_rows": len(frame), "source_columns": len(source.columns), "participants": sorted(frame.PP.unique()),
             "represented_minutes": len(frame), "represented_hours": len(frame) / 60,
             "labeled_minutes": int((frame.Condition != "R").sum()),
             "labeled_blocks": frame.loc[frame.Condition != "R", "unit_id"].nunique(),
             "usable_minutes": len(data), "usable_hours": len(data) / 60,
             "usable_blocks": data.unit_id.nunique(), "usable_participants": sorted(data.participant.unique()),
             "all_physiology_missing_labeled_minutes": int(((frame.Condition != "R") & frame[FEATURES].isna().all(axis=1)).sum()),
             "complete_physiology_labeled_minutes": int(((frame.Condition != "R") & frame[FEATURES].notna().all(axis=1)).sum()),
             "missing_fraction_all_minutes": frame[FEATURES].isna().mean().to_dict(),
             "prior_rest_delta_available_fraction": data[[f + "_minus_prior_rest" for f in FEATURES]].notna().mean().to_dict(),
             "condition_counts": frame.Condition.value_counts().to_dict(), "references": reference_audit,
             "target_ranges_observed": {t: [float(data[t].min()), float(data[t].max())] for t in TARGETS},
             "mental_effort_above_10_blocks": int((data.groupby("unit_id").mental_effort.first() > 10).sum()),
             "units": "Original workbook values preserved; SCL/RMSSD units not mapped to canonical live telemetry units."}
    return data, json_ready(audit)


def configurations():
    choices = [{"name": "constant_" + method, "kind": "constant", "profile": "native", "strategy": method}
               for method in ("mean", "median")]
    for profile in PROFILES:
        for alpha in (10., 100.):
            choices.append({"name": f"{profile}_ridge_{alpha:g}", "kind": "ridge", "profile": profile, "alpha": alpha})
        choices.append({"name": profile + "_svr_1", "kind": "svr", "profile": profile})
        choices.append({"name": profile + "_boost_absolute", "kind": "boost", "profile": profile})
    return choices


def fit(config, rows, target):
    if config["kind"] == "constant":
        model = DummyRegressor(strategy=config["strategy"])
    elif config["kind"] == "boost":
        model = HistGradientBoostingRegressor(loss="absolute_error", max_iter=100, learning_rate=.05,
            max_leaf_nodes=7, min_samples_leaf=15, l2_regularization=10., max_bins=64,
            early_stopping=False, random_state=SEED)
    else:
        learner = Ridge(alpha=config["alpha"]) if config["kind"] == "ridge" else SVR(C=1., epsilon=.05)
        model = make_pipeline(SimpleImputer(strategy="median", add_indicator=True, keep_empty_features=True),
                              RobustScaler(quantile_range=(10, 90)), learner)
    argument = f"{model.steps[-1][0]}__sample_weight" if hasattr(model, "steps") else "sample_weight"
    model.fit(rows[PROFILES[config["profile"]]], rows[target] / 10., **{argument: weights(rows)})
    return model


def predict(model, config, rows, target):
    values = model.predict(rows[PROFILES[config["profile"]]]) * 10.
    return np.maximum(values, 0) if target == "mental_effort" else np.clip(values, 0, 10)


def metrics(rows, target, predictions):
    result = rows[["participant", "unit_id", target]].copy()
    error = abs(result[target].to_numpy() - np.asarray(predictions))
    if not np.isfinite(error).all():
        raise ValueError("Nonfinite evaluation error")
    result["error"] = error
    result["within_one"] = error <= 1.
    result["within_two"] = error <= 2.
    per_person = result.groupby(["participant", "unit_id"])[["error", "within_one", "within_two"]].mean().groupby("participant").mean()
    return {"participant_macro_mae": float(per_person.error.mean()),
            "within_one_point_fraction": float(per_person.within_one.mean()),
            "within_two_points_fraction": float(per_person.within_two.mean()),
            "tolerance_units": "original workbook points; not percent error or instantaneous-state ground truth",
            "per_participant_mae": per_person.error.to_dict(), "participants": len(per_person),
            "minutes": len(result), "blocks": result.unit_id.nunique()}


def run_swell(root, workbook):
    started = time.monotonic()
    digest = hashlib.sha256(workbook.read_bytes()).hexdigest()
    source, sheets = read_workbook(workbook)
    data, audit = prepare_frame(source)
    # Fixed participant split, independent of ratings and model performance.
    people = sorted(source.PP.unique())
    shuffled = np.random.default_rng(SEED).permutation(people).tolist()
    split = {"development": sorted(shuffled[5:]), "test": sorted(shuffled[:5]), "seed": SEED}
    if set(audit["usable_participants"]) != set(people):
        raise ValueError("Some participants have no usable physiological minutes; revise protocol explicitly")
    choices = configurations()
    plan = {"experiment": "005-swell-physiology", "workbook_name": workbook.name, "workbook_sha256": digest,
            "code_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "split": split, "development_folds": person_folds(split["development"], 5),
            "candidates": choices, "profiles": PROFILES, "targets": TARGETS, "excluded_inputs_targets": EXCLUDED,
            "labels": "Repeated condition questionnaire ratings. RSME is not UNIVERSE's five-level target.",
            "metric": "Per-minute absolute error, averaged within block, then participant, then people.",
            "agreement": "Absolute error <=1 original workbook point; <=2 also reported as secondary.",
            "reference": "Median of >=3 valid preceding relaxation minutes per signal within the same person/block; no reference labels or future samples.",
            "selection": "Five participant-grouped development folds; lowest MAE, constants eligible. All choices fixed before any test scoring.",
            "evaluation": "Five held-out participants evaluated once after selection. All candidates use the same available minutes.",
            "scope": "Offline Mobi ECG/finger-sensor research; no claim of wrist transfer, streaming feature equivalence or production validation.",
            "license": "Publisher lists CC-BY-NC-SA-4.0. Research artifact; commercial deployment is not authorized by this experiment."}
    frozen = root / "experiments/005-swell-protocol.json"
    if frozen.exists() and json.loads(frozen.read_text()) != json.loads(json.dumps(plan)):
        raise ValueError("Frozen SWELL protocol changed; version a new experiment")
    output = root / "results/swell-v1"
    if (output / "report.json").exists():
        raise ValueError("Completed holdout evaluation exists; inspect it instead of repeatedly scoring the same test set")
    save_json(frozen, plan)
    save_json(output / "audit.json", audit)
    destination = root / "data/prepared/swell-v1/minutes.csv.gz"
    destination.parent.mkdir(parents=True, exist_ok=True)
    data.to_csv(destination, index=False, compression={"method": "gzip", "mtime": 0})
    save_json(output / "workbook-notes.json", {key: value for key, value in sheets.items() if key != "SWELLdata"})
    development, test = data[data.participant.isin(split["development"])], data[data.participant.isin(split["test"])]
    selected, scores_all, heads = {}, {}, {}
    with threadpool_limits(limits=2):
        # Complete selection for every output before opening any test labels for scoring.
        for target in TARGETS:
            rows = development[development[target].notna()].reset_index(drop=True)
            scores = {}
            for config in choices:
                prediction = np.full(len(rows), np.nan)
                for train_ids, validation_ids in plan["development_folds"]:
                    fitting = rows[rows.participant.isin(train_ids)]
                    mask = rows.participant.isin(validation_ids).to_numpy()
                    model = fit(config, fitting, target)
                    prediction[mask] = predict(model, config, rows.loc[mask], target)
                scores[config["name"]] = metrics(rows, target, prediction)
            def best(candidates):
                return min(candidates, key=lambda c: scores[c["name"]]["participant_macro_mae"])
            selected[target] = {"selected": best(choices), "constant": best(choices[:2]), "learned": best(choices[2:]),
                                "native_learned": best([c for c in choices[2:] if c["profile"] == "native"]),
                                "prior_rest_learned": best([c for c in choices[2:] if c["profile"] == "prior_rest"])}
            scores_all[target] = scores
            save_json(output / "development.json", {"scores": scores_all, "choices": selected})
            print(f"{target}: development selected {selected[target]['selected']['name']}", flush=True)
        save_json(output / "frozen-selection.json", selected)
        report = {"protocol": plan, "data_audit": audit, "prepared_sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
                  "targets": {}, "development_scores": scores_all, "artifact_status": "research_only_not_promoted"}
        for target in TARGETS:
            fitting = development[development[target].notna()]
            evaluation = test[test[target].notna()]
            results, fitted = {}, {}
            for role, config in selected[target].items():
                if config["name"] not in fitted:
                    fitted[config["name"]] = fit(config, fitting, target)
                model = fitted[config["name"]]
                prediction = predict(model, config, evaluation, target)
                results[role] = metrics(evaluation, target, prediction)
                records = evaluation[["participant", "unit_id", "session", "window_end", target]].copy()
                records["prediction"] = prediction
                records.to_csv(output / f"{target}__{role}.csv.gz", index=False, compression={"method": "gzip", "mtime": 0})
            report["targets"][target] = {"choices": selected[target], "heldout": results,
                "learned_change_vs_constant": paired_change(results["constant"], results["learned"])}
            chosen = selected[target]["selected"]
            heads[target] = {"config": chosen, "model": fitted[chosen["name"]],
                             "status": "no_predictive_model_selected" if chosen["kind"] == "constant" else "research_only"}
            print(f"{target}: heldout learned MAE {results['learned']['participant_macro_mae']:.3f}, "
                  f"within ±1 {results['learned']['within_one_point_fraction']:.1%}; "
                  f"constant {results['constant']['within_one_point_fraction']:.1%}", flush=True)
    artifact = root / "models/swell-v1-research.joblib"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"heads": heads, "protocol": plan, "feature_profiles": PROFILES}, artifact)
    report.update(elapsed_seconds=time.monotonic() - started, artifact_sha256=hashlib.sha256(artifact.read_bytes()).hexdigest())
    save_json(output / "report.json", report)
    return report
