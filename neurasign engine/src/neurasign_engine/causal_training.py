"""Grouped model search scored on individual causal windows with weak labels."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import time
import warnings

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.exceptions import ConvergenceWarning
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.metrics import f1_score
from sklearn.neural_network import MLPRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import FunctionTransformer, RobustScaler
from threadpoolctl import threadpool_limits

from .causal import FEATURES, PIPELINE, STEP, WINDOW, json_ready
from .schema import TARGETS, EXCLUDED_TARGETS, SEED
from .training import save_json, weights
from .tuning import person_folds, paired_change

CONFIGURATIONS = [
    {"name": "constant_mean", "kind": "constant", "strategy": "mean"},
    {"name": "constant_median", "kind": "constant", "strategy": "median"},
    {"name": "ridge_100", "kind": "ridge", "alpha": 100.},
    {"name": "ridge_1000", "kind": "ridge", "alpha": 1000.},
    {"name": "boost_squared_7", "kind": "boost", "loss": "squared_error", "leaves": 7},
    {"name": "boost_absolute_7", "kind": "boost", "loss": "absolute_error", "leaves": 7},
    {"name": "boost_squared_15", "kind": "boost", "loss": "squared_error", "leaves": 15},
    {"name": "neural_32_16", "kind": "neural", "hidden_layers": [32, 16], "alpha": 1.},
]
FIT_WINDOWS_PER_INTERVAL = 20


def thin_training(rows):
    indices = []
    for _, group in rows.sort_values("window_end").groupby("unit_id", sort=True):
        chosen = np.unique(np.linspace(0, len(group) - 1, min(len(group), FIT_WINDOWS_PER_INTERVAL)).astype(int))
        indices.extend(group.iloc[chosen].index.tolist())
    return rows.loc[indices]


def make_estimator(config):
    if config["kind"] == "constant":
        return DummyRegressor(strategy=config["strategy"])
    if config["kind"] == "boost":
        return HistGradientBoostingRegressor(
            loss=config["loss"], max_iter=100, learning_rate=.05,
            max_leaf_nodes=config["leaves"], min_samples_leaf=30,
            l2_regularization=10, early_stopping=False, max_bins=64, random_state=SEED)
    if config["kind"] == "neural":
        model = MLPRegressor(hidden_layer_sizes=tuple(config["hidden_layers"]), alpha=config["alpha"],
                             activation="tanh", max_iter=150, batch_size=128,
                             early_stopping=False, random_state=SEED, tol=1e-4)
    else:
        model = Ridge(alpha=config["alpha"])
    return make_pipeline(SimpleImputer(strategy="median", add_indicator=True, keep_empty_features=True),
                         RobustScaler(quantile_range=(10, 90)),
                         FunctionTransformer(np.tanh, feature_names_out="one-to-one"), model)


def fit_model(config, rows, target):
    fitting = thin_training(rows)
    model = make_estimator(config)
    low, high = TARGETS[target]["range"]
    parameter = f"{model.steps[-1][0]}__sample_weight" if hasattr(model, "steps") else "sample_weight"
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", ConvergenceWarning)
        model.fit(fitting[FEATURES], (fitting[target] - low) / (high - low), **{parameter: weights(fitting)})
    info = {"training_windows": len(fitting),
            "convergence_warnings": [str(w.message) for w in caught if issubclass(w.category, ConvergenceWarning)]}
    return model, info


def predict_model(model, rows, target):
    low, high = TARGETS[target]["range"]
    return np.clip(model.predict(rows[FEATURES]), 0, 1) * (high - low) + low


def window_metrics(rows, target, prediction):
    prediction = np.asarray(prediction, dtype=float)
    error = abs(rows[target].to_numpy() - prediction)
    if not np.isfinite(error).all():
        raise ValueError("Evaluation predictions must be finite")
    frame = rows[["participant", "unit_id", "session", target]].copy()
    frame["absolute_error"] = error
    frame["prediction"] = prediction
    units = frame.groupby(["participant", "unit_id", "session"], as_index=False).absolute_error.mean()
    people = units.groupby("participant").absolute_error.mean()
    weight = weights(rows)
    tolerance = 1. if target == "mental_effort" else 10.
    result = {
        "participant_macro_mae": float(people.mean()),
        "weighted_rmse": float(np.sqrt(np.average(error ** 2, weights=weight))),
        "within_tolerance_fraction": float(np.average(error <= tolerance, weights=weight)),
        "tolerance_points": tolerance, "windows": len(rows), "units": len(units), "participants": len(people),
        "per_participant_mae": {str(k): float(v) for k, v in people.items()},
        "by_session": {name: {"mae": float(group.groupby("participant").absolute_error.mean().mean()),
                              "units": len(group)} for name, group in units.groupby("session")},
        "label_reference": "repeated_questionnaire_interval_rating_not_instantaneous_truth",
    }
    if target == "mental_effort":
        rounded = np.clip(np.floor(prediction + .5), 1, 5)
        result["weighted_exact_level_accuracy"] = float(np.average(rounded == rows[target], weights=weight))
        result["weighted_macro_f1"] = float(f1_score(rows[target], rounded, labels=[1, 2, 3, 4, 5],
            average="macro", sample_weight=weight, zero_division=0))
    # Secondary only: averaging predictions can hide window-level errors.
    aggregated = frame.groupby(["participant", "unit_id"], as_index=False).agg({target: "first", "prediction": "mean"})
    aggregated["error"] = abs(aggregated[target] - aggregated.prediction)
    result["secondary_interval_average_mae"] = float(aggregated.groupby("participant").error.mean().mean())
    return result


def select(rows, target, folds):
    scores, fit_notes = {}, Counter()
    for config in CONFIGURATIONS:
        predictions = np.full(len(rows), np.nan)
        for fitting_ids, validation_ids in folds:
            fitting = rows[rows.participant.isin(fitting_ids)]
            mask = rows.participant.isin(validation_ids).to_numpy()
            model, info = fit_model(config, fitting, target)
            fit_notes[config["name"]] += len(info["convergence_warnings"])
            predictions[mask] = predict_model(model, rows.loc[mask], target)
        scores[config["name"]] = window_metrics(rows, target, predictions)["participant_macro_mae"]
    return min(CONFIGURATIONS, key=lambda candidate: scores[candidate["name"]]), scores, dict(fit_notes)


class CausalModel:
    def __init__(self, heads, report):
        if set(heads) != set(TARGETS):
            raise ValueError("Exactly the supported six outputs are required")
        self.heads, self.report = heads, report

    def predict(self, window):
        if window["pipeline_id"] != PIPELINE or set(window["features"]) != set(FEATURES):
            raise ValueError("Model and signal extraction pipelines differ")
        result = {**window, "research_only": True, "confidence": None,
                  "label_granularity": "questionnaire_interval", "estimates": {}}
        if window["status"] != "features_ready":
            return json_ready(result)
        frame = pd.DataFrame([window["features"]], columns=FEATURES)
        for target, head in self.heads.items():
            info = self.report["targets"][target]
            value = {"scale": TARGETS[target]["range"], "confidence": None,
                     "window_validation_mae": info["selected"]["participant_macro_mae"],
                     "constant_validation_mae": info["constant"]["participant_macro_mae"]}
            if head["config"]["kind"] == "constant":
                value["status"] = "no_predictive_model_selected"
            else:
                value.update(status="experimental_questionnaire_estimate",
                             predicted_rating=float(predict_model(head["model"], frame, target)[0]))
            result["estimates"][target] = value
        result["status"] = "experimental_estimates"
        return json_ready(result)


def train_causal(root: Path, data, audit):
    started = time.monotonic()
    if set(data.participant) != set(audit["development"]):
        raise ValueError("Every development participant must have usable causal windows")
    outer = person_folds(audit["development"], 5)
    protocol = {
        "pipeline": PIPELINE, "seed": SEED, "features": FEATURES,
        "window_seconds": WINDOW, "step_seconds": STEP, "candidates": CONFIGURATIONS,
        "fit_windows_per_interval": FIT_WINDOWS_PER_INTERVAL,
        "development": audit["development"], "excluded_test": audit["original_test_excluded"],
        "outer_folds": outer, "inner_folds": 3,
        "dataset_sha256": audit["dataset_sha256"], "extractor_sha256": audit["extractor_sha256"],
        "metric": "absolute error of each window, mean within interval, then within participant, then across participants",
        "neural_training": "32/16 tanh units, 150 maximum epochs, no random validation/early stopping, alpha=1",
        "preprocessing": "Fold-only median imputation with missing indicators, robust 10/90 scaling, tanh for ridge/MLP",
        "targets": TARGETS, "excluded_targets": EXCLUDED_TARGETS,
    }
    protocol_path = root / "experiments/003-causal-protocol.json"
    if protocol_path.exists() and json.loads(protocol_path.read_text()) != json.loads(json.dumps(protocol)):
        raise ValueError("Frozen causal protocol changed; version a new experiment")
    save_json(protocol_path, protocol)
    output = root / "results/causal-v3"
    report = {"protocol": protocol, "data_audit": audit, "targets": {}, "original_test_evaluated": False,
              "versions": {"sklearn": sklearn.__version__, "numpy": np.__version__, "pandas": pd.__version__}}
    heads = {}
    with threadpool_limits(limits=2):
        for target in TARGETS:
            rows = data[data[target].notna()].reset_index(drop=True)
            predictions = {name: np.full(len(rows), np.nan) for name in ("selected", "constant", "learned")}
            folds = []
            for index, (train_ids, validation_ids) in enumerate(outer):
                fitting = rows[rows.participant.isin(train_ids)]
                mask = rows.participant.isin(validation_ids).to_numpy()
                inner = person_folds(train_ids, 3, SEED + index + 1)
                chosen, scores, notes = select(fitting, target, inner)
                constant = min(CONFIGURATIONS[:2], key=lambda c: scores[c["name"]])
                learned = min(CONFIGURATIONS[2:], key=lambda c: scores[c["name"]])
                for name, config in (("selected", chosen), ("constant", constant), ("learned", learned)):
                    model, _ = fit_model(config, fitting, target)
                    predictions[name][mask] = predict_model(model, rows.loc[mask], target)
                folds.append({"fold": index, "fit": train_ids, "validation": validation_ids,
                              "selected": chosen["name"], "learned": learned["name"],
                              "scores": scores, "convergence_warnings": notes})
                print(f"{target}: causal outer fold {index + 1}/5, {chosen['name']}", flush=True)
            metrics = {name: window_metrics(rows, target, pred) for name, pred in predictions.items()}
            chosen, scores, notes = select(rows, target, outer)
            model, fit_info = fit_model(chosen, rows, target)
            heads[target] = {"config": chosen, "model": model}
            report["targets"][target] = {**metrics, "folds": folds, "final_config": chosen,
                "final_selection_scores": scores, "final_convergence_warnings": notes, "final_fit": fit_info,
                "change_vs_constant": paired_change(metrics["constant"], metrics["selected"])}
            save_json(output / "progress.json", report)
            rows[["participant", "session", "unit_id", "window_end", target]].assign(**predictions).to_csv(
                output / f"{target}-predictions.csv.gz", index=False, compression={"method": "gzip", "mtime": 0})
            print(f"{target}: per-window weak-label MAE {metrics['selected']['participant_macro_mae']:.3f}; "
                  f"constant {metrics['constant']['participant_macro_mae']:.3f}", flush=True)
    report["elapsed_seconds"] = round(time.monotonic() - started, 2)
    artifact = root / "models/causal-v3.joblib"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(CausalModel(heads, report), artifact, compress=3)
    report["model_sha256"] = hashlib.sha256(artifact.read_bytes()).hexdigest()
    save_json(output / "report.json", report)
    write_report(root, report)
    return report


def write_report(root, report):
    audit = report["data_audit"]
    lines = ["# Causal raw-wrist streaming experiment", "",
        "Status: trained and evaluated against weak questionnaire labels; streaming replay is implemented.", "",
        f"{audit['windows']:,} usable windows from {audit['units']} intervals and {len(audit['participants'])} development participants. "
        "The original five test participants were not read for feature extraction, fitting or scoring.", "",
        "## Live computation contract", "",
        "A prediction uses the preceding 60 seconds and updates every 10 seconds. Raw labeled BVP, EDA, "
        "temperature, HR and three acceleration axes replace the authors' offline feature tables. "
        "The same extractor processes recorded prefixes and incoming blocks. Every operation is limited "
        "to samples before the prediction timestamp; there is no backward fill, future interpolation, "
        "whole-task normalization or completed-task feature aggregation.", "",
        "43 features describe pulse-wave shape/periodicity and pulse intervals, skin signals, trends and "
        "movement. Acceleration counts are converted to g; magnitude is recomputed from XYZ because some "
        "published ACC_MAG series contain erroneous zeros. Pulse variability is masked when heuristic "
        "quality or motion checks fail; missing channels/gaps cause abstention, not fabricated readings.", "",
        "## Model comparison", "",
        "Eight configurations cover mean/median references, ridge regression, gradient-boosted trees and "
        "a 32/16-unit neural network. Neural training has no random internal validation split. "
        "Up to 20 evenly spaced windows per interval are used for fitting to limit overlap redundancy; "
        "every usable evaluation window is scored. Missing answers are masked independently.", "",
        "Five outer participant folds evaluate selection; three inner folds tune models. Unlike v1/v2, "
        "the primary error is computed before averaging window predictions: errors cannot cancel within "
        "a task. Interval and participant weighting prevent long recordings from dominating.", "",
        "| Output | Selected procedure MAE | Best learned procedure MAE | Constant procedure MAE | Final choice |",
        "| --- | ---: | ---: | ---: | --- |"]
    for target, row in report["targets"].items():
        lines.append(f"| {target} | {row['selected']['participant_macro_mae']:.3f} | "
                     f"{row['learned']['participant_macro_mae']:.3f} | {row['constant']['participant_macro_mae']:.3f} | "
                     f"{row['final_config']['name']} |")
    lines += ["", "These scores evaluate the selection procedure across development people. They are not "
        "independent test scores of the final artifact, and cannot be compared directly to v1/v2 scores "
        "with different accepted windows and evaluation definitions.", "", "## Limits", ""]
    lines += ["- " + item for item in audit["limitations"]]
    lines += [
        "- Per-prediction confidence remains null. Sensor-quality flags are not calibrated probabilities.",
        "- A selected constant produces `no_predictive_model_selected`, never a fake changing state score.",
        "- Predicting a questionnaire rating from a past window does not validate instantaneous state changes.",
        "- Emotions, mental-health outputs and the composite containing frustration remain excluded.",
        "- This is an engine interface and recorded replay; it is not a production API integration or hardware certification.", "",
        "## Quality coverage", "", f"```json\n{json.dumps(audit['counts'], indent=2)}\n```", "",
        "## Reproduce", "", "```bash", ".venv/bin/python scripts/train_causal.py",
        ".venv/bin/python scripts/replay_causal.py --participant UN_101 --session Lab1 --seconds 180",
        ".venv/bin/python scripts/stream_causal.py < samples.jsonl", "```", "",
        "The model is `models/causal-v3.joblib`; full per-window predictions and metrics are under "
        "`results/causal-v3/`. The extractor, raw provenance and quality exclusions are under "
        "`data/prepared/causal-v3/`. These directories are ignored by Git.", "",
        "References: [UNIVERSE source synchronization](https://github.com/HPI-CH/UNIVERSE/blob/main/Synchronization/main.py), "
        "[forward filtering](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.sosfilt.html), "
        "[MLP regression](https://scikit-learn.org/stable/modules/generated/sklearn.neural_network.MLPRegressor.html).", "",
    ]
    (root / "experiments/003-causal-results.md").write_text("\n".join(lines))
