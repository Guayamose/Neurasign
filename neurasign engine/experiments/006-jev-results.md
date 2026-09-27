# Experiment 006: real Jev dataset benchmark

Completed 1,806 real requests to pinned `jev-1.13.0`: two frozen prompt variants across 472 UNIVERSE windows and 431 SWELL minutes. The connectivity probe is excluded. No synthetic responses or local fallbacks were used. No model or heuristic was promoted into the app.

## Reading the numbers

Agreement means **exact rounded level** for UNIVERSE mental effort (1–5), **within ±10 points** for its five 0–100 ratings, and **within ±1 native workbook point** for SWELL. These tolerances are not interchangeable definitions of correctness, and 100 minus MAE is not accuracy. All percentages here give equal weight to people, then questionnaire blocks, then observations. Historical v1/v2 mental-effort percentages have been recomputed with this weighting and can differ from their earlier pooled percentages.

A constant predicts a training-set mean or median without using the current physiology. A learned model is selected from nonconstant candidates using training participants. 'Selected procedure' allows constants to win. Jev zero-shot uses measurements and definitions; eight-shot additionally receives eight labeled windows from eight different training people. This is in-context prompting, not training Jev's weights.

## Interpretation of this run

Both Jev variants have higher mean absolute error than the constant comparator for all six UNIVERSE outputs. Eight examples improve several agreement percentages, but do not establish useful physiological inference. For example, eight-shot time-pressure agreement is 33.98% versus the constant's 14.44%, while its MAE is worse: 33.86 versus 27.61 points. A tolerance percentage alone hides the size of errors outside the tolerance.

In SWELL, eight-shot physical demand is the clearest exploratory improvement: 65.29% within one point and MAE 1.44, versus 53.33% and MAE 1.75 for the constant. The descriptive participant-bootstrap MAE improvement range is approximately 0.02–0.61 points, based on only five people and without adjustment for multiple comparisons. Other outputs and prompt variants are mixed. This is a hypothesis to replicate, not validated general-purpose live interpretation. No prompt was changed after inspecting these results.

## Direct comparison: same observations

### UNIVERSE

One middle available causal window from each of 472 questionnaire intervals, 19 development people. Mental-effort labels exist for 338 windows. Local predictions are the existing out-of-fold v3 predictions at exactly these instants. Entire corresponding outer validation folds were excluded from Jev examples. This is a previously inspected development benchmark, not a fresh final test.

| Method | Mental effort | Mental demand | Physical demand | Time pressure | General effort | Self-rating |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Constant comparator | 37.48% | 27.08% | 68.51% | 14.44% | 36.26% | 34.57% |
| Local selected procedure | 39.86% | 26.91% | 62.18% | 14.86% | 36.26% | 33.46% |
| Local learned procedure | 30.02% | 24.56% | 45.08% | 15.09% | 26.12% | 29.66% |
| Jev: no examples | 16.91% | 17.60% | 53.34% | 27.17% | 17.94% | 24.45% |
| Jev: eight examples | 31.60% | 22.60% | 55.85% | 33.98% | 24.53% | 32.22% |

Mean absolute errors on the original numeric scales:

| Target | Constant | Local learned | Jev: no examples | Jev: eight examples |
| --- | ---: | ---: | ---: | ---: |
| mental effort | 0.8824 | 0.8942 | 1.3942 | 1.0772 |
| mental demand | 24.5028 | 24.1767 | 38.3339 | 31.7593 |
| physical demand | 19.4140 | 19.9533 | 21.4040 | 20.8023 |
| time pressure | 27.6088 | 27.9025 | 29.3349 | 33.8551 |
| recorded self-rated performance | 20.5366 | 20.8781 | 23.7049 | 22.1059 |
| general effort | 20.9596 | 21.3266 | 36.0717 | 28.1871 |

### SWELL

All 431 eligible held-out minutes from 15 blocks and five people. Jev examples come only from the original 20 development people. All current physiological features and available differences from preceding rest are provided. This is a previously inspected test benchmark. Chest ECG and finger EDA, precomputed offline, do not establish transfer to live wrist devices.

| Method | Mental effort | Mental demand | Physical demand | Time pressure | General effort | Self-rating |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Constant comparator | 6.67% | 6.67% | 53.33% | 26.67% | 26.67% | 13.33% |
| Local selected procedure | 16.89% | 5.41% | 53.33% | 26.67% | 26.67% | 13.33% |
| Local learned procedure | 16.89% | 5.41% | 39.99% | 49.91% | 16.77% | 36.83% |
| Local native features | 19.30% | 5.41% | 39.99% | 49.91% | 17.98% | 36.83% |
| Local with prior-rest differences | 16.89% | 11.30% | 46.73% | 41.82% | 16.77% | 25.62% |
| Jev: no examples | 27.92% | 8.16% | 55.12% | 14.65% | 14.85% | 21.11% |
| Jev: eight examples | 19.90% | 4.87% | 65.29% | 26.75% | 22.73% | 21.13% |

Mean absolute errors on the original numeric scales:

| Target | Constant | Local learned | Jev: no examples | Jev: eight examples |
| --- | ---: | ---: | ---: | ---: |
| mental effort | 2.6600 | 2.9174 | 2.5225 | 3.1303 |
| mental demand | 2.4386 | 2.7568 | 2.7327 | 2.7220 |
| physical demand | 1.7533 | 1.9852 | 1.6368 | 1.4378 |
| time pressure | 1.8733 | 1.7502 | 3.2188 | 2.5203 |
| recorded self-rated performance | 2.0778 | 1.9077 | 2.0338 | 2.0502 |
| general effort | 2.0667 | 2.4846 | 2.8944 | 2.4097 |

## Historical experiments: separate evaluation protocols

These rows describe earlier complete evaluations, **not** a fair leaderboard against the sampled UNIVERSE Jev run. V1 uses five original test people and offline feature processing; v2 uses nested folds of 19 development people and complete-task summaries; v3 uses individual causal windows from those 19 development people. V1/v2 average predictions across tasks before scoring; v3 scores each window before averaging errors.

| Method | Mental effort | Mental demand | Physical demand | Time pressure | General effort | Self-rating |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| V1: published offline features (Ridge / boosting) | 37.58% | 24.24% | 33.43% | 13.85% | 16.65% | 14.69% |
| V2: full-task tuning, selected procedure | 40.58% | 24.69% | 64.21% | 18.81% | 32.74% | 30.06% |
| V2: constant comparator | 37.64% | 27.40% | 69.01% | 14.36% | 36.41% | 34.49% |
| V3: all windows, selected procedure | 40.11% | 27.43% | 61.62% | 15.53% | 36.26% | 33.44% |
| V3: all windows, learned procedure | 29.61% | 24.17% | 44.71% | 15.63% | 27.21% | 29.40% |
| V3: all windows, constant comparator | 37.48% | 27.08% | 68.51% | 14.44% | 36.26% | 34.57% |

### All information-audit variants

Fixed Ridge/boosting diagnostic models, five participant folds, all v3 validation windows. Variants were diagnostic comparisons, not independently validated winners. Native IBI was inventoried only; it has no trained-model score.

| Method | Mental effort | Mental demand | Physical demand | Time pressure | General effort | Self-rating |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| all_training_windows/boost_squared_7 | 26.98% | 22.27% | 34.24% | 17.19% | 26.01% | 29.38% |
| all_training_windows/ridge_100 | 29.32% | 23.35% | 30.56% | 16.02% | 26.54% | 29.43% |
| relax_motion/boost_squared_7 | 26.90% | 21.60% | 33.84% | 16.58% | 25.76% | 30.00% |
| relax_motion/ridge_100 | 29.51% | 23.04% | 30.09% | 16.29% | 26.49% | 29.26% |
| relax_motion_periodicity/boost_squared_7 | 27.86% | 22.49% | 34.05% | 16.63% | 25.38% | 30.26% |
| relax_motion_periodicity/ridge_100 | 29.13% | 23.12% | 29.35% | 16.26% | 27.11% | 29.00% |
| v3_gates/boost_squared_7 | 28.65% | 21.18% | 33.58% | 17.45% | 26.17% | 29.34% |
| v3_gates/constant_mean | 24.56% | 22.22% | 18.69% | 15.00% | 29.04% | 30.34% |
| v3_gates/constant_median | 43.46% | 33.83% | 68.51% | 19.40% | 38.62% | 38.84% |
| v3_gates/ridge_100 | 29.96% | 23.50% | 30.71% | 16.13% | 26.47% | 29.30% |
| without_device_hr/boost_squared_7 | 27.80% | 21.40% | 33.61% | 16.94% | 26.62% | 29.09% |
| without_device_hr/ridge_100 | 29.76% | 23.02% | 30.13% | 16.01% | 25.66% | 29.63% |
| without_eda/boost_squared_7 | 29.55% | 23.36% | 34.44% | 16.64% | 26.38% | 29.76% |
| without_eda/ridge_100 | 29.29% | 23.74% | 30.33% | 16.05% | 27.60% | 29.52% |
| without_motion/boost_squared_7 | 29.29% | 22.29% | 28.00% | 16.46% | 26.03% | 29.42% |
| without_motion/ridge_100 | 29.14% | 22.83% | 26.31% | 15.41% | 26.99% | 28.76% |
| without_pulse_intervals/boost_squared_7 | 28.54% | 21.88% | 34.40% | 16.49% | 26.17% | 29.58% |
| without_pulse_intervals/ridge_100 | 28.03% | 23.61% | 28.22% | 15.84% | 27.17% | 29.42% |
| without_pulse_wave/boost_squared_7 | 30.96% | 22.24% | 34.14% | 17.63% | 26.17% | 29.49% |
| without_pulse_wave/ridge_100 | 29.70% | 24.08% | 26.36% | 15.19% | 27.69% | 29.13% |
| without_temperature/boost_squared_7 | 32.56% | 21.69% | 34.47% | 16.40% | 26.28% | 29.72% |
| without_temperature/ridge_100 | 32.09% | 22.79% | 30.85% | 16.45% | 26.16% | 30.60% |

## Method inventory

- V1: Ridge and histogram gradient boosting against a mean constant.
- V2: 18 configurations across mean/median constants, Ridge, RBF SVR, histogram gradient boosting and Extra Trees; task means or 50 task statistics.
- V3: eight configurations: constants, Ridge, histogram gradient boosting and a 32/16-unit neural network; causal wrist features.
- Information audit: fixed Ridge and boosting with all training windows, relaxed quality gates and individual signal removals; 132 target/configuration results.
- SWELL: ten configurations across constants, Ridge, RBF SVR and boosting; native physiology or added preceding-rest differences.
- Jev: two fixed prompts, zero-shot and eight-shot. No fine-tuning or test-driven prompt search.
- Demo formulas, Gemini, native IBI model and additional external datasets: no corresponding label-accuracy benchmark completed; no percentage claimed.

Candidate-selection MAEs remain in each experiment's original development/fold reports. The tables report evaluated selection procedures or explicitly fixed models; they do not invent independent accuracies for every candidate tried during tuning.

## API operation and verification

| Dataset / prompt | Requests | Responses | Median latency | P95 latency | Input tokens |
| --- | ---: | ---: | ---: | ---: | ---: |
| universe:zero_shot | 472 | 472 | 0.243 s | 0.355 s | 1,736,754 |
| universe:eight_shot | 472 | 472 | 0.282 s | 0.398 s | 4,494,678 |
| swell:zero_shot | 431 | 431 | 0.247 s | 0.332 s | 1,434,653 |
| swell:eight_shot | 431 | 431 | 0.253 s | 0.326 s | 1,968,231 |

Input tokens: 9,634,316. Estimated list-price cost: $0.4046, using the [documented price](https://docs.typesafe.ai/models) checked on 2026-09-26; this is not an invoice. Invalid/missing target answers: 0. The machine-readable report includes coverage, paired comparisons and internal confidence, which is not physiological accuracy.

All six questions are sent together. Jev selects explicit rating categories (UNIVERSE 0–100 step10 or effort 1–5; SWELL 0–10 step1 or RSME 0–15 step1). No arithmetic interpolation of probability scores is used. Local models retain their continuous predictions. The provider [documents limitations with numeric precision](https://docs.typesafe.ai/model-jaggedness/jev-1.13); this experiment tests two specific physiological prompts, not every possible use of Jev.

Payloads contain physiological features and measurement definitions only, plus optional training examples. Current labels, task names, conditions, participant IDs and timestamps are excluded. API credentials are read only into the authorization header, never saved into artifacts. Requests, responses, datasets and models remain Git-ignored. Prompts, sampling, mappings, source hashes and comparator predictions were frozen before calls. Transport failures never become fallback predictions. Quantization, missingness and task-level weak labels limit interpretation.

UNIVERSE performance direction remains unverified; the prompt explicitly avoids asserting that higher means better. SWELL RSME and physiological exports retain their original units. SWELL's research-only source license remains applicable. Public-dataset exposure during provider pretraining cannot be ruled out. Neither benchmark validates real employees, instantaneous mental states, diagnoses or device compatibility.

```bash
.venv/bin/python scripts/benchmark_jev.py --prepare-only
.venv/bin/python scripts/benchmark_jev.py
.venv/bin/python scripts/report_jev.py
.venv/bin/python scripts/verify_jev.py
```

Saved outputs: `results/jev-v1/report.json`, `matched-comparison.csv`, `all-experiments.csv`, per-target predictions, frozen request manifest and original API responses. The original engine, models, splits and prior reports are unchanged.
