# Experiment 019: richer physiological context for daily readiness

**Exploratory nested development evaluation. The original four test people remain excluded.**

This evaluates 2788 daily observations from 14 previously studied development people. Four outer folds hold out complete people; three inner folds select configurations using only the outer-training people. All preprocessing and physiological model fitting stay inside the training folds. Prior experiments informed the candidate design, so this is not fresh external validation. The earlier 3.98-point test MAE remains a separate result on a different cohort.

Target: the observed 1–100 Oura daily readiness score in [IFH Affect](https://zenodo.org/records/10458511), CC0. It is a vendor-score approximation, not an independently measured instantaneous employee state. No vendor score, readiness contributor, target history, identity or questionnaire is a predictor.

The original 50 features are compared with 261 physiological/context features: sleep-stage fractions, sleep timing phase, strictly preceding 7/14/28-day personal physiology references, previous activity, and raw overnight HR/HRV recovery trajectories. Measurements use the published sleep-end cutoff, subject to the source timing qualification below. Calendar dates and absolute timestamps are used for alignment only.

Eighteen registered profile/algorithm configurations compare ridge, spline ridge, RBF SVR, CatBoost with squared or absolute loss, and histogram gradient boosting with absolute loss. A mean of the top three inner models may win on inner MAE. The fixed historical reference refits the experiment016 SVR C10 / CatBoost depth3 / CatBoost depth5 ensemble on exactly the same outer-training people, preserving its original preprocessing. The constant predicts only the outer-training person-weighted mean.

| Planned arm | MAE /100 | RMSE /100 | R² | Within ±5 points | Within ±10 points |
|---|---:|---:|---:|---:|---:|
| constant | 7.266 | 9.355 | -0.046 | 43.8% | 74.1% |
| fixed | 4.274 | 5.614 | 0.623 | 67.5% | 92.4% |
| selected | 4.207 | 5.414 | 0.650 | 66.6% | 93.3% |

**All metrics weight people equally. Tolerance percentages are not classification accuracy.**

Relative selected MAE reduction against the fixed reference: 1.6%. The 95% person-bootstrap MAE interval is 3.359–5.235. The paired selected-minus-fixed MAE interval is -0.336–0.208; negative differences favor the new procedure. These intervals condition on the frozen outer predictions.

Predeclared research gate (≥10% improvement, MAE ≤4, R² ≥0.5): **not reached**.

| Outer fold | Inner-selected configuration(s) |
|---|---|
| 1 | `recovery_context:cat_rmse5` |
| 2 | `recovery_context:cat_rmse5` |
| 3 | `recovery_context:cat_rmse3` |
| 4 | `recovery_context:cat_mae4`, `recovery_context:cat_rmse3`, `recovery_context:cat_rmse5` |

## Source timing audit and sensitivity

The independent source audit found 9 reversed sleep intervals among 2796 source sleep records from these development participants. 2 occur among the 2788 scored daily rows. Each reversed interval differs from its published duration by exactly one day. Neither endpoint was shifted or repaired. Both affected scored rows have missing raw overnight heart trajectories and retain their published aggregate sleep measurements. The other scored intervals match their published durations exactly.

A post-hoc sensitivity check excludes those 2 scored rows and recomputes aggregate metrics on 2786 rows from 14 people, using exactly the same saved predictions. Models, training data and selection are unchanged:

| Same predictions, affected scored rows excluded | MAE /100 | R² | Within ±10 points |
|---|---:|---:|---:|
| constant | 7.265 | -0.046 | 74.1% |
| fixed | 4.271 | 0.624 | 92.4% |
| selected | 4.207 | 0.650 | 93.3% |

This sensitivity does not repair physiological histories or remove invalid training rows. Invalid source records may also contribute to later physiological histories. It therefore does not establish a fully corrected timing pipeline. The original frozen results remain the primary report.

Detailed source checks and independently recomputed metrics are recorded locally in ignored `results/readiness-refinement-v1/source-timing-independent-audit.json`; no individual records are published here.

Final development-only fit: `recovery_context:cat_rmse5`, `recovery_context:hgb15`, `recovery_context:cat_rmse3`. This artifact is saved for reproducibility, not selected by its outer score or evaluated again on the old test cohort. All artifacts carry `production_enabled=False`.

Reproduce from the engine directory after experiment016 data preparation:

```sh
.venv/bin/python scripts/run_readiness_refinement.py prepare
.venv/bin/python scripts/run_readiness_refinement.py run
.venv/bin/python scripts/run_readiness_refinement.py verify
.venv/bin/python scripts/audit_readiness_refinement.py --require-results
.venv/bin/python scripts/report_readiness_refinement.py
```

The immutable protocol records source, code and prepared-data hashes. Verification replays every outer artifact, checks excluded people, independently recomputes metrics and outer-training constants, and recomputes every inner candidate MAE. Raw data, participant predictions and fitted weights stay ignored.
