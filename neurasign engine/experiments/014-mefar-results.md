# Experiment 014: MEFAR observed fatigue from wrist signals

**Offline research only. No production integration, clinical claim or calibrated confidence.**

Sources: [MEFAR v5](https://data.mendeley.com/datasets/z3g26tphnv/5) and [original data paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC10762351/), CC BY 4.0. The raw archive SHA256 matches the publisher. All 46 CFS questionnaire totals were independently recomputed from the 11 marked items and agree with the source summary. Fatigue means CFS ≥12, as defined by this dataset; the scale combines mental and physical fatigue. These are two ratings per person, not independently labeled instantaneous states.

Data: 23 people, 46 sessions, 1458 matched endpoints. Inputs are raw wrist BVP, EDA, temperature, acceleration and device HR only. No EEG, demographics, session/time-of-day or questionnaire values are predictors. The author-normalized and oversampled processed data are excluded. Each causal feature window ends before prediction; signal summaries and pulse variability are computed from the trailing 60 or 180 seconds, at 60-second steps. Pulse variability extracted from moving wrist BVP is exploratory, not ECG-validated HRV.

Eighteen people are used for four person-disjoint development folds; five people are reserved before training and evaluated once. All sessions/windows from a person stay together. The fixed search contains 60 configurations: two window lengths, three signal profiles and ten settings across logistic regression, RBF SVM, ExtraTrees and CatBoost. A top-three score ensemble and seven predefined decision thresholds are compared on development predictions only. Imputation/scaling are fitted on each training fold; training weights balance people, sessions and classes. Evaluation weights people equally, then sessions equally.

Development people: S1, S10, S11, S13, S14, S15, S16, S17, S18, S2, S20, S21, S3, S4, S5, S6, S7, S9. Test people: S12, S19, S22, S23, S8.

Development-selected arm: `w180_autonomic_rbf0.1` at threshold 0.50. Development balanced accuracy: 63.6%. This is a selection score, not an unbiased accuracy claim.

| Untouched test arm | Accuracy | Balanced accuracy | Low recall | Fatigue recall | Within-person balanced |
|---|---:|---:|---:|---:|---:|
| selected | 51.1% | 46.7% | 68.5% | 25.0% | 57.8% |
| fixed | 52.2% | 47.8% | 69.7% | 25.9% | 52.7% |
| majority | 40.0% | 50.0% | 0.0% | 100.0% | 50.0% |
| time_context_only | 70.0% | 70.8% | 66.7% | 75.0% | 75.0% |

Selected test balanced accuracy 95% person-bootstrap interval: 22.2%–69.7%. Only five test people make uncertainty large; repeated windows do not add independent people.

Predeclared gate (balanced accuracy ≥80% and both recalls ≥70%): **not reached**.

The time-context baseline predicts low in the morning and high in the evening; it diagnoses collection confounding and is never a candidate or model input. The fixed logistic reference is reported regardless of whether it beats the development-selected model; final test outcomes must not be used to change the selection. Generalization across devices, workplaces and days is not established. This does not train readiness or workload.

Reproduce: `.venv/bin/python scripts/run_mefar.py prepare`, then `run`; inspect the completed immutable evaluation using `verify`. Full comparisons, frozen selection, source audit, local weights and predictions remain in ignored data/results/models directories.
