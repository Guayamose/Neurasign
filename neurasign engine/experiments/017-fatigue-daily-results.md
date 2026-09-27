# Experiment 017: daily fatigue from an independent wearable dataset

**Offline daily-fatigue research. No production integration or instantaneous fatigue claim.**

Sources: [Luo/De Luca public dataset](https://zenodo.org/records/4266157) and [original paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC7768149/). All 29 downloaded files match publisher checksums; local SHA256 manifests are retained. Dataset license: CC BY 4.0. The device is a Biovotion Everion worn on the upper arm, rather than a validated wrist-device transfer.

Targets stay distinct: overall fatigue VAS 1–10 and physical/mental exhaustion frequency encoded Never 1, Sometimes 2, Regularly 3, Often 4, Always 5. No sleepiness, stress, readiness or workload labels are invented. Simultaneous conflicting answers are excluded; latest daily responses are used.

Primary track uses the previous calendar day of wearable readings. Sensor timezone is undocumented while questionnaire timezone varies between UTC/CET/CEST; previous-day features avoid using the full outcome day. The secondary same-day track is explicitly retrospective: some readings can occur after the questionnaire. Neither track establishes within-minute fatigue detection.

Sensors: HR, device HRV, respiration, blood perfusion/pulse-wave summaries, skin conductance, skin temperature, activity counts, energy expenditure and steps. Barometer, identity, calendar, timezone and every other questionnaire are excluded as predictors. Each day requires 288 minutes with HR or activity; a channel requires 30 finite minutes. The history profile uses only preceding seven-calendar-day unlabeled sensor medians. No global imputation or future-baseline normalization.

People: 21 development, 6 untouched test. Four person-disjoint development folds compare 33 configurations per target/track (ridge, RBF SVR, ExtraTrees, CatBoost; physiological/all wearable/history profiles). Person-balanced MAE selects all six configurations before any test evaluation. Targets are never predictors for another target.

Test people: S19, S20, S23, S27, S28, S9.

| Track | Target / scale | Days / people | Selected MAE | Constant MAE | Within tolerance | Tolerance | Weighted R² |
|---|---|---:|---:|---:|---:|---:|---:|
| previous_day | vas / [1, 10] | 117 / 6 | 2.309 | 2.318 | 24.4% | ±1 | -0.450 |
| previous_day | physical / [1, 5] | 117 / 6 | 0.711 | 0.681 | 37.5% | ±0.5 | -0.006 |
| previous_day | mental / [1, 5] | 117 / 6 | 0.633 | 0.611 | 41.1% | ±0.5 | -0.035 |
| same_day_retrospective | vas / [1, 10] | 121 / 6 | 2.582 | 2.532 | 17.7% | ±1 | -0.615 |
| same_day_retrospective | physical / [1, 5] | 121 / 6 | 0.741 | 0.723 | 34.1% | ±0.5 | -0.011 |
| same_day_retrospective | mental / [1, 5] | 121 / 6 | 0.646 | 0.647 | 39.6% | ±0.5 | -0.031 |

**Within-tolerance percentages are regression agreement, not classification accuracy or confidence.** VAS tolerance is one original scale point; frequency tolerance is half a category. MAE is reported in original units, not converted into a fabricated percentage accuracy. The constant predicts the development-person-weighted median. Full fixed-reference results, person-bootstrap intervals, all 198 development comparisons and 12 saved artifact audits are retained in the ignored results directory.

Research gate requires at least 20% test MAE reduction against the constant and positive weighted R². Results:

- previous_day / vas: not reached; MAE improvement 0.4%; MAE 95% person-bootstrap interval 1.252–3.521.
- previous_day / physical: not reached; MAE improvement -4.3%; MAE 95% person-bootstrap interval 0.628–0.795.
- previous_day / mental: not reached; MAE improvement -3.6%; MAE 95% person-bootstrap interval 0.488–0.772.
- same_day_retrospective / vas: not reached; MAE improvement -2.0%; MAE 95% person-bootstrap interval 1.658–3.659.
- same_day_retrospective / physical: not reached; MAE improvement -2.5%; MAE 95% person-bootstrap interval 0.614–0.863.
- same_day_retrospective / mental: not reached; MAE improvement 0.1%; MAE 95% person-bootstrap interval 0.491–0.779.

No test-based selection or retuning. Small numbers of people and changing data coverage limit transportability. Daily questionnaire labels and session CFS labels from MEFAR are not pooled as equivalent outcomes.

Reproduce: `.venv/bin/python scripts/run_fatigue_daily.py prepare`, then `run`; use `verify` after completion.
