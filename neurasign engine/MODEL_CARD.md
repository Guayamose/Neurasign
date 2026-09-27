# NEURASIGN model evidence

NEURASIGN has trained research models and reproducible evaluation code. It does **not** have an independently validated model with 80% accuracy across stress, readiness, fatigue and workload. The company application does not load these research artifacts; the demo's workload, fatigue and readiness indices still use explicit experimental formulas.

## The four product outputs

| Product output | Available evidence | Current status |
| --- | --- | --- |
| Stress | Actual self-reported stress ratings in UNIVERSE and SWELL; new experiments 012 and 013 evaluate these labels directly | Trained research classifiers; insufficient evidence for general live wrist interpretation |
| Workload | Separate questionnaire dimensions such as mental, physical and temporal demand and effort | Multiple trained research models; a result for one dimension does not validate general workload |
| Fatigue | No aligned fatigue reference identified in the acquired/prepared training sources | Demo formula only; physical demand and effort are not relabeled fatigue |
| Readiness | No defined, aligned readiness outcome in the acquired/prepared training sources | Demo formula only; no measured predictive accuracy |

A common feature pipeline or shared neural encoder cannot create missing target answers. Each target needs its own reference definition and evaluation. These outputs cannot share one claimed accuracy number.

## Stress: measured SWELL result

[Experiment 013](experiments/013-swell-stress-results.md) trains on the workbook's actual `Stress` responses. It compares low (≤3⅓) and high (≥6⅔) exported ratings; middle ratings are excluded. Inputs are HR, RMSSD and SCL. They were measured with chest ECG and finger conductance, so this is **not validation on consumer wrist devices**.

The fixed model is a logistic classifier with C=1, specified before observing the new results. Imputation and scaling are fitted inside training folds. Five outer folds hold out whole people; an additional selected-model arm chooses among four algorithms using three inner person-disjoint folds. All evaluated minutes are out of fold.

| Prespecified arm | Person/block-weighted accuracy | Balanced accuracy | High-stress recall |
| --- | ---: | ---: | ---: |
| Always the outer-training majority | 88.2% | 50.0% | 0.0% |
| Fixed logistic model | **79.5%** | **75.5%** | **70.2%** |
| Model selected inside training folds | 73.8% | 50.6% | 20.2% |

The fixed model's result is a measured, exploratory benchmark result. It must not be rounded into “NEURASIGN detects employee states with 80% accuracy.” The selected procedure's much weaker result is also reported; no winner is retroactively substituted for that procedure.

The evaluated subset contains 17 development people, 41 blocks and 1,235 minute rows, from 1,766 development minutes with physiology. It excludes 531 middle-rated minutes. Only **four blocks from three people** have high stress; only two people have both low and high blocks. Their fixed-model within-person balanced accuracy is 45.2%, which is not evidence of reliable individual state-change detection. The minutes repeat block-level answers and are not independent labels. The original five test people remain excluded; this is development evaluation, not fresh external confirmation.

## Other stress and workload evidence

[Experiment 012](experiments/012-stress-results.md) joins original UNIVERSE stress responses to the existing wrist feature windows. Label coverage leaves only two paired people for Lab1-to-Lab2 evaluation. The selected personal model scores 59.5% within-person balanced accuracy; that sample is too small to establish generalization. The missing labels are not inferred from tasks or other questionnaires.

[Experiment 010](experiments/010-personalization-results.md) measures a separate workload component: low/high self-reported mental demand. The hybrid reaches 60.1% within-person balanced accuracy in 17 people and 54.3% when relaxation is excluded among the 13 retaining both classes. These are not stress, fatigue or readiness accuracy figures.

[Experiment 011](experiments/011-short-window-results.md) compares exactly one second of raw samples against matched sixty-second windows. The one-second mental-demand results remain near the 50% constant reference. This did not produce a faster validated interpretation model.

## Review and reproduce

The complete model definitions, preprocessing, grouping rules, target thresholds, protocols and aggregate results are versionable source files. Datasets, individual predictions, provider responses and fitted artifacts remain in ignored local directories with checksums. Credentials remain in ignored environment files.

From `neurasign engine/`:

```sh
# Verify already completed research artifacts without tuning on their outcomes.
.venv/bin/python scripts/run_stress_benchmark.py verify
.venv/bin/python scripts/run_swell_stress.py verify
.venv/bin/python scripts/run_short_window.py verify

# Run the engine's implementation tests.
.venv/bin/python -m unittest discover -s tests -v
```

The experiment 012 and 013 reports document their reproduction commands. Preparation requires the verified source data and prior participant splits described in the engine README. Completed runs refuse replacement. Existing test subjects are not silently recycled into training.

Artifacts explicitly carry `production_enabled=False`. Research predictions are neither diagnoses nor fitness-for-duty clearance. No trained stress output has been connected to named employees or the manager dashboard.
