# Experiment 016: Oura daily readiness score approximation

**This predicts a vendor-generated daily score, not independently observed real-time employee readiness.**

Source: [IFH Affect/Dryad author archive mirrored by Zenodo](https://zenodo.org/records/10458511), CC0. The download contains 24 participant directories, while the paper and author loader specify par_1..par_21. Only that published cohort is considered; one has no sleep data and two have fewer than 10 aligned days. The retained 18 people provide 3472 daily observations. Four people / 684 days are reserved before model selection; the other 14 people supply 2788 development days.

The exact target is `oura/readiness.csv:score` on 1–100, with 0 treated as missing. Every readiness contributor and every other vendor `score` column is excluded from predictors. There is no target history, identity, demographic, mood or questionnaire input. Features use completed-sleep HR/HRV, respiration, temperature, sleep durations and stages, prior activity ending before the sleep cutoff, and strictly earlier 7/14-day physiological histories. Within-night variation uses only samples recorded by sleep end.

The source README describes sleep dates as prior-day dates, but 3,985 of 3,997 archive records end on their exported date in America/Los_Angeles. The pipeline requires that timestamp agreement and excludes the 12 mismatches. Date alignment was established before scoring; no shift was selected to maximize results. This remains an offline daily comparison: the source does not supply the exact publication time of each readiness score.

Four person-disjoint development folds compare 30 configurations of Ridge, RBF SVR, ExtraTrees and CatBoost across three feature profiles. Development MAE selects a three-model ensemble: SVR C10 and CatBoost depths 5/3 with sleep, physiology, prior activity and history. The ensemble is frozen before the single held-out evaluation.

| Metric, equal weight per person | Selected ensemble | Training-mean baseline |
|---|---:|---:|
| MAE, points out of 100 | 3.98 | 8.71 |
| RMSE, points out of 100 | 5.30 | 11.07 |
| R² | 0.770 | -0.002 |
| Within ±5 points | 71.7% | 34.8% |
| Within ±10 points | 93.4% | 65.7% |

**The 93.4% figure is agreement within ±10 points of Oura, not classification accuracy or physiological ground truth.** The MAE falls 54.4% relative to the constant baseline. The predefined research gate (MAE ≤8, at least 20% improvement, and R² ≥0.25) is met. Four held-out people still give limited population evidence. The 95% person-bootstrap MAE interval is 3.11–5.11 points; it does not measure device-transfer uncertainty.

The selected trained artifact is `models/readiness-oura-v1/selected.joblib`, with `production_enabled=False`. It requires completed overnight/daily summaries and does not operate on a one-second live wrist window. The company dashboard and demo remain unchanged.

Reproduce: `python3 scripts/download_readiness_oura.py`; then `.venv/bin/python scripts/run_readiness_oura.py prepare` and `run`. Inspect the completed immutable evaluation using `verify`.
