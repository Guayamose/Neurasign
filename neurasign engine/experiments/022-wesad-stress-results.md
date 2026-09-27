# Experiment 022: WESAD wrist protocol-condition benchmark

**Offline scientific research only. Production disabled. This is not an employee stress detector.**

## Data and target

New external dataset: 15 WESAD participants, authors’ synchronized Empatica E4 BVP (64 Hz), EDA and skin temperature (4 Hz), and accelerometer (32 Hz). No chest, EEG, demographics, questionnaire answers, subject IDs, timestamps or condition codes enter the model. The label is baseline versus the experimentally induced TSST protocol condition; it is not the participant’s actual instantaneous stress.

There are 434 eligible non-overlapping 60-second windows. Only windows entirely within one source condition are retained; transitions, amusement and meditation are excluded. The readme warns that raw wrist CSV times are not synchronized; this benchmark instead uses the authors’ synchronized arrays. HR/IBI vendor files are ignored as the source instructs. Pulse summaries are estimated within each completed BVP window and are not ECG-validated HRV.

## Evaluation

Frozen before feature extraction: 12 development people ['S10', 'S11', 'S13', 'S14', 'S15', 'S16', 'S2', 'S3', 'S6', 'S7', 'S8', 'S9']; 3 test people ['S17', 'S4', 'S5']. Four participant-disjoint inner folds select among 32 fixed configurations: logistic regression, RBF SVM, ExtraTrees and histogram gradient boosting; autonomic-only versus all wrist channels. The criterion is mean per-person balanced accuracy. Fitted preprocessing never sees validation/test people. No random window split and no test tuning.

| Arm | Accuracy | Balanced accuracy | Baseline recall | TSST recall | Person-mean balanced |
|---|---:|---:|---:|---:|---:|
| majority | 66.28% | 50.00% | 100.00% | 0.00% | 50.00% |
| fixed_logit | 96.51% | 95.67% | 98.25% | 93.10% | 96.09% |
| selected | 94.19% | 92.23% | 98.25% | 86.21% | 92.73% |

Selected configuration: `{"profile": "wrist_all", "kind": "extra", "leaf": 3}`. Development participant-grouped mean balanced accuracy: 88.45%.

The predeclared fixed logistic baseline performed better on these three test people. The selected ExtraTrees model remains the primary selected-model result: we did not switch models or retune after seeing the test. This search did not improve over the fixed baseline on the held-out set.

Selected model’s descriptive 95% participant-cluster bootstrap interval for person-mean balanced accuracy: 83.73%–100.00%. Only three held-out clusters: this interval is unstable and cannot establish population reliability. It is not per-prediction confidence.

Coverage: 86 / 86 eligible held-out windows, no abstention; eligibility already excludes unlabeled/transition/non-target periods. A prediction uses a completed trailing minute and updates once per minute. No instantaneous/live validation was performed.

## Limits

- Three unseen participants only; windows are not independent subjects.
- Protocol stress condition is not an individual self-report or validated mental-state label.
- Lab tasks, speech/movement, posture and temperature drift may confound classification.
- Requires E4 raw BVP/EDA/TEMP/ACC; no transfer claim to other devices.
- No confidence calibration, clinical, workplace, or real-time validation.
- Scientific non-commercial source license; no product integration.

Do not compare this number directly with self-report stress, fatigue, readiness or workload benchmarks: the target and difficulty are different. Condition recognition can partly exploit task/activity or temperature drift; it does not solve general employee monitoring.

## Source, integrity and reproduction

[Authors’ dataset and scientific non-commercial terms](https://ubi29.informatik.uni-siegen.de/usi/data_wesad.html); [UCI metadata](https://archive.ics.uci.edu/dataset/465/wesad+wearable+stress+and+affect+detetection); [Schmidt et al., ICMI 2018](https://doi.org/10.1145/3242969.3242985).

Official ZIP members are fetched by byte range, with original ZIP CRC/size and SHA-256 recorded. A restricted NumPy-only unpickler rejects arbitrary globals and persistent references; only numeric wrist arrays and synchronized labels enter feature extraction. No downloaded executable code is run. Acquired recordings and models remain ignored by git.

Run `scripts/run_wesad_stress_022.py freeze`, `download`, `prepare`, `run`, then `verify` with the engine Python environment. A completed held-out run refuses reruns; verification independently recomputes metrics and replays saved artifacts. Artifacts in `models/wesad-stress-022/`, evidence in `results/wesad-stress-022/`. Prior experiments 001–018 remain unchanged.
