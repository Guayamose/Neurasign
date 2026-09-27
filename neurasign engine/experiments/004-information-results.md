# Experiment 004: useful-information audit

This is a completed development diagnostic, not a new production model or an independent confirmation of accuracy.

## Measured findings

- Fitting all available windows changes errors only slightly with the two fixed models. It does not establish a reliable six-output interpreter.
- Relaxing pulse gates recovers numerical features but does not produce a consistent error reduction across targets and models.
- Removing acceleration increases physical-demand error by 1.28 points for the linear model and 1.33 points for the trees. This is evidence of a useful contribution in these models, although their full physical-demand predictions still lose to the median constant.
- Removing temperature improves some outputs and worsens mental demand. Channel usefulness is target-dependent; no global channel deletion is justified by this comparison.
- The audit tests these particular extracted features and models. It does not prove that the raw recordings contain no further predictive information.

## Labels and actual recording duration

Every window already inherits the questionnaire rating of its source task. The audit verifies that ratings are constant within each task. This supports weakly supervised window prediction; it cannot measure within-task transition timing against an instantaneous reference that was never recorded.

- 41,069 overlapping windows from 472 questionnaire intervals and 19 development participants.
- Source segments cover **121.011 hours**; accepted window coverage is **120.636 hours**.
- Summing all 60-second windows would incorrectly count **684.483 hours** because windows overlap.
- The previous 20-window-per-task fitting sample has 9,440 windows covering 101.386 source hours before target-specific missing-label masking. The audit compares this sample with fitting every available labeled window.
- Source-clock intervals are merged within participant/session; the five original test people remain excluded.

| Session | Accepted coverage, hours | Windows | Pulse intervals available |
| --- | ---: | ---: | ---: |
| Lab1 | 27.764 | 9,160 | 62.65% |
| Lab2 | 25.492 | 8,412 | 51.62% |
| Wild | 67.381 | 23,497 | 45.30% |

Hours supply physiological variation; they do not create extra independently rated tasks or additional people. Both the duration and the number of independent people matter. These diagnostics do not establish a sample-size ceiling.

## Pulse masking and signal checks

The earlier extraction considered 41,205 windows, rejected 12 for gaps, and removed 124 duplicated recording instants. It did not reject half the recordings. On the final 41,069 rows, seven pulse-related features are missing in 20,344 windows (49.536%); the remaining 36 features are present. Counts from the earlier audit include pre-deduplication rows and therefore differ slightly.

| Diagnostic group | Windows | All windows | Median pulse/device-HR difference | Difference ≤10 bpm |
| --- | ---: | ---: | ---: | ---: |
| v3_retained | 20,725 | 50.46% | 1.73 bpm | 94.17% |
| recover_motion_only | 6,381 | 15.54% | 22.96 bpm | 37.06% |
| recover_after_both_gates | 19,908 | 48.47% | 8.95 bpm | 52.42% |
| still_fails_beat_checks | 436 | 1.06% | n/a | n/a |

Recovery groups overlap. Ignoring motion retains the periodicity and beat-count checks; ignoring both gates still requires at least 20 valid intervals and ≥80% of intervals between 300 and 2,000 ms. No production quality gate has been relaxed.

Device HR is corroborating evidence from the same optical sensor, not independent ECG ground truth. A large difference suggests an unstable measurement; agreement alone cannot validate pulse-interval variability.

The audit flags 10,268 windows for acceleration near its measurement limit, 9,631 for high acceleration variation, and 13,875 for low pulse periodicity. These groups overlap. EDA is flat within 0.001 µS across 494 windows. Temperature is outside 30–40 °C for most samples in 5,562 windows. These are screening flags, not proof that every affected channel is unusable or that a participant has a physiological condition.

Three source checks (UN_121/Lab2 arithmetic easy, UN_110/Lab2 N-back hard, UN_103/Lab2 arithmetic hard) match the full labeled BVP and acceleration sequences to original CSV samples exactly after reversing the counts-to-g conversion. High acceleration values are present in those original recordings. This rules out our conversion as their cause in those three cases; it does not identify the underlying device or recording problem. The ignored `native-acc-check.json` records positions and ranges.

## Fixed-model ablations

Five participant-disjoint folds, two fixed learned models, ten fixed input/training variants and two constant baselines. All variants receive the same validation windows and targets. Median imputation and scaling are fitted only on each training fold. Removing device HR also removes the derived pulse/HR difference to avoid retaining that signal indirectly. The all-window variant keeps total fitting weight unchanged to avoid silently changing L2 regularization strength.

The metric is absolute error on each window, averaged within task, then participant, then across people. Mental effort uses 1–5; all other targets use 0–100. Smaller is better. These fixed-model results differ from v3's nested model-selection procedure.

### Regularized linear model

| Variant | Mental effort | Mental demand | Physical demand | Time pressure | Performance rating | Effort |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| constant mean | 0.9058 | 24.3209 | 22.5269 | 27.5980 | 20.6222 | 21.0121 |
| constant median | 0.8384 | 23.8989 | 19.4140 | 27.8827 | 20.1862 | 20.8065 |
| Original gates, 20 windows/task | 0.9058 | 24.2059 | 21.0985 | 27.8906 | 21.3548 | 21.5292 |
| All training windows | 0.9043 | 24.2281 | 21.1475 | 27.8626 | 21.3618 | 21.5513 |
| Ignore motion gate | 0.9073 | 24.3457 | 21.0721 | 28.3055 | 21.2784 | 21.5625 |
| Ignore motion + periodicity gates | 0.9107 | 24.4065 | 21.1668 | 28.4170 | 21.2860 | 21.5929 |
| Remove EDA | 0.9116 | 24.4504 | 21.2892 | 28.1360 | 21.2293 | 21.5068 |
| Remove temperature | 0.8930 | 24.4101 | 20.8934 | 27.6582 | 20.9320 | 21.7693 |
| Remove acceleration | 0.9130 | 24.5576 | 22.3812 | 27.7940 | 21.3303 | 21.4123 |
| Remove device HR | 0.9078 | 24.3523 | 21.2624 | 28.0595 | 21.2122 | 21.7232 |
| Remove all pulse-wave features | 0.9004 | 23.9539 | 21.3394 | 28.0290 | 21.2337 | 21.0800 |
| Remove pulse intervals | 0.9105 | 24.0848 | 21.0421 | 28.0030 | 21.3173 | 21.3471 |

### Gradient-boosted trees

| Variant | Mental effort | Mental demand | Physical demand | Time pressure | Performance rating | Effort |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| constant mean | 0.9058 | 24.3209 | 22.5269 | 27.5980 | 20.6222 | 21.0121 |
| constant median | 0.8384 | 23.8989 | 19.4140 | 27.8827 | 20.1862 | 20.8065 |
| Original gates, 20 windows/task | 0.9231 | 24.4759 | 21.0298 | 27.7590 | 21.0847 | 21.3533 |
| All training windows | 0.9313 | 24.1895 | 20.9311 | 27.8200 | 21.1276 | 21.4924 |
| Ignore motion gate | 0.9288 | 24.3440 | 21.0417 | 28.0113 | 21.0399 | 21.4769 |
| Ignore motion + periodicity gates | 0.9252 | 24.3116 | 21.0117 | 27.9437 | 21.0840 | 21.5229 |
| Remove EDA | 0.9083 | 24.0202 | 21.3210 | 28.4204 | 21.0555 | 21.4933 |
| Remove temperature | 0.8760 | 24.6726 | 20.0841 | 27.3322 | 20.9425 | 21.2945 |
| Remove acceleration | 0.9226 | 24.4090 | 22.3624 | 27.3573 | 21.3038 | 21.1096 |
| Remove device HR | 0.9279 | 24.5685 | 20.9259 | 28.0032 | 21.1672 | 21.4348 |
| Remove all pulse-wave features | 0.9375 | 25.0068 | 21.0244 | 27.9870 | 21.0747 | 21.7301 |
| Remove pulse intervals | 0.9218 | 24.4073 | 21.0299 | 27.9060 | 21.0886 | 21.4242 |

## Additional source inventory: native beat intervals

After defining the ablation protocol, a separate source inventory checked original Empatica `IBI.csv` files. This exploratory inventory does not change any ablation, target or fitted model.

The 19 development participants have 100 native IBI files. 98 passed strict parsing and contain **314,536 observed beat intervals**; 2 files contain embedded headers and were explicitly excluded rather than silently repaired. 86 of the parsed files have interevent gaps longer than one minute. These counts include unlabeled recording time and are not a measure of labeled-window coverage.

The current causal engine derives intervals from the BVP waveform; it does not consume these manufacturer intervals. They are a concrete untested input, not a demonstrated accuracy improvement. A next experiment should align their native clock to the verified BVP/task segments, compute variability only over valid consecutive beats without bridging gaps, and compare coverage and held-out-person errors against the current detector. The same optical source means these intervals are not independent ECG ground truth.

Reproduce with `.venv/bin/python scripts/audit_native_ibi.py`. Digests, file-level counts and exclusions are in ignored `results/information-v4/native-ibi-inventory.json`.

All ablation settings were recorded before fitting in [the protocol](004-information-protocol.json). The comparisons are exploratory on reused development people. We report all variants, select no winner, and do not treat the best cell among many comparisons as independently established improvement. The machine-readable report includes paired participant changes and descriptive bootstrap ranges; these are not per-prediction confidence values.

## Reproduce and inspect

```bash
.venv/bin/python scripts/audit_native_ibi.py
.venv/bin/python scripts/audit_information.py
.venv/bin/python scripts/verify_information_audit.py
.venv/bin/python -m unittest discover -s tests -p 'test_information_audit.py' -v
```

Ignored artifacts under `results/information-v4/`: `report.json`, `quality.json`, `diagnostics.csv.gz`, `extraction.json`, `ablation.json`, and per-variant predictions. Raw-source digests are checked before loading. The unmasked pulse features are cross-checked against every corresponding v3 row. Runtime v3, its frozen data, trained artifact and dashboard are unchanged.

Measured run time: 386.4 seconds. No external training API was used.

## Research references

The [UNIVERSE paper](https://www.nature.com/articles/s41597-024-03738-7) reports 159.70 wrist-recording hours across all 24 people. Its signal-quality analysis reports BVP passing its own spectral-entropy check for 68.94% of lab and 51.18% of uncontrolled data. Its criteria and population differ from ours, so these figures cannot validate our gate. The authors also discuss fit/contact and possible sensor-cap issues. Neither observation establishes the cause of a particular local flagged window.

[Empatica's raw-data specification](https://www.empatica.com/blog/decoding-wearable-sensor-signals-what-to-expect-from-your-e4-data/) confirms acceleration counts divided by 64 give g, and that its HR output averages 10-second spans. That smoothing is another reason detector/device-HR differences cannot be interpreted as independent measurement errors.

The authors' [published classifier driver](https://github.com/HPI-CH/UNIVERSE/blob/0502dd32bfcb18d5960f8faa51a26f75ca4d6322/Machine%20learning/main_ml.py) includes EEG, per-person binary problems and full-participant label thresholds in its Wild example. Its [split implementation](https://github.com/HPI-CH/UNIVERSE/blob/0502dd32bfcb18d5960f8faa51a26f75ca4d6322/Machine%20learning/classification.py) uses shuffled KFold for the corresponding example. That setup is not evidence of six-target, wrist-only generalization to unseen people. We do not reproduce its affective composite target.
