# Experiment 018: DailySense observed daily fatigue

**Daily questionnaire prediction from preceding wrist signals. No instantaneous-state or production claim.**

Source: [DailySense, Hitachi public release](https://zenodo.org/records/10816004), CC BY 4.0. The source study contains 36 people in two separate cohorts monitored for 14 days. The target is the original `drm_vas1` fatigue VAS, from 0 (none) to 100 (worst). The regression preserves that scale; classification uses the fixed research midpoint ≥50 versus <50, without removing middle ratings. This is not a clinical cutoff.

The scheduled survey cutoff is 21:30 Asia/Tokyo on `SignalDate`. Delayed completion does not allow next-day signals into an earlier label. Each row represents one original daily answer. Inputs summarize preceding HR, native IBI, BVP, EDA, skin temperature and acceleration; profiles compare cardiac daily summaries, autonomic daily summaries, daily plus last-hour summaries, and deviations from strictly earlier seven-day sensor histories. No target history or other questionnaire enters the model.

Both complete outer ZIPs match publisher MD5. Many nested archives contain damaged compressed channels: independent fresh range retrieval reproduced the problem. Each inner CSV must pass its own size/CRC verification before parsing. Damaged channels remain missing; healthy channels are retained. Day inclusion requires at least 60 minutes with three verified channels, including cardiac and autonomic evidence, and at least five paired days per person. Detailed exclusions and source hashes are retained in the ignored preparation audit. Of 579 source recordings, 578 were cached and one malformed recording was excluded. Among cached recordings, 431 BVP streams and 178 acceleration streams failed verification; each of HR, EDA, temperature and IBI remained valid in at least 558 recordings.

The retained cohort contains 36 people and 453 daily answers. 28 people / 357 days are used for development; 8 reserved people / 96 days are scored once. Both targets use the same person split. Four person-disjoint development folds compare 40 profile/algorithm configurations per target plus one top-three ensemble. Imputation, scaling and fitting are confined to the training folds. All evaluation metrics give each person equal weight.

| Classifier | Person-weighted accuracy | Balanced accuracy | Low recall | High-fatigue recall |
|---|---:|---:|---:|---:|
| selected | 54.8% | 60.6% | 78.2% | 43.0% |
| baseline | 66.6% | 50.0% | 0.0% | 100.0% |

Test references: 26 low and 70 high. Selected confusion counts: true low 19, false high 7, false low 39, true high 31. Raw unweighted accuracy is 52.1% (50/96); the table gives each person equal weight. The selected classifier is `cardiac_day:extra5`. Within-person balanced accuracy is 53.2% among 6 test people with both classes.

| Regressor | MAE /100 | RMSE /100 | R² | Within ±5 points | Within ±10 points |
|---|---:|---:|---:|---:|---:|
| selected | 20.89 | 25.32 | -0.208 | 13.7% | 24.4% |
| baseline | 20.14 | 23.32 | -0.024 | 10.1% | 21.4% |

The selected regressor is `autonomic_day:svm10, day_last_hour:cat5, day_last_hour:svm10`. **Regression tolerance agreement is not classification accuracy or calibrated confidence.**

Person-bootstrap 95% intervals: balanced accuracy 46.1%–72.0%; regression MAE 15.45–26.54 points.

Predefined classification gate (balanced accuracy ≥80%, both recalls ≥70%): **not reached**. Regression gate (MAE ≤8, ≥20% improvement over the training-mean constant, R² ≥0.25): **not reached**.

A small reserved cohort, daily retrospective labels, source signal damage and a single wrist-device family limit interpretation. This evaluation does not validate second-by-second fatigue, new wearable brands or fitness for duty.

Reproduce: install `requirements-fatigue.txt`; run `scripts/download_dailysense.py`, `scripts/prepare_dailysense.py cache`, then `scripts/run_dailysense.py prepare` and `run`. Use `scripts/run_dailysense.py verify` to replay completed artifacts without reopening selection. The trained artifacts are in ignored `models/dailysense-classification-v1/` and `models/dailysense-regression-v1/`; both carry `production_enabled=False`.
