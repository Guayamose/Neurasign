# First wrist-only multi-output experiment

Status: trained and evaluated offline; research use only.

The prepared dataset contains 43,062 overlapping windows from 598 questionnaire/task intervals and 24 participants. A window is not an independent label.

## Outputs and held-out results

MAE is the absolute error in questionnaire scale points, averaged within participant and then across the five held-out participants. Predictions are averaged over each labeled interval for scoring. A lower value is better. The baseline always predicts a development-set mean with participant/interval weighting.

| Output | Scale | Selected model | Model MAE | Baseline MAE | Better than baseline |
| --- | --- | --- | ---: | ---: | --- |
| mental_effort | 1–5 | ridge | 0.960 | 0.959 | No |
| mental_demand | 0–100 | hist_gradient_boosting | 29.719 | 30.095 | Yes |
| physical_demand | 0–100 | hist_gradient_boosting | 16.607 | 18.127 | Yes |
| temporal_demand | 0–100 | hist_gradient_boosting | 29.602 | 29.625 | Yes |
| perceived_performance | 0–100 | ridge | 26.372 | 25.978 | No |
| effort | 0–100 | ridge | 29.122 | 28.684 | No |

All six supported targets retain their original rating scales. Missing target values are masked independently; no missing questionnaire answer is imputed. The six heads share an input schema and bundle but are fitted separately.

## Selection and validation

- Frozen participant split: 19 development participants, five held-out participants, recorded in `split-v1.json`.
- Five-fold participant-grouped validation compares a mean baseline, ridge regression and histogram gradient boosting. Model selection finishes before held-out scoring.
- Imputation and standardization are fitted inside each development fold. Tree early stopping is disabled to avoid a random internal window split.
- Per-participant and per-interval sample weights prevent long recordings from dominating training.
- Only the ten allowlisted pulse-HRV, EDA and temperature features enter the models. IDs, task names and all questionnaire responses are excluded from inputs.
- Stress, frustration, PANAS and affective-slider outputs are excluded from workplace biometric inference. The weighted NASA composite is also excluded because it includes frustration.

## Data audit

| Target | Labeled intervals | Windows | Participants |
| --- | ---: | ---: | ---: |
| mental_effort | 422 | 35021 | 24 |
| mental_demand | 598 | 43062 | 24 |
| physical_demand | 598 | 43062 | 24 |
| temporal_demand | 598 | 43062 | 24 |
| perceived_performance | 598 | 43062 | 24 |
| effort | 598 | 43062 | 24 |

Audit exclusions and missingness: `{"duplicate_feature_segments_removed": 0, "feature_segments_seen": 611, "malformed_questionnaire_rows": 9, "missing_label:mental_effort": 180, "questionnaire_rows": 618, "segments_missing_modality": 3, "segments_with_misaligned_modalities": 4, "segments_without_usable_questionnaire": 6, "windows_rejected_missing_features": 137}`.

## Interpretation limits

- Offline published features: upstream interpolation/backfill and segment-wise processing can use future samples. Not a causal real-time validation.
- Labels describe whole tasks/questionnaire intervals; adjacent windows are not independent labels.
- Feature tables cover a subset of recorded hours. No conversion of overlapping windows into independent recording hours.
- These features use pulse-derived HRV, EDA and temperature; no EEG, task IDs, participant IDs or questionnaire answers are model inputs.
- Only physiological feature missingness is imputed inside training folds; missing targets are never fabricated.
- Five held-out participants provide a limited research evaluation, not workplace or cross-device validation.
- Predictions are estimates of questionnaire ratings, not observed mental states, diagnoses, productivity or fitness for duty.
- Performance is self-reported; its numeric direction is preserved without asserting objective success.

The source pipeline fills some missing feature values using later samples and processes complete segments. This experiment therefore does not validate live causal inference. Re-extract causal windows and evaluate signal quality and device transfer before live integration.

No score is claimed to measure fatigue, recovery, emotion, mental health, employee productivity or fitness for duty. A head that fails to beat the baseline has not demonstrated predictive benefit in this held-out comparison.

## Reproduction

From the engine directory:

```bash
.venv/bin/python scripts/train_multioutput.py
.venv/bin/python scripts/predict_multioutput.py --input results/multioutput-v1/example-input.json
```

Detailed reports/predictions are under ignored `results/multioutput-v1/`; the artifact is `models/multioutput-v1.joblib`. Model and data hashes are stored in the report. Repeatedly tuning on this held-out result would invalidate it as a final test.

Sources: [UNIVERSE](https://zenodo.org/records/10371068), [authors' feature extraction](https://github.com/HPI-CH/UNIVERSE/blob/main/Features/main_features.py), [participant-grouped validation](https://scikit-learn.org/stable/modules/cross_validation.html#cross-validation-iterators-for-grouped-data).
