# Experiment 009: raw pulse transfer with PaPaGei-S

**Development experiment only. No new independent test and no product integration.**

**Assessment:** This bounded frozen-encoder experiment did not find a dependable improvement. Every paired development interval against the engineered comparator includes zero. None establishes a positive advantage over the constant comparator either. The findings do not support deploying questionnaire interpretation scores. They apply to this frozen encoder and these heads; end-to-end fine-tuning and other temporal architectures have not been exhausted.

The frozen encoder processed 43,503 distinct completed 10-second chunks; 43,495 passed availability checks. The matched comparison includes 35,425/41,069 original endpoints (86.3%), 472 tasks and 19 development participants. Every profile requires the same three-minute warm-up and signal coverage, including the one-minute profiles and baselines.

## Results

Lower mean absolute error (MAE) is better. Each person and task has equal weight. The selected PaPaGei configuration is chosen by development MAE, not by the agreement column. Agreement is exact 1–5 category agreement for mental effort and within ±10 points for the five 0–100 ratings.

| Questionnaire target | Constant MAE | Engineered MAE | PaPaGei MAE | PaPaGei agreement | Constant agreement | Best PaPaGei |
|---|---:|---:|---:|---:|---:|---|
| mental_effort | 0.838 | 0.870 | 0.854 | 34.5% | 43.5% | fused180__ridge1000 |
| mental_demand | 23.782 | 23.833 | 23.966 | 25.9% | 36.3% | ppg60__cat4 |
| physical_demand | 19.414 | 19.580 | 20.084 | 49.9% | 68.5% | ppg60__cat4 |
| temporal_demand | 27.498 | 25.989 | 25.916 | 19.5% | 14.3% | fused60__ridge100 |
| perceived_performance | 20.186 | 20.388 | 20.233 | 33.5% | 38.8% | ppg60__cat4 |
| effort | 20.831 | 20.391 | 20.392 | 31.0% | 37.4% | fused180__cat4 |

The engineered comparator is the better of the newly matched engineered candidates and the prior experiment 008 winner retrained on exactly the same eligible population. Constants are fitted independently inside each fold. Their mean/median variant is selected on development MAE. These are development selection results, so neither the selected scores nor their intervals establish generalization.

| Target | MAE improvement over constant (95% descriptive interval) | MAE improvement over engineered (95% descriptive interval) |
|---|---:|---:|
| mental_effort | -0.016 [-0.134, 0.103] | 0.016 [-0.008, 0.039] |
| mental_demand | -0.184 [-0.630, 0.260] | -0.133 [-1.703, 1.403] |
| physical_demand | -0.670 [-1.255, -0.132] | -0.504 [-2.333, 1.259] |
| temporal_demand | 1.582 [-0.148, 3.361] | 0.073 [-0.613, 0.749] |
| perceived_performance | -0.046 [-0.325, 0.229] | 0.156 [-0.464, 0.755] |
| effort | 0.439 [-0.695, 1.605] | -0.001 [-0.315, 0.314] |

Positive improvement means lower PaPaGei error. Intervals resample the 19 people, not overlapping windows. They are descriptive, do not correct for selecting the best candidate and are not an independent validation claim.

## Method and boundaries

- PaPaGei-S is frozen: a 512-coordinate embedding per completed 10-second raw BVP chunk, output index 0. No UNIVERSE target is used to update the encoder.
- Inputs follow the authors' training normalization order: filter at 64 Hz, z-score each chunk, resample to 125 Hz. The band-pass uses only the chunk and up to 10 seconds of past padding; the full task is never filtered in advance. A zero-phase filter over a completed past chunk is endpoint-causal.
- Profiles compare the last minute, fusion with EDA/temperature/movement/HR and past-reference deltas, and three-minute embedding means plus recent-versus-earlier differences. This is temporal aggregation, not a recurrent network or end-to-end fine-tuning.
- Ridge (alpha 100 and 1000) and CatBoost (depth 4) are trained in five participant-disjoint folds. CatBoost receives 32 PCA coordinates per embedding block; PCA, scaling and imputation are fitted on training participants only. Maximum 20 training windows per task; all eligible validation windows are scored.
- 90 target/configuration comparisons, 450 supervised fold fits: 54 with PaPaGei, 18 matched engineered controls, 12 constants and six retrained prior winners. All six questionnaire targets remain separate.
- No EEG, task name, person identity, questionnaire field, future physiology or held-out participant enters predictors. Original UNIVERSE and Mobile tests remain closed. Mobile has no raw PPG for this route.
- Questionnaire ratings apply to an entire task. Repeating them across windows does not create instantaneous ground truth. History resets at labeled recording boundaries; this comparison does not establish continuous, boundary-free deployment performance.
- Availability checks reject gaps, nonfinite values and flat chunks; they do not establish freedom from motion artifacts. The three-minute warm-up and coverage restriction reduce the scored population.
- Raw PPG access is required. Supporting a wearable's HR API alone does not make it compatible with this encoder. Physical demand is not fatigue, and perceived performance is a self-rating, not measured productivity.

## Reproduce

From `neurasign engine/`:

```bash
.venv/bin/python scripts/download_papagei.py
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python scripts/run_papagei.py extract
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python scripts/run_papagei.py train
.venv/bin/python scripts/run_papagei.py report
.venv/bin/python scripts/run_papagei.py verify
.venv/bin/python scripts/audit_papagei.py
```

The independent verifier permits at most 0.000001 point of MAE rounding difference when float32 predictions are saved to CSV and read as float64. The original 1e-10 relative check was too strict for that serialization. Training code, saved predictions and recorded scores remain unchanged; no model was retrained for this correction. The additional audit writes `results/papagei-v1/comparison.png` and `.pdf`.

All verification checks passed: 270 independently recalculated error/agreement metrics, 90 balanced accuracies, 12 paired intervals and six saved research artifacts. The largest CSV MAE difference was 0.0000000115 points. All 27 frozen experiment 008 code files and its old test report are unchanged. All 46 tests pass, including future-sample mutation, missing-signal rejection, training-only PCA and independence from other inference-batch members.

The complete candidate table, per-window out-of-fold predictions, selected research models, source checksums and audit are stored in ignored `results/papagei-v1/`, `models/papagei-v1/` and `data/prepared/papagei-v1/`. The [protocol](009-papagei-protocol.json) was written before supervised PaPaGei outcomes. The experiment does not exhaust end-to-end fine-tuning, larger temporal models or other foundation models.

## Sources

- [Official PaPaGei repository](https://github.com/Nokia-Bell-Labs/papagei-foundation-model/tree/0c537dad4d2850e15b724260de820dd68d77f0b0), pinned architecture and normalization code.
- [Official pretrained weights](https://zenodo.org/records/13983110), published MD5 verified, safe tensor-only loading. Authors list VitalDB, MIMIC-III and MESA as training sources; no UNIVERSE overlap is reported. This is not a workload-specific pretraining claim.
- [PaPaGei paper](https://arxiv.org/abs/2410.20542). Published model results are not NEURASIGN accuracy.

The source file labels its license BSD-3-Clause-Clear while the repository LICENSE is BSD 3-Clause. Both original notices are retained in the vendored architecture and license file. No research artifact is integrated into the product.
