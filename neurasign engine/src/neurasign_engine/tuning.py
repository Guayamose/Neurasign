"""Development-only, nested participant validation of interval representations.

This is an offline questionnaire-interval experiment, not a live feature pipeline.
The original five-person test set is never used for tuning or scoring here.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import time

import joblib
import numpy as np
import pandas as pd
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import ExtraTreesRegressor, HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVR
from threadpoolctl import threadpool_limits

from .schema import FEATURES, TARGETS, EXCLUDED_TARGETS, SEED, PIPELINE_ID
from .training import estimator, fit, metrics, participant_split, save_json, weights

INTERVAL_PIPELINE = "universe_complete_interval_summary_offline_v2"
STATISTICS = ("mean", "median", "std", "q10", "q90")
PROFILES = {
    "means": [f"{feature}__mean" for feature in FEATURES],
    "distribution": [f"{feature}__{stat}" for feature in FEATURES for stat in STATISTICS],
}
BASELINES = ("mean", "median")


def development_only(data, split):
    """Filter before any feature/label analysis and fail on unknown IDs."""
    known = set(split["development"]) | set(split["test"])
    if set(data.participant) - known:
        raise ValueError("Unexpected participants in the prepared dataset")
    result = data[data.participant.isin(split["development"])].copy()
    if set(result.participant) != set(split["development"]):
        raise ValueError("Development participants are missing")
    return result


def summarize_intervals(data):
    """No population statistics: each interval is summarized independently.

    Labels and identifiers are metadata only. Duration/window count/task names
    are deliberately not included in the predictor matrix.
    """
    metadata = ["participant", "session", *TARGETS]
    grouped = data.groupby("unit_id", sort=True)
    if (grouped[metadata].nunique(dropna=False) > 1).any().any():
        raise ValueError("An interval has conflicting participant/session/labels")
    signals = grouped[FEATURES]
    tables = {
        "mean": signals.mean(), "median": signals.median(),
        "std": signals.std(ddof=0),
        "q10": signals.quantile(.1), "q90": signals.quantile(.9),
    }
    output = pd.concat(
        [table.rename(columns=lambda column: f"{column}__{stat}")
         for stat, table in tables.items()], axis=1,
    )[PROFILES["distribution"]]
    return output.join(grouped[metadata].first()).reset_index()


def person_folds(participants, count, seed=SEED):
    people = np.array(sorted(set(participants)))
    splitter = GroupKFold(n_splits=count, shuffle=True, random_state=seed)
    return [(people[train].tolist(), people[test].tolist())
            for train, test in splitter.split(people, groups=people)]


def candidates():
    result = [{"name": f"constant_{strategy}", "kind": "constant",
               "profile": "means", "strategy": strategy} for strategy in BASELINES]
    for profile in PROFILES:
        for alpha in (1., 100., 1000.):
            result.append({"name": f"{profile}_ridge_{alpha:g}", "kind": "ridge",
                           "profile": profile, "alpha": alpha})
        for cost in (1., 10.):
            result.append({"name": f"{profile}_svr_{cost:g}", "kind": "svr",
                           "profile": profile, "C": cost})
        for loss in ("squared_error", "absolute_error"):
            result.append({"name": f"{profile}_boost_{loss}", "kind": "boost",
                           "profile": profile, "loss": loss})
        result.append({"name": f"{profile}_extra_trees", "kind": "extra_trees",
                       "profile": profile})
    return result


def make_candidate(config):
    kind = config["kind"]
    if kind == "constant":
        return DummyRegressor(strategy=config["strategy"])
    if kind == "boost":
        return HistGradientBoostingRegressor(
            loss=config["loss"], max_iter=80, learning_rate=.05,
            max_leaf_nodes=7, min_samples_leaf=15, l2_regularization=10,
            max_bins=64, early_stopping=False, random_state=SEED,
        )
    if kind == "ridge":
        regressor = Ridge(alpha=config["alpha"])
    elif kind == "svr":
        regressor = SVR(C=config["C"], epsilon=.05, gamma="scale")
    elif kind == "extra_trees":
        regressor = ExtraTreesRegressor(
            n_estimators=96, min_samples_leaf=10,
            max_features=1., random_state=SEED, n_jobs=1,
        )
    else:
        raise ValueError(kind)
    return make_pipeline(SimpleImputer(strategy="median", keep_empty_features=True),
                         StandardScaler(), regressor)


def fit_candidate(config, rows, target):
    model = make_candidate(config)
    lower, upper = TARGETS[target]["range"]
    outcome = (rows[target] - lower) / (upper - lower)
    argument = (f"{model.steps[-1][0]}__sample_weight"
                if hasattr(model, "steps") else "sample_weight")
    model.fit(rows[PROFILES[config["profile"]]], outcome, **{argument: weights(rows)})
    return model


def predict_candidate(model, config, rows, target):
    lower, upper = TARGETS[target]["range"]
    prediction = model.predict(rows[PROFILES[config["profile"]]])
    return np.clip(prediction, 0, 1) * (upper - lower) + lower


def candidate_search(rows, target, folds, configurations):
    scores = {}
    for config in configurations:
        predictions = np.full(len(rows), np.nan)
        for train_ids, validation_ids in folds:
            train = rows[rows.participant.isin(train_ids)]
            mask = rows.participant.isin(validation_ids).to_numpy()
            model = fit_candidate(config, train, target)
            predictions[mask] = predict_candidate(model, config, rows.loc[mask], target)
        if not np.isfinite(predictions).all():
            raise ValueError("Cross-validation did not cover every interval")
        scores[config["name"]] = metrics(rows, target, predictions)["participant_macro_mae"]
    # Constants appear first: an exact tie does not justify a learned model.
    return min(configurations, key=lambda config: scores[config["name"]]), scores


def original_search(windows, target, folds):
    scores = {}
    for name in ("ridge", "hist_gradient_boosting"):
        prediction = np.full(len(windows), np.nan)
        for train_ids, validation_ids in folds:
            train = windows[windows.participant.isin(train_ids)]
            mask = windows.participant.isin(validation_ids).to_numpy()
            model = fit(estimator(name), name, train, target)
            prediction[mask] = np.clip(model.predict(windows.loc[mask, FEATURES]), *TARGETS[target]["range"])
        scores[name] = metrics(windows, target, prediction)["participant_macro_mae"]
    return min(scores, key=scores.get), scores


def paired_change(reference, candidate):
    """Descriptive participant bootstrap; CV training sets are not independent."""
    people = sorted(reference["per_participant_mae"])
    changes = np.array([reference["per_participant_mae"][person] -
                        candidate["per_participant_mae"][person] for person in people])
    rng = np.random.default_rng(SEED)
    draws = rng.choice(changes, size=(5000, len(changes)), replace=True).mean(axis=1)
    return {
        "mean_mae_reduction": float(changes.mean()),
        "descriptive_bootstrap_95_percent": np.quantile(draws, [.025, .975]).tolist(),
        "participants_improved": int((changes > 0).sum()),
        "participants": len(people),
        "caution": "Descriptive only: folds share training people; not an independent confirmatory interval.",
    }


def run_tuning(root: Path):
    started = time.monotonic()
    prepared = root / "data/prepared/wrist_multioutput.csv.gz"
    audit = json.loads((prepared.parent / "audit.json").read_text())
    digest = hashlib.sha256(prepared.read_bytes()).hexdigest()
    if digest != audit["dataset_sha256"]:
        raise ValueError("Prepared dataset digest differs from its audit")
    split = participant_split(root, audit["participants"])
    data = development_only(pd.read_csv(prepared), split)
    intervals = summarize_intervals(data)
    configurations = candidates()
    outer_folds = person_folds(split["development"], 5)
    plan = {
        "experiment": "002-development-tuning", "seed": SEED,
        "source_pipeline": PIPELINE_ID, "pipeline": INTERVAL_PIPELINE,
        "dataset_sha256": digest, "development": split["development"],
        "excluded_original_test": split["test"], "profiles": PROFILES,
        "targets": TARGETS, "excluded_targets": EXCLUDED_TARGETS,
        "candidates": configurations, "outer_folds": outer_folds, "inner_folds": 3,
        "selection": "Minimum participant-macro interval MAE; constants eligible.",
        "comparison": "Original two-window-model selection rerun inside the same nested folds.",
        "scope": "Complete labeled intervals, offline only; not interchangeable with live windows.",
    }
    plan_path = root / "experiments/002-tuning-protocol.json"
    if plan_path.exists() and json.loads(plan_path.read_text()) != json.loads(json.dumps(plan)):
        raise ValueError("Protocol changed; use a new versioned experiment")
    save_json(plan_path, plan)
    output = root / "results/multioutput-v2"
    save_json(output / "protocol.json", plan)
    report = {
        "protocol": plan, "windows": len(data), "intervals": len(intervals),
        "original_test_evaluated": False, "targets": {},
        "versions": {"numpy": np.__version__, "pandas": pd.__version__,
                     "sklearn": __import__("sklearn").__version__},
    }
    heads = {}
    with threadpool_limits(limits=2):
        for target in TARGETS:
            units = intervals[intervals[target].notna()].reset_index(drop=True)
            windows = data[data[target].notna()].reset_index(drop=True)
            predictions = {key: np.full(len(units), np.nan)
                           for key in ("tuned", "original", "constant")}
            fold_reports = []
            for index, (train_ids, validation_ids) in enumerate(outer_folds):
                train = units[units.participant.isin(train_ids)]
                mask = units.participant.isin(validation_ids).to_numpy()
                validation = units.loc[mask]
                inner = person_folds(train_ids, 3, SEED + index + 1)
                chosen, scores = candidate_search(train, target, inner, configurations)
                constant = min(configurations[:2], key=lambda config: scores[config["name"]])
                for name, config in (("tuned", chosen), ("constant", constant)):
                    model = fit_candidate(config, train, target)
                    predictions[name][mask] = predict_candidate(model, config, validation, target)
                window_train = windows[windows.participant.isin(train_ids)]
                window_validation = windows[windows.participant.isin(validation_ids)]
                original, original_scores = original_search(window_train, target, inner)
                old_model = fit(estimator(original), original, window_train, target)
                old_prediction = np.clip(old_model.predict(window_validation[FEATURES]), *TARGETS[target]["range"])
                by_unit = window_validation[["unit_id"]].assign(prediction=old_prediction).groupby("unit_id").prediction.mean()
                predictions["original"][mask] = validation.unit_id.map(by_unit).to_numpy()
                fold_reports.append({
                    "fold": index, "train": train_ids, "validation": validation_ids,
                    "selected": chosen["name"], "constant": constant["name"],
                    "original": original, "inner_scores": scores,
                    "original_inner_scores": original_scores,
                })
                print(f"{target}: outer fold {index + 1}/5, selected {chosen['name']}", flush=True)
            if any(not np.isfinite(value).all() for value in predictions.values()):
                raise ValueError("Nested evaluation produced missing predictions")
            results = {name: metrics(units, target, prediction) for name, prediction in predictions.items()}
            chosen, scores = candidate_search(units, target, outer_folds, configurations)
            heads[target] = {"config": chosen, "model": fit_candidate(chosen, units, target)}
            results.update({
                "final_development_selection": chosen, "final_selection_scores": scores,
                "folds": fold_reports,
                "selection_counts": dict(Counter(fold["selected"] for fold in fold_reports)),
                "change_vs_original": paired_change(results["original"], results["tuned"]),
                "change_vs_constant": paired_change(results["constant"], results["tuned"]),
            })
            report["targets"][target] = results
            units[["unit_id", "participant", "session", target]].assign(**predictions).to_csv(
                output / f"{target}-nested-predictions.csv", index=False,
            )
            save_json(output / "progress.json", report)
            print(f"{target}: nested MAE {results['tuned']['participant_macro_mae']:.3f}; "
                  f"original {results['original']['participant_macro_mae']:.3f}; "
                  f"constant {results['constant']['participant_macro_mae']:.3f}", flush=True)
    artifact = root / "models/multioutput-v2-interval-research.joblib"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"research_only": True, "pipeline": INTERVAL_PIPELINE, "heads": heads,
                 "protocol": plan, "nested_metrics": report["targets"]}, artifact, compress=3)
    report["model_sha256"] = hashlib.sha256(artifact.read_bytes()).hexdigest()
    report["elapsed_seconds"] = round(time.monotonic() - started, 2)
    save_json(output / "report.json", report)
    write_tuning_report(root, report)
    return report


def write_tuning_report(root, report):
    lines = [
        "# Development-only representation and model search", "",
        "Status: completed offline exploratory experiment; no live deployment.", "",
        f"Only the original 19 development participants were used: {report['windows']:,} "
        f"windows and {report['intervals']} labeled intervals. The original five test participants "
        "were excluded before feature analysis, model selection and evaluation.", "",
        "## What changed", "",
        "Each questionnaire interval contributes one row. Candidate representations are the means "
        "of ten physiological features, or their mean, median, standard deviation and 10th/90th "
        "percentiles (50 features). No task identity, duration, participant identity or answers enter predictors.", "",
        "The fixed search includes ridge regularization, RBF support-vector regression, shallow gradient "
        "boosting with squared/absolute loss, and extra trees. Participant-weighted mean and median "
        "constants are eligible to win. Targets retain their original scales; internal 0–1 scaling "
        "uses those declared scale bounds, not population statistics.", "",
        "## Evaluation", "",
        "Five outer participant folds evaluate the entire selection procedure. Three inner participant "
        "folds choose models and representations using only each outer training partition. All learned "
        "preprocessing stays inside fitting folds. The original window-level ridge/boosting procedure "
        "is reselected within the same inner folds for a matched comparison. Every score below averages "
        "interval errors within participant, then across participants; lower is better.", "",
        "These are development nested-validation scores, not the first experiment's five-person test "
        "scores. Do not compare the numbers across those two populations.", "",
        "| Output | Original procedure MAE | Tuned procedure MAE | Constant procedure MAE | Change vs original |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for name, result in report["targets"].items():
        change = result["change_vs_original"]["mean_mae_reduction"]
        lines.append(f"| {name} | {result['original']['participant_macro_mae']:.3f} | "
                     f"{result['tuned']['participant_macro_mae']:.3f} | "
                     f"{result['constant']['participant_macro_mae']:.3f} | {change:+.3f} |")
    lines += ["", "Positive change means lower MAE. A tuned procedure may choose a constant: "
              "that is not evidence that physiology predicts the target.", "",
              "## Stability and final fit", "",
              "| Output | People improved vs original | Descriptive 95% interval for MAE reduction | Final candidate |",
              "| --- | ---: | --- | --- |"]
    for name, result in report["targets"].items():
        change = result["change_vs_original"]
        lower, upper = change["descriptive_bootstrap_95_percent"]
        lines.append(f"| {name} | {change['participants_improved']}/{change['participants']} | "
                     f"{lower:+.3f} to {upper:+.3f} | {result['final_development_selection']['name']} |")
    improved = sum(result["change_vs_original"]["mean_mae_reduction"] > 0
                   for result in report["targets"].values())
    uncertain = sum(result["change_vs_constant"]["descriptive_bootstrap_95_percent"][0] <= 0 <=
                    result["change_vs_constant"]["descriptive_bootstrap_95_percent"][1]
                    for result in report["targets"].values())
    lines += [
        "", "Bootstrap intervals resample participant errors and are descriptive only: folds share "
        "training participants, and this is a follow-up exploratory study. They are not confirmatory significance tests.", "",
        f"Point-estimate MAE improves over the original procedure for {improved}/6 outputs. "
        f"For {uncertain}/6 outputs, the descriptive range for improvement over the constant procedure "
        "includes zero. Retain this experiment for research; these results do not establish a clear "
        "physiological prediction benefit. In particular, lower errors obtained by selecting a constant "
        "do not demonstrate signal interpretation.", "",
        "A final five-fold search across all 19 development participants selects each persisted head. "
        "Its tuning score is not an independent evaluation of that exact fitted artifact. No original "
        "test participants are included in any persisted model.", "",
        "## Limits and next evidence", "",
        "- Complete-interval aggregation requires the interval to finish and know its boundaries. "
        "It cannot be substituted for a live rolling window.",
        "- Published source features already include noncausal processing. This experiment tests an "
        "offline representation hypothesis, not real-time performance.",
        "- Only 19 development people constrain generalization. More models cannot create missing "
        "physiological information or finer-grained ground truth.",
        "- Ratings remain self-reports, not observed states, productivity, fatigue or diagnoses. "
        "Emotion/mental-health outputs and the composite containing frustration remain excluded.",
        "- Future live work needs causal signal extraction, timestamped references and evaluation on "
        "new participants/devices; the already inspected five-person test cannot become fresh evidence.", "",
        "## Reproduce", "", "```bash", ".venv/bin/python scripts/tune_multioutput.py", "```", "",
        "The versioned protocol is `002-tuning-protocol.json`. Detailed fold predictions, search scores "
        "and hashes are in ignored `results/multioutput-v2/`. The separate research artifact is "
        "`models/multioutput-v2-interval-research.joblib`; v1 remains unchanged.", "",
        "Method references: [nested model selection](https://scikit-learn.org/stable/auto_examples/"
        "model_selection/plot_nested_cross_validation_iris.html), [participant groups](https://scikit-learn.org/"
        "stable/modules/cross_validation.html#cross-validation-iterators-for-grouped-data).", "",
    ]
    (root / "experiments/002-tuning-results.md").write_text("\n".join(lines))
