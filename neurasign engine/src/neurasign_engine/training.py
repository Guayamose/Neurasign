"""Grouped development validation and one held-out participant evaluation."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import platform
import time

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.metrics import balanced_accuracy_score, f1_score
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

from .model import MultiOutputEngine
from .schema import FEATURES, TARGETS, EXCLUDED_TARGETS, PIPELINE_ID, SEED


def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value,indent=2,allow_nan=False)+"\n")


def participant_split(root, participants):
    path = root/"experiments/split-v1.json"
    if path.exists():
        split = json.loads(path.read_text())
    else:
        shuffled = np.random.default_rng(SEED).permutation(sorted(participants)).tolist()
        split = {"seed":SEED,"unit":"participant","development":sorted(shuffled[5:]),
                 "test":sorted(shuffled[:5]),"selection":"Seeded ID permutation; no label balancing or performance-based selection."}
        save_json(path,split)
    development, test = set(split["development"]), set(split["test"])
    if development & test or development | test != set(participants) or len(development)!=19 or len(test)!=5:
        raise ValueError("Participant manifest must be disjoint and cover 19 development + 5 test participants")
    return split


def weights(frame):
    # Each participant has equal total influence, each questionnaire unit has
    # equal influence within that participant, regardless of window overlap.
    units = frame.groupby("participant").unit_id.transform("nunique").to_numpy()
    windows = frame.groupby("unit_id").unit_id.transform("size").to_numpy()
    value = 1/(units*windows)
    return value/value.mean()


def estimator(name):
    if name == "baseline":
        return DummyRegressor(strategy="mean")
    if name == "ridge":
        return make_pipeline(SimpleImputer(strategy="median",keep_empty_features=True),
                             StandardScaler(),Ridge(alpha=10.0))
    if name == "hist_gradient_boosting":
        return HistGradientBoostingRegressor(max_iter=100,learning_rate=.06,
            max_leaf_nodes=15,min_samples_leaf=60,l2_regularization=10,
            max_bins=128,early_stopping=False,random_state=SEED)
    raise ValueError(name)


def fit(model, name, frame, target):
    kwargs = {"ridge__sample_weight":weights(frame)} if name == "ridge" else {"sample_weight":weights(frame)}
    model.fit(frame[FEATURES],frame[target],**kwargs)
    return model


def unit_predictions(frame, target, prediction):
    rows = frame[["unit_id","participant","session",target]].copy()
    rows["prediction"] = prediction
    return rows.groupby(["unit_id","participant","session"],as_index=False).agg({target:"first","prediction":"mean"})


def metrics(frame, target, prediction):
    units = unit_predictions(frame,target,prediction)
    units["absolute_error"] = abs(units[target]-units.prediction)
    per_person = units.groupby("participant").absolute_error.mean()
    result = {
        "participant_macro_mae":float(per_person.mean()),
        "unit_mae":float(units.absolute_error.mean()),
        "label_units":len(units), "windows":len(frame), "participants":len(per_person),
        "per_participant_mae":{k:float(v) for k,v in per_person.items()},
        "by_session":{},
    }
    for session,group in units.groupby("session"):
        result["by_session"][session] = {
            "participant_macro_mae":float(group.groupby("participant").absolute_error.mean().mean()),
            "label_units":len(group),"participants":group.participant.nunique()}
    if TARGETS[target]["kind"] == "ordinal":
        labels = np.clip(np.floor(units.prediction.to_numpy()+.5),1,5).astype(int)
        truth = units[target].to_numpy(dtype=int)
        result["rounded_level_accuracy"] = float((labels==truth).mean())
        result["macro_f1_all_five_levels"] = float(f1_score(truth,labels,labels=[1,2,3,4,5],average="macro",zero_division=0))
    return result


def train(root: Path, data: pd.DataFrame, audit: dict):
    started = time.monotonic()
    split = participant_split(root,audit["participants"])
    results_root = root/"results/multioutput-v1"
    results_root.mkdir(parents=True,exist_ok=True)
    development = data[data.participant.isin(split["development"])].copy()
    report = {"pipeline":PIPELINE_ID,"seed":SEED,"split":split,"features":FEATURES,
              "targets":{},"excluded_targets":EXCLUDED_TARGETS,
              "dataset_sha256":audit["dataset_sha256"],"coverage":audit["coverage"],
              "versions":{"python":platform.python_version(),"numpy":np.__version__,"pandas":pd.__version__,"sklearn":sklearn.__version__},
              "limitations":audit["limitations"] + [
                  "Five held-out participants provide a limited research evaluation, not workplace or cross-device validation.",
                  "Predictions are estimates of questionnaire ratings, not observed mental states, diagnoses, productivity or fitness for duty.",
                  "Performance is self-reported; its numeric direction is preserved without asserting objective success.",
              ]}
    selected = {}
    candidates = ("baseline","ridge","hist_gradient_boosting")
    with threadpool_limits(limits=2):
        for target,spec in TARGETS.items():
            train_rows = development[development[target].notna()].copy()
            if train_rows.participant.nunique()<10 or train_rows.unit_id.nunique()<30:
                raise ValueError(f"Insufficient development label coverage: {target}")
            folds = list(GroupKFold(n_splits=5,shuffle=True,random_state=SEED).split(
                train_rows,groups=train_rows.participant))
            target_report = {"scale":spec["range"],"meaning":spec["meaning"],"validation":{}}
            for candidate in candidates:
                out_of_fold = np.full(len(train_rows),np.nan)
                fold_mae = []
                for train_indices,val_indices in folds:
                    fit_rows = train_rows.iloc[train_indices]
                    val_rows = train_rows.iloc[val_indices]
                    assert not set(fit_rows.participant)&set(val_rows.participant)
                    model = fit(estimator(candidate),candidate,fit_rows,target)
                    prediction = np.clip(model.predict(val_rows[FEATURES]),*spec["range"])
                    out_of_fold[val_indices] = prediction
                    fold_mae.append(metrics(val_rows,target,prediction)["participant_macro_mae"])
                target_report["validation"][candidate] = metrics(train_rows,target,out_of_fold)
                target_report["validation"][candidate]["fold_mae"] = fold_mae
                print(f"{target}: {candidate} grouped validation MAE = {target_report['validation'][candidate]['participant_macro_mae']:.3f}",flush=True)
            # Freeze selection before any held-out rating is used for scoring.
            chosen = min(("ridge","hist_gradient_boosting"),key=lambda name:target_report["validation"][name]["participant_macro_mae"])
            selected[target] = chosen
            target_report["selected_model"] = chosen
            report["targets"][target] = target_report
            save_json(results_root/"development.json",report)
        save_json(results_root/"frozen-selection.json",{"dataset_sha256":audit["dataset_sha256"],"split":split,"heads":selected})
        heads = {}
        for target,spec in TARGETS.items():
            train_rows = development[development[target].notna()]
            test_rows = data[data.participant.isin(split["test"]) & data[target].notna()]
            if test_rows.empty:
                raise ValueError(f"No held-out reference for {target}")
            chosen = selected[target]
            model = fit(estimator(chosen),chosen,train_rows,target)
            baseline = fit(estimator("baseline"),"baseline",train_rows,target)
            prediction = np.clip(model.predict(test_rows[FEATURES]),*spec["range"])
            baseline_prediction = np.clip(baseline.predict(test_rows[FEATURES]),*spec["range"])
            target_report = report["targets"][target]
            target_report["test"] = metrics(test_rows,target,prediction)
            target_report["baseline_test"] = metrics(test_rows,target,baseline_prediction)
            error = target_report["test"]["participant_macro_mae"]
            baseline_error = target_report["baseline_test"]["participant_macro_mae"]
            target_report["beat_baseline_on_holdout"] = error < baseline_error
            target_report["relative_mae_improvement"] = 1-error/baseline_error if baseline_error else None
            heads[target] = model
            predictions = unit_predictions(test_rows,target,prediction)
            predictions.to_csv(results_root/f"{target}-heldout-units.csv",index=False)
            print(f"{target}: held-out MAE {error:.3f}; baseline {baseline_error:.3f}",flush=True)
    report["elapsed_seconds"] = round(time.monotonic()-started,2)
    # Retain the models fitted to development participants only. Held-out
    # participants are never included in the persisted fitted artifact.
    bundle = MultiOutputEngine(heads,report)
    model_path = root/"models/multioutput-v1.joblib"
    model_path.parent.mkdir(parents=True,exist_ok=True)
    joblib.dump(bundle,model_path,compress=3)
    report["model_sha256"] = hashlib.sha256(model_path.read_bytes()).hexdigest()
    save_json(results_root/"report.json",report)
    write_report(root,report,audit)
    # Save a physiological-only input fixture for reproducing the CLI contract.
    row = data.iloc[0][FEATURES]
    save_json(results_root/"example-input.json",{"pipeline_id":PIPELINE_ID,"features":{
        key:None if pd.isna(value) else float(value) for key,value in row.items()}})
    return report


def write_report(root,report,audit):
    lines = ["# First wrist-only multi-output experiment", "", "Status: trained and evaluated offline; research use only.", "",
        f"The prepared dataset contains {audit['windows']:,} overlapping windows from {audit['label_units']:,} questionnaire/task intervals and {len(audit['participants'])} participants. A window is not an independent label.","",
        "## Outputs and held-out results", "",
        "MAE is the absolute error in questionnaire scale points, averaged within participant and then across the five held-out participants. Predictions are averaged over each labeled interval for scoring. A lower value is better. The baseline always predicts a development-set mean with participant/interval weighting.","",
        "| Output | Scale | Selected model | Model MAE | Baseline MAE | Better than baseline |",
        "| --- | --- | --- | ---: | ---: | --- |"]
    for name,row in report["targets"].items():
        lines.append(f"| {name} | {row['scale'][0]}–{row['scale'][1]} | {row['selected_model']} | {row['test']['participant_macro_mae']:.3f} | {row['baseline_test']['participant_macro_mae']:.3f} | {'Yes' if row['beat_baseline_on_holdout'] else 'No'} |")
    lines += ["","All six supported targets retain their original rating scales. Missing target values are masked independently; no missing questionnaire answer is imputed. The six heads share an input schema and bundle but are fitted separately.","",
        "## Selection and validation", "",
        "- Frozen participant split: 19 development participants, five held-out participants, recorded in `split-v1.json`.",
        "- Five-fold participant-grouped validation compares a mean baseline, ridge regression and histogram gradient boosting. Model selection finishes before held-out scoring.",
        "- Imputation and standardization are fitted inside each development fold. Tree early stopping is disabled to avoid a random internal window split.",
        "- Per-participant and per-interval sample weights prevent long recordings from dominating training.",
        "- Only the ten allowlisted pulse-HRV, EDA and temperature features enter the models. IDs, task names and all questionnaire responses are excluded from inputs.",
        "- Stress, frustration, PANAS and affective-slider outputs are excluded from workplace biometric inference. The weighted NASA composite is also excluded because it includes frustration.","",
        "## Data audit", "", "| Target | Labeled intervals | Windows | Participants |", "| --- | ---: | ---: | ---: |"]
    for name,row in audit["coverage"].items():
        lines.append(f"| {name} | {row['label_units']} | {row['windows']} | {row['participants']} |")
    lines += ["", "Audit exclusions and missingness: `"+json.dumps(audit["audit_counts"],sort_keys=True)+"`.","",
        "## Interpretation limits", ""] + ["- "+text for text in report["limitations"]]
    lines += ["","The source pipeline fills some missing feature values using later samples and processes complete segments. This experiment therefore does not validate live causal inference. Re-extract causal windows and evaluate signal quality and device transfer before live integration.","",
        "No score is claimed to measure fatigue, recovery, emotion, mental health, employee productivity or fitness for duty. A head that fails to beat the baseline has not demonstrated predictive benefit in this held-out comparison.","",
        "## Reproduction", "", "From the engine directory:", "", "```bash", ".venv/bin/python scripts/train_multioutput.py", ".venv/bin/python scripts/predict_multioutput.py --input results/multioutput-v1/example-input.json", "```", "",
        "Detailed reports/predictions are under ignored `results/multioutput-v1/`; the artifact is `models/multioutput-v1.joblib`. Model and data hashes are stored in the report. Repeatedly tuning on this held-out result would invalidate it as a final test.","",
        "Sources: [UNIVERSE](https://zenodo.org/records/10371068), [authors' feature extraction](https://github.com/HPI-CH/UNIVERSE/blob/main/Features/main_features.py), [participant-grouped validation](https://scikit-learn.org/stable/modules/cross_validation.html#cross-validation-iterators-for-grouped-data).", ""]
    (root/"experiments/001-multioutput-results.md").write_text("\n".join(lines))
