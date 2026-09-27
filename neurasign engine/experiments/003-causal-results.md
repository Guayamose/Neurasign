# Causal raw-wrist streaming experiment

Status: trained and evaluated against weak questionnaire labels; streaming replay is implemented.

41,069 usable windows from 472 intervals and 19 development participants. The original five test participants were not read for feature extraction, fitting or scoring.

## Live computation contract

A prediction uses the preceding 60 seconds and updates every 10 seconds. Raw labeled BVP, EDA, temperature, HR and three acceleration axes replace the authors' offline feature tables. The same extractor processes recorded prefixes and incoming blocks. Every operation is limited to samples before the prediction timestamp; there is no backward fill, future interpolation, whole-task normalization or completed-task feature aggregation.

43 features describe pulse-wave shape/periodicity and pulse intervals, skin signals, trends and movement. Acceleration counts are converted to g; magnitude is recomputed from XYZ because some published ACC_MAG series contain erroneous zeros. Pulse variability is masked when heuristic quality or motion checks fail; missing channels/gaps cause abstention, not fabricated readings.

## Model comparison

Eight configurations cover mean/median references, ridge regression, gradient-boosted trees and a 32/16-unit neural network. Neural training has no random internal validation split. Up to 20 evenly spaced windows per interval are used for fitting to limit overlap redundancy; every usable evaluation window is scored. Missing answers are masked independently.

Five outer participant folds evaluate selection; three inner folds tune models. Unlike v1/v2, the primary error is computed before averaging window predictions: errors cannot cancel within a task. Interval and participant weighting prevent long recordings from dominating.

| Output | Selected procedure MAE | Best learned procedure MAE | Constant procedure MAE | Final choice |
| --- | ---: | ---: | ---: | --- |
| mental_effort | 0.873 | 0.895 | 0.882 | constant_median |
| mental_demand | 24.703 | 24.123 | 24.503 | boost_absolute_7 |
| physical_demand | 19.394 | 19.901 | 19.414 | constant_median |
| temporal_demand | 28.054 | 27.809 | 27.609 | constant_mean |
| perceived_performance | 20.929 | 21.070 | 20.537 | constant_median |
| effort | 20.960 | 21.245 | 20.960 | constant_median |

These scores evaluate the selection procedure across development people. They are not independent test scores of the final artifact, and cannot be compared directly to v1/v2 scores with different accepted windows and evaluation definitions.

## Limits

- Labels are task/questionnaire ratings copied as weak supervision, not moment-by-moment ground truth.
- Recorded replay validates causal computation, not Bluetooth delivery or cross-device physiological accuracy.
- Empatica labeled raw samples retain source alignment; source sampling clocks were synchronized offline by the authors.
- Each labeled segment starts with an empty buffer; no future segment statistics or task identity enter features.
- Pulse-interval variability is not ECG HRV; quality thresholds are engineering checks, not clinical validation.
- Per-prediction confidence remains null. Sensor-quality flags are not calibrated probabilities.
- A selected constant produces `no_predictive_model_selected`, never a fake changing state score.
- Predicting a questionnaire rating from a past window does not validate instantaneous state changes.
- Emotions, mental-health outputs and the composite containing frustration remain excluded.
- This is an engine interface and recorded replay; it is not a production API integration or hardware certification.

## Quality coverage

```json
{
  "questionnaire_rows": 484,
  "missing_label:mental_effort": 135,
  "segments_considered": 472,
  "windows_considered": 41205,
  "pulse_variability_unavailable": 20406,
  "pulse_variability_masked_during_high_motion": 10441,
  "missing_labeled_segment": 3,
  "malformed_questionnaire_rows": 9,
  "windows_rejected": 12,
  "rejection:incomplete_bvp": 12,
  "rejection:incomplete_eda": 12,
  "rejection:incomplete_temperature": 12,
  "rejection:incomplete_acc_x": 12,
  "rejection:incomplete_acc_y": 12,
  "rejection:incomplete_acc_z": 12,
  "duplicate_instants_removed": 124
}
```

## Reproduce

```bash
.venv/bin/python scripts/train_causal.py
.venv/bin/python scripts/replay_causal.py --participant UN_101 --session Lab1 --seconds 180
.venv/bin/python scripts/stream_causal.py < samples.jsonl
```

The model is `models/causal-v3.joblib`; full per-window predictions and metrics are under `results/causal-v3/`. The extractor, raw provenance and quality exclusions are under `data/prepared/causal-v3/`. These directories are ignored by Git.

References: [UNIVERSE source synchronization](https://github.com/HPI-CH/UNIVERSE/blob/main/Synchronization/main.py), [forward filtering](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.sosfilt.html), [MLP regression](https://scikit-learn.org/stable/modules/generated/sklearn.neural_network.MLPRegressor.html).
