# Experiment 011: one second versus sixty seconds of sensor evidence

**Lab1 fitting and selection; the same Lab2 observations in all comparisons. Development research only.**

This experiment changes the amount of evidence consumed per prediction, not the output cadence. The matched profiles use exactly the same 23 statistics of BVP, EDA, skin temperature and acceleration over [end−1, end) or [end−60, end). They use no history, HRV, vendor heart rate, or filter state from outside the window. Predictions remain at the original ten-second endpoints to hold rows and fitting volume fixed. The historical 60-second, 28-feature profile is an additional control; its feature set also changes, so it cannot isolate duration.

Vendor heart rate is excluded from both matched profiles because [Empatica documents ten-second averaging](https://www.empatica.com/blog/decoding-wearable-sensor-signals-what-to-expect-from-your-e4-data/). One timestamped HR output would otherwise import evidence older than one second.

## Population and label coverage

| Target | Paired people | Adequately calibrated | Scored Lab2 windows / all available | Coverage within paired people |
|---|---:|---:|---:|---:|
| mental_demand | 17 | 12 | 6,708 / 8,412 | 79.7% |
| mental_effort | 2 | 1 | 936 / 8,412 | 94.5% |

Both matched feature tables retain 13,900 union rows across 253 tasks. Across their 23 features, observed availability ranges from 100.0% to 100.0%; per-feature counts are in `feature-availability.csv`. These counts describe the matched, previously eligible rows, not all raw sensor time.

Mental demand uses questionnaire ≤33⅓ versus ≥66⅔; mental effort uses ratings 1–2 versus 4–5. Neutral and missing ratings remain excluded. Mental effort has only two paired people and cannot support a population conclusion. No new model is selected from Lab2 results.

## All paired people

Accuracy weights people equally and tasks equally within people. Within-person balanced accuracy averages low/high recall within each person before averaging people with both classes. Low/high recall columns use the aggregate person/task weights; their average can differ from the within-person balanced measure.

### mental_demand

| Profile | Arm | Accuracy | Within-person balanced accuracy | Low recall | High recall |
|---|---|---:|---:|---:|---:|
| short1 | generic_constant | 69.2% | 50.0% | 0.0% | 100.0% |
| short1 | personal_constant | 68.1% | 50.0% | 36.4% | 82.2% |
| short1 | generic_fixed | 48.4% | 49.8% | 45.3% | 49.7% |
| short1 | personal_fixed | 53.9% | 51.2% | 41.1% | 59.7% |
| short1 | hybrid_fixed | 47.2% | 49.0% | 41.5% | 49.7% |
| short1 | generic_selected | 51.2% | 48.9% | 43.6% | 54.6% |
| short1 | personal_selected | 54.2% | 52.5% | 44.1% | 58.7% |
| short1 | hybrid_selected | 47.1% | 47.8% | 40.4% | 50.0% |
| short60 | generic_constant | 69.2% | 50.0% | 0.0% | 100.0% |
| short60 | personal_constant | 68.1% | 50.0% | 36.4% | 82.2% |
| short60 | generic_fixed | 51.7% | 52.9% | 48.1% | 53.3% |
| short60 | personal_fixed | 57.3% | 56.0% | 57.0% | 57.4% |
| short60 | hybrid_fixed | 52.8% | 56.4% | 51.4% | 53.4% |
| short60 | generic_selected | 51.9% | 53.1% | 48.7% | 53.4% |
| short60 | personal_selected | 57.6% | 55.3% | 52.9% | 59.7% |
| short60 | hybrid_selected | 52.3% | 55.1% | 54.4% | 51.3% |
| legacy60 | generic_constant | 69.2% | 50.0% | 0.0% | 100.0% |
| legacy60 | personal_constant | 68.1% | 50.0% | 36.4% | 82.2% |
| legacy60 | generic_fixed | 51.4% | 52.6% | 47.5% | 53.1% |
| legacy60 | personal_fixed | 59.2% | 57.1% | 54.6% | 61.3% |
| legacy60 | hybrid_fixed | 54.5% | 56.5% | 49.4% | 56.8% |
| legacy60 | generic_selected | 50.1% | 51.3% | 47.7% | 51.1% |
| legacy60 | personal_selected | 62.9% | 58.0% | 56.5% | 65.7% |
| legacy60 | hybrid_selected | 55.2% | 56.7% | 52.4% | 56.5% |

| Arm | One second minus sixty seconds, points [95% interval] | Paired people with both classes |
|---|---:|---:|
| generic_fixed | -3.1 [-5.5, -1.2] | 17 |
| personal_fixed | -4.8 [-9.5, -1.0] | 17 |
| hybrid_fixed | -7.4 [-12.4, -3.5] | 17 |
| generic_selected | -4.2 [-6.8, -1.9] | 17 |
| personal_selected | -2.9 [-7.6, +1.5] | 17 |
| hybrid_selected | -7.2 [-13.4, -1.6] | 17 |

### mental_effort

| Profile | Arm | Accuracy | Within-person balanced accuracy | Low recall | High recall |
|---|---|---:|---:|---:|---:|
| short1 | generic_constant | 88.2% | 50.0% | 0.0% | 100.0% |
| short1 | personal_constant | 88.2% | 50.0% | 0.0% | 100.0% |
| short1 | generic_fixed | 25.5% | 56.1% | 96.6% | 16.0% |
| short1 | personal_fixed | 32.3% | 55.8% | 85.7% | 25.2% |
| short1 | hybrid_fixed | 18.1% | 53.6% | 100.0% | 7.1% |
| short1 | generic_selected | 25.5% | 56.1% | 96.6% | 16.0% |
| short1 | personal_selected | 32.3% | 55.8% | 85.7% | 25.2% |
| short1 | hybrid_selected | 18.1% | 53.6% | 100.0% | 7.1% |
| short60 | generic_constant | 88.2% | 50.0% | 0.0% | 100.0% |
| short60 | personal_constant | 88.2% | 50.0% | 0.0% | 100.0% |
| short60 | generic_fixed | 47.2% | 52.0% | 61.5% | 45.3% |
| short60 | personal_fixed | 53.5% | 65.1% | 78.8% | 50.1% |
| short60 | hybrid_fixed | 25.8% | 57.9% | 100.0% | 15.9% |
| short60 | generic_selected | 47.2% | 52.0% | 61.5% | 45.3% |
| short60 | personal_selected | 42.6% | 59.0% | 78.8% | 37.7% |
| short60 | hybrid_selected | 25.8% | 57.9% | 100.0% | 15.9% |
| legacy60 | generic_constant | 88.2% | 50.0% | 0.0% | 100.0% |
| legacy60 | personal_constant | 88.2% | 50.0% | 0.0% | 100.0% |
| legacy60 | generic_fixed | 76.8% | 51.8% | 19.1% | 84.6% |
| legacy60 | personal_fixed | 62.3% | 61.0% | 58.9% | 62.7% |
| legacy60 | hybrid_fixed | 24.0% | 57.0% | 100.0% | 13.8% |
| legacy60 | generic_selected | 76.8% | 51.8% | 19.1% | 84.6% |
| legacy60 | personal_selected | 52.6% | 63.1% | 75.2% | 49.6% |
| legacy60 | hybrid_selected | 24.0% | 57.0% | 100.0% | 13.8% |

| Arm | One second minus sixty seconds, points [95% interval] | Paired people with both classes |
|---|---:|---:|
| generic_fixed | +4.1 [-3.2, +11.4] | 2 |
| personal_fixed | -9.3 [-9.6, -9.0] | 2 |
| hybrid_fixed | -4.4 [-8.6, -0.1] | 2 |
| generic_selected | +4.1 [-3.2, +11.4] | 2 |
| personal_selected | -3.2 [-9.0, +2.6] | 2 |
| hybrid_selected | -4.4 [-8.6, -0.1] | 2 |

## Prespecified subgroup checks

These subsets reuse saved predictions without refitting. Adequate calibration requires two Lab1 tasks per class. Active-only excludes the relaxation video. Counts explicitly show people retaining both Lab2 classes.

| Target | Group | Arm | People (both classes) | 1s balanced | 60s balanced | Difference, points [95% interval] |
|---|---|---|---:|---:|---:|---:|
| mental_demand | adequate_calibration | generic_fixed | 12 (12) | 49.5% | 52.6% | -3.1 [-6.2, -0.7] |
| mental_demand | adequate_calibration | personal_fixed | 12 (12) | 50.7% | 56.7% | -6.0 [-12.0, -1.0] |
| mental_demand | adequate_calibration | hybrid_fixed | 12 (12) | 48.9% | 57.5% | -8.6 [-15.1, -3.6] |
| mental_demand | adequate_calibration | generic_selected | 12 (12) | 48.6% | 52.9% | -4.3 [-7.5, -1.6] |
| mental_demand | adequate_calibration | personal_selected | 12 (12) | 52.5% | 55.7% | -3.2 [-9.9, +2.7] |
| mental_demand | adequate_calibration | hybrid_selected | 12 (12) | 45.5% | 55.6% | -10.2 [-17.6, -3.5] |
| mental_demand | active_tasks_only | generic_fixed | 17 (13) | 51.2% | 52.3% | -1.1 [-5.1, +2.3] |
| mental_demand | active_tasks_only | personal_fixed | 17 (13) | 50.8% | 50.6% | +0.3 [-2.4, +3.0] |
| mental_demand | active_tasks_only | hybrid_fixed | 17 (13) | 50.3% | 51.4% | -1.1 [-3.5, +1.1] |
| mental_demand | active_tasks_only | generic_selected | 17 (13) | 51.1% | 52.6% | -1.5 [-5.8, +2.5] |
| mental_demand | active_tasks_only | personal_selected | 17 (13) | 51.6% | 50.4% | +1.3 [-3.9, +5.6] |
| mental_demand | active_tasks_only | hybrid_selected | 17 (13) | 50.5% | 51.9% | -1.4 [-6.0, +2.5] |
| mental_effort | adequate_calibration | generic_fixed | 1 (1) | 62.1% | 50.7% | +11.4 [+11.4, +11.4] |
| mental_effort | adequate_calibration | personal_fixed | 1 (1) | 53.7% | 63.4% | -9.6 [-9.6, -9.6] |
| mental_effort | adequate_calibration | hybrid_fixed | 1 (1) | 52.0% | 60.6% | -8.6 [-8.6, -8.6] |
| mental_effort | adequate_calibration | generic_selected | 1 (1) | 62.1% | 50.7% | +11.4 [+11.4, +11.4] |
| mental_effort | adequate_calibration | personal_selected | 1 (1) | 53.7% | 51.1% | +2.6 [+2.6, +2.6] |
| mental_effort | adequate_calibration | hybrid_selected | 1 (1) | 52.0% | 60.6% | -8.6 [-8.6, -8.6] |
| mental_effort | active_tasks_only | generic_fixed | 2 (0) | n/a | n/a | n/a |
| mental_effort | active_tasks_only | personal_fixed | 2 (0) | n/a | n/a | n/a |
| mental_effort | active_tasks_only | hybrid_fixed | 2 (0) | n/a | n/a | n/a |
| mental_effort | active_tasks_only | generic_selected | 2 (0) | n/a | n/a | n/a |
| mental_effort | active_tasks_only | personal_selected | 2 (0) | n/a | n/a | n/a |
| mental_effort | active_tasks_only | hybrid_selected | 2 (0) | n/a | n/a | n/a |

## Interpretation and reproducibility

- Fixed arms use logistic regression C=1. Selected arms choose among logistic C=1, RBF SVM C=1, ExtraTrees and CatBoost using Lab1 alone. General selection holds out people; personal selection holds out whole tasks; hybrid uses the general selection. A maximum of 20 rows per training task and the original person/task/class balancing are shared across profiles.
- Bootstrap intervals resample paired people 10,000 times, never individual windows. They are exploratory, uncorrected for multiple comparisons, and do not establish equivalence if they include zero. A selected-model difference also includes the effect of independent Lab1 model selection; fixed arms hold the algorithm constant.
- Task-level questionnaires are not one-second ground truth. The same task families recur across sessions. This experiment cannot establish one-second response latency, change detection, workplace validity, or cross-device performance.
- One second means samples in the released, offline-aligned recording. Sensor transfer functions and the authors’ clock synchronization are not validated here. Rows inherit the earlier 60-second quality/availability screen, so this is a matched-row duration test, not an independent assessment of first-second startup or deployment coverage.
- Labeled Lab1 calibration still spans complete tasks. Shorter inference windows do not establish a one-second onboarding procedure. Lab2 has been used in earlier development experiments; original UNIVERSE held-out people and Mobile test data are not used for fitting or selection.
- No production, phone or dashboard integration is enabled. These artifacts are research models, and scores are not calibrated confidence.

Protocol: [011-short-window-protocol.json](011-short-window-protocol.json). Saved predictions, per-person metrics, duration intervals and CSV/PNG/PDF comparisons are in `results/short-window-v1/`; artifacts are in `models/short-window-v1/`. `verification.json` records independent metric checks and exact saved-artifact prediction replays.
