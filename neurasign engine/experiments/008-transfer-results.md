# Experiment 008: multi-dataset transfer and stronger models

**Decision: no output met the registered MVP research gate. No interpretation model was enabled in the product.**

This round trained conventional regressors, CatBoost, a masked multi-output neural network, and an external-signal feature autoencoder. It tested native beat intervals, modality subsets, strictly preceding personal references, joint training across two wrist-device studies, and direct three-level classification. All results below come from actual local fits and saved predictions. Jev was already tested in [experiment 006](006-jev-results.md); this round makes no new Jev calls.

The sweep contains **680 target/configuration comparisons** (914 source-specific rows), including repeated control configurations across experiments. There are eight conventional regression configurations, two constant controls, ten multi-output network configurations, 72 coarse-classification comparisons, and a separate nested MAUS probe. Counts of configurations are not counts of independent models or people.

## Fresh held-out wrist study

Ten Mobile CogLoad user codes were reserved before modeling. One has no released questionnaire, leaving **9 scored codes, 27 tasks and 257 windows**. The 26 development codes were used for model selection. Final choices and model files were frozen before the reserved labels were scored. No tuning followed this test.

Agreement means a prediction within **±10 points** of a questionnaire rating on a 0–100 scale. It is not the probability that a live physiological interpretation is correct. Each person contributes equally, and each task within a person contributes equally.

| Output | Learned agreement ±10 | Constant agreement ±10 | Learned MAE /100 | Constant MAE /100 | MAE improvement, paired 95% CI | Pass |
|---|---:|---:|---:|---:|---:|---|
| Mental demand | 28.6% | 33.3% | 24.70 | 24.63 | -0.08 [-0.32, +0.15] | No |
| Physical demand | 48.3% | 63.0% | 18.85 | 19.26 | +0.41 [-2.08, +3.14] | No |
| Time pressure | 12.5% | 14.8% | 27.62 | 27.08 | -0.54 [-2.95, +1.85] | No |
| Self-rated performance | 30.1% | 37.0% | 21.67 | 23.33 | +1.66 [-0.08, +3.60] | No |
| Effort | 17.8% | 7.4% | 29.26 | 30.37 | +1.11 [-4.79, +6.49] | No |

Positive MAE improvement favors the learned model. Confidence intervals resample whole user codes 10,000 times; they do not treat overlapping windows as independent. They are descriptive per output and not adjusted for multiple comparisons. Constants are selected using development data only. A constant can have high agreement when ratings cluster, without reading physiological signals.

| Output | Selected continuous candidate | Separate low/middle/high balanced accuracy |
|---|---|---:|
| Mental demand | `local__summary__ridge1000` | 25.1% |
| Physical demand | `pooled__summary__cat6` | 19.3% |
| Time pressure | `pooled__summary_history__ridge1000` | 49.2% |
| Self-rated performance | `local__summary_history__ridge100` | 49.1% |
| Effort | `pooled__summary_history__cat6` | 46.9% |

The coarse classifier is selected separately. Its fixed cut points are 33⅓ and 66⅔; balanced accuracy averages recall across true classes. A three-class chance reference is 33⅓%. This experiment does not change the continuous-rating acceptance criterion after seeing results.

Signal-window coverage among recordings with questionnaire files was 100.0%. The missing questionnaire is not counted as a successful interpretation or silently assigned a target.

## Development results on UNIVERSE

These are the best **development selection scores after a broad search**, not a new independent accuracy claim. The original five test participants remained excluded throughout. Mental effort uses exact rounded-level agreement on its separate 1–5 scale. Other rows use ±10-point agreement.

| Output | Best learned MAE | Best constant MAE | Learned agreement | Constant agreement | Selected learned comparison |
|---|---:|---:|---:|---:|---|
| Mental effort (1–5) | 0.857 | 0.838 | 37.0% | 43.5% | `universe/local__ppg_eda__boost_absolute` |
| Mental demand | 23.369 | 23.782 | 29.1% | 36.3% | `pooled/local__summary_history__cat4` |
| Physical demand | 19.436 | 19.414 | 46.9% | 68.5% | `native/local__native__boost_absolute` |
| Time pressure | 25.839 | 27.449 | 19.1% | 20.3% | `universe/local__all_history__ridge100` |
| Self-rated performance | 20.319 | 20.186 | 30.6% | 38.8% | `universe/local__all_history__ridge1000` |
| Effort | 20.200 | 20.547 | 32.2% | 38.5% | `universe/local__all_history__boost_absolute` |

## What the added data contributed

| Source | Actual use | Limitation |
|---|---|---|
| UNIVERSE | 19 development people; 41,069 causal windows, 472 labeled tasks; six questionnaire targets | Ratings describe tasks/intervals, not momentary truth; original five test people untouched |
| Mobile CogLoad / Snake | 26 development user codes, 78 tasks, 722 windows; joint training of four demand/effort dimensions; nine labeled reserved codes | Export has 36 codes while paper reports 23 people; source identity reconciliation unresolved; one reserved code has no labels |
| CLACIR | 5,727 nonoverlapping minute windows from 142 wrist recording groups, unlabeled pretraining | 140 metadata people plus two unmatched recording IDs (experiment 1/050 and experiment 2/140); no duplicate raw BVP hashes; no NASA-TLX ratings pooled |
| CogWear | 336 nonoverlapping minute windows from 24 participant namespaces; unlabeled pretraining | No compatible questionnaire targets pooled; published CSV checksums verified |
| MAUS | Author-public wrist PPG table: 342 rows, 13 features, 19 subject groups | Raw files require IEEE login; protocol classification only |
| CognitiveLoad_Wearables | All 60 raw/timing archive files acquired for 15 people; withheld from fitting | Timing spreadsheets contain no task NASA-TLX answers; demographics file does not supply them |
| WAUC | Source/access reviewed | Direct raw and rating downloads return HTTP 403; available author GitHub sample covers one person |
| MOCAS | Source/access reviewed | Publisher confirms signed EULA and approved researcher access are required; no request sent |
| SWELL | Prior benchmark retained in experiment 005 | Chest ECG/finger EDA; native units and target scales were not silently merged into wrist training |

Primary sources: [Mobile repository](https://gitlab.fri.uni-lj.si/lrk/mobile-cogload-dataset), [original Mobile thesis](https://repozitorij.uni-lj.si/IzpisGradiva.php?id=110571), [CLACIR](https://github.com/unl-cchil/clacir_dataset), [CogWear](https://physionet.org/content/consumer-grade-wearables/1.0.0/), [MAUS author code](https://github.com/rickwu11/MAUS_dataset_baseline_system), [CognitiveLoad release](https://zenodo.org/records/20815030), [WAUC](https://musaelab.ca/wauc-dataset/), [MOCAS access terms](https://zenodo.org/records/7023242).

An additional [n-back/music release](https://physionet.org/content/multimodal-nback-music/1.0.0/) was screened. It explicitly lacks subject cognitive-state scores and only includes five usable participants. It was not downloaded as another supposedly labeled training source.

## Methods and findings

- Trailing 60-second evidence windows, normally updated every 10 seconds. No participant, task, condition, game score, taps, EEG, personality, affect or frustration predictors. Missing channels remain missing and are imputed within training folds only; labels are never fabricated.
- Equal source weighting for pooled fits, then equal people and tasks. At most 20 training windows per task; all eligible validation windows are scored. Five disjoint user folds per source. No random splitting of neighboring windows.
- Ridge (two regularization strengths), SVR, squared/absolute histogram boosting, CatBoost (depth 4/6), and Extra Trees. Profiles cover pulse, EDA, summary measurements, all signals and preceding personal differences. The reference is initial physiology, not assumed resting physiology.
- A 64→32→6 neural regressor learns all available targets jointly with masked missing labels; fixed 80 epochs, two losses, source-specific training. It uses engineered causal features, not raw waveform deep learning.
- The denoising feature autoencoder learned a 16-dimensional representation from 4953 external training windows; 1110 separate recording-group windows checked reconstruction. The source pool spans 101.05 nonoverlapping hours. It sees no supervised/test labels. Better signal reconstruction did not establish better questionnaire interpretation.
- Native E4 beat intervals were joined only after matching three distant raw BVP blocks. 39,114 of 41,069 windows were aligned; 6,014 (14.6%) passed native-interval quality checks. Gaps remain gaps; differences never bridge missing beats. These are manufacturer PPG intervals, not ECG ground truth.
- Microsoft Band resistance in kΩ is converted to conductance in µS using 1000/R. Native event RR files are used, never the repeated last-value RR column. Four NASA-TLX sliders are linearly mapped 0–20→0–100 using the source instrument/export; measurement equivalence remains an assumption. Self-rated performance stays source-specific.
- Direct low/middle/high classifiers use class-balanced training and fixed thresholds. They are evaluated separately from numeric ratings.

The MAUS nested probe achieved **56.4% ordinary accuracy and 55.9% balanced accuracy**; its majority constant achieved 66.7% and 50.0%, respectively. Outer evaluation leaves one subject out; three inner person folds select among seven configurations. The authors’ future-aware whole-subject normalization was not reused. These labels encode experimental N-back conditions, not a real-time mental-state diagnosis or an MVP pass.

## Acceptance, limits and next evidence

The gate was specified before new outcome scoring: at least 15% MAE reduction over the selected constant, a positive lower paired-bootstrap improvement bound, at least 60% three-level balanced accuracy, at least 60% ±10-point agreement, at least 80% coverage, and at least ten held-out people. No output passed. Nine labeled held-out codes also fail the minimum evaluation-size criterion independently of performance. The criterion was not lowered after testing.

The evidence does not show that physiological inference is impossible or that every possible architecture has been exhausted. It shows that this completed battery, the accessible labels and these generalization tests do not justify a dependable general-purpose live interpreter. More unlabeled hours do not supply missing target truth. Access to restricted compatible sources and a genuinely independent target-domain dataset are the next material dependencies; repeated tuning on this test would not provide new validation.

The product can continue displaying measured signals and explicitly observed trends. These research models should not supply authoritative fatigue, productivity, concentration or employee-ranking claims. Physical demand is not fatigue; subjective performance is not productivity. No dashboard or phone behavior was changed in this round.

## Artifacts and verification

All 41 engine tests passed. Independent verification recalculated 1828 development metrics across 680 prediction files, plus all held-out rating scores and paired confidence intervals. Model, prediction, split and input hashes passed. The verification command does not refit models or choose new winners.

- Plan: [008-transfer-protocol.json](008-transfer-protocol.json); [acquisition amendment](008-protocol-amendment.md); [frozen selection](008-final-selection.json).
- Full local results and predictions: `results/transfer-v1/`; complete comparison: `final/development-comparison.csv`; final test: `final/test-report.json`; independent audit: `verification.json`.
- Frozen experimental weights: `models/transfer-v1/`. They are research artifacts with `production_enabled=False`, not a deployed model service.
- Data, credentials, logs, weights and participant-level predictions remain ignored by Git. Source licenses/access conditions remain attached to each dataset; public availability is not a blanket production-use clearance.

From the engine directory, the completed run can be inspected without rerunning its held-out evaluation:

```bash
.venv/bin/python scripts/verify_transfer.py
.venv/bin/python scripts/report_transfer.py
```

Research preparation/training commands and dependencies are listed in the engine README. Do not overwrite the frozen run or reuse the final holdout to tune another configuration.
