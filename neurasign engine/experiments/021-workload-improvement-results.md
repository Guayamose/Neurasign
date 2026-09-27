# Experiment 021: improving overall workload prediction

**Assessment:** The nested development-selected model reduced overall workload error versus the fixed prior algorithm: MAE 13.02 versus 16.04 points on the 0–100 recorded NASA-TLX scale. The training-median baseline scores 16.24. Paired mean error reduction versus the prior is +3.03 points (exploratory 95% interval +2.10 to +3.93). Selected weighted R² is 0.368. These are development results from 19 previously studied people, not untouched-test or workplace validation.

**Material limitation:** The earlier-reference availability perfectly separates the initial relaxation context from active tasks: 19/19 relaxation tasks lack a reference, while 148/148 active tasks have one. All outer winners use this profile, so missingness indicators offer a task-context shortcut; the overall gain cannot be attributed to physiological discrimination alone. On active tasks alone, MAE is 12.97, R² 0.077, and gain over the fixed prior is +1.02 [-0.20, +2.22] points. Active-only extreme-label balanced accuracy is 49.5%. The frozen experiment therefore does not establish a reliable improvement in active-workload discrimination. This descriptive audit does not change features, selection, predictions or cutoffs after scoring.

The separately requested **post-hoc context-only diagnostic** reaches MAE 13.22 using only the relaxation/active context and outer-training medians, with no physiology. The selected model's additional MAE reduction is just +0.20 [-0.66, +1.01] points. This diagnostic is not a wearable model or a new selection candidate.

## What was predicted

The target is the source **Weighted Nasa Score**, the overall subjective NASA-TLX score. Every retained questionnaire total was checked against all 15 recorded pairwise weights and all six recorded ratings, divided by 15, agreeing within 0.011 source rounding. Values and component ratings were checked against 0–100 units. This is a distinct target from the Mental Demand component used in 010/011; their percentages must not be relabeled or directly compared with this experiment.

NASA-TLX combines mental, physical and temporal demand, performance, effort and frustration. The questionnaire fields serve only to verify the overall outcome; none are predictors and no separate emotional-state output is trained. This is anonymous academic research, with the earlier employee-product output exclusions preserved. [NASA instrument definition](https://www.nasa.gov/human-systems-integration-division/nasa-task-load-index-tlx/); [UNIVERSE source study](https://www.nature.com/articles/s41597-024-03738-7).

## Frozen comparison

Only Lab1 of the original development people is used: 167 completed tasks and 9,160 previously eligible 60-second windows. One task contributes one reference score, so overlapping windows cannot inflate the number of labels. The entire task is aggregated before prediction; these are post-task estimates, not instantaneous estimates or an improvement to the one-second experiment. Lab2, the original five UNIVERSE test people and Mobile evaluation records are outside this experiment.

Four outer person folds evaluate the bounded procedure. Three inner person folds select preprocessing, model and ensemble within each outer-training population. All 28 candidates and fold assignments were registered before scoring. The 24 base candidates combine three feature profiles with eight regularized ridge/SVR/tree models; four further candidates average the top three inner-ranked base models globally or within a profile. Selection uses equal-person/equal-task MAE. The winning ensemble members are never chosen using outer outcomes.

Added features include robust temporal task summaries, gap-safe native pulse-interval variability with verified waveform alignment, log transforms, quality/availability indicators and earlier unlabeled personal references. Missing signals are imputed only within training folds. Task names, difficulty, timestamps, person IDs, questionnaire answers, future-task observations and target history are excluded as input columns. The initial-reference missingness shortcut remains, as audited above. The fixed comparator uses the original 28 signal features aggregated as medians and fixed Ridge 100; it is refitted on the identical tasks and folds, rather than reusing any model that has seen evaluation people.

## Continuous-score results

| Population | Model | People / tasks | MAE ↓ | RMSE ↓ | Weighted R² ↑ | Within 10 points |
|---|---|---:|---:|---:|---:|---:|
| all_tasks | constant | 19 / 167 | 16.24 | 20.17 | -0.017 | 40.0% |
| all_tasks | fixed_prior | 19 / 167 | 16.04 | 19.78 | 0.022 | 38.7% |
| all_tasks | selected | 19 / 167 | 13.02 | 15.90 | 0.368 | 42.0% |
| active_tasks_only | constant | 19 / 148 | 13.82 | 16.74 | -0.043 | 45.2% |
| active_tasks_only | fixed_prior | 19 / 148 | 13.99 | 16.96 | -0.071 | 43.1% |
| active_tasks_only | selected | 19 / 148 | 12.97 | 15.75 | 0.077 | 41.4% |

Agreement within 10 points is regression tolerance agreement, not classification accuracy. MAE/RMSE and R² give people equal weight, then divide their weight equally across tasks.

| Population | Comparison | Paired MAE reduction [95% interval] | People improved / worse |
|---|---|---:|---:|
| all_tasks | selected versus constant | +3.23 [+2.23, +4.23] | 17 / 2 |
| all_tasks | selected versus fixed_prior | +3.03 [+2.10, +3.93] | 17 / 2 |
| active_tasks_only | selected versus constant | +0.85 [-0.05, +1.80] | 14 / 5 |
| active_tasks_only | selected versus fixed_prior | +1.02 [-0.20, +2.22] | 12 / 7 |

Intervals use 10,000 paired whole-person resamples. They are exploratory and do not account for overlapping training populations or the broader history of development experimentation. An interval crossing zero does not demonstrate improvement.

## Prespecified low/high description

This secondary description keeps true reference scores ≤33⅓ or ≥66⅔ and excludes the middle; the prediction threshold is fixed at 50. The regression models are neither refitted nor selected for this subset. A high binary percentage is not accuracy at predicting the continuous workload score.

| Population | Model | Low / high / excluded-middle tasks | Coverage | Balanced accuracy | Low recall | High recall | ROC AUC |
|---|---|---:|---:|---:|---:|---:|---:|
| all_tasks | constant | 21 / 61 / 85 | 49.1% | 50.0% | 0.0% | 100.0% | 0.432 |
| all_tasks | fixed_prior | 21 / 61 / 85 | 49.1% | 50.0% | 0.0% | 100.0% | 0.712 |
| all_tasks | selected | 21 / 61 / 85 | 49.1% | 82.7% | 66.5% | 98.9% | 0.899 |
| active_tasks_only | constant | 7 / 61 / 80 | 45.9% | 50.0% | 0.0% | 100.0% | 0.368 |
| active_tasks_only | fixed_prior | 7 / 61 / 80 | 45.9% | 50.0% | 0.0% | 100.0% | 0.621 |
| active_tasks_only | selected | 7 / 61 / 80 | 45.9% | 49.5% | 0.0% | 99.0% | 0.719 |

Active-only excludes relaxation video tasks using the same saved predictions, without refitting or choosing another winner. It checks whether separation survives beyond the deliberately resting context.

## Selection and limitations

| Outer fold | Inner-selected configuration | Inner selection MAE |
|---|---|---:|
| 0 | reference/svr30, reference/ridge100, reference/extra | 12.96 |
| 1 | reference/extra | 13.75 |
| 2 | reference/cat3, reference/svr30, reference/extra | 14.04 |
| 3 | reference/extra | 13.35 |

## Post-hoc context-only diagnostic

After discovering the missing-reference shortcut, a separate descriptive baseline uses recorded task context alone. For each frozen outer fold, it computes the person/task-weighted training target median separately for relaxation and active tasks, then applies the appropriate median to the held people. It uses no physiological value and performs no candidate or threshold selection. **It is not a wearable model, was not a preregistered candidate and does not replace or retune the frozen primary results.** This diagnostic tests how much error reduction can be obtained simply by knowing the experimental context.

| Population | Context-only MAE | Context-only R² | Selected minus context improvement in MAE [95% interval] |
|---|---:|---:|---:|
| all_tasks | 13.22 | 0.352 | +0.20 [-0.66, +1.01] |
| active_tasks_only | 13.54 | -0.006 | +0.57 [-0.27, +1.34] |

Positive improvement means the selected physiological model has lower error than this context-only diagnostic. The paired intervals remain exploratory; the diagnostic was requested after outcome inspection and cannot be presented as a fresh confirmatory comparison.

- Inner selection figures are optimization scores, not independent performance estimates. Outer predictions evaluate the registered selection procedure; no single universal winner is claimed.
- Task-level questionnaire ratings remain subjective and retrospective. Native pulse intervals are not ECG truth; manufacturing filters and source offline clock alignment persist. Personal references are earlier unlabeled physiology, not verified rest.
- All people were already used in earlier development. This nested comparison controls the new search but does not erase prior researcher exposure. A future independent cohort is needed before generalization claims.
- Aggregating complete tasks consumes minutes of evidence, and source eligibility inherits previous 60-second quality screening. This is not a continuous live, one-second, cross-device or workplace validation.
- Research artifacts remain production-disabled; no named employee, phone app or dashboard integration was made.

## Artifacts and reproduction

Protocol: [021-workload-improvement-protocol.json](021-workload-improvement-protocol.json). Data: `data/prepared/workload-improvement-v1/`; predictions, selections, CSV/PNG/PDF results and verification: `results/workload-improvement-v1/`; saved fold models: `models/workload-improvement-v1/`.

```bash
.venv/bin/python scripts/run_workload_improvement.py prepare
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python scripts/run_workload_improvement.py run
.venv/bin/python scripts/run_workload_improvement.py report
.venv/bin/python scripts/run_workload_improvement.py verify
```

Preparation and training refuse to overwrite an existing registered run. Earlier experiments are checked by hashes; no thresholds or candidates are changed after outer evaluation.
