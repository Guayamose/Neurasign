# Experiment 015: FatigueSet wrist fatigue labels

Original [FatigueSet](https://www.esense.io/datasets/fatigueset/) wrist recordings and physical/mental fatigue VAS answers. Twelve people and 36 sessions supply 108 potential reference answers; 103 have sufficient wrist features. The classifier target is the fixed research midpoint: VAS ≥50 versus <50. No middle answers are discarded. This threshold is not a clinical definition of fatigue.

Nine people are used for development; three reserved people provide 27 answers for the single final evaluation. Fifty classifier/profile configurations per target compare logistic regression, RBF SVM, ExtraTrees and CatBoost. Four person-disjoint development folds select balanced accuracy; a top-three ensemble is also eligible. All choices are frozen before test scoring. Preprocessing is trained within each fold.

Inputs are E4 wrist BVP, HR, IBI, EDA, temperature and acceleration, with cardiac/autonomic/all-signal profiles, 60-second/180-second evidence and optional deviations from the first 60 seconds of baseline physiology. No EEG, chest signals, task phase, time, demographics, identity or questionnaire answers enter the features. Each questionnaire uses its own UTC submission marker to resolve changing relative-clock offsets. Features end before the response and no response is copied into thousands of independent labels.

| Target | Test accuracy | Balanced accuracy | Low recall | High recall | Test low/high answers |
|---|---:|---:|---:|---:|---:|
| physical fatigue | 66.7% | 82.7% | 65.4% | 100.0% | 26/1 |
| mental fatigue | 77.8% | 43.8% | 87.5% | 0.0% | 24/3 |

**The physical-fatigue 82.7% balanced result is based on only one high-fatigue answer.** Its ordinary accuracy is 66.7% and low-state recall 65.4%; nine low answers become false high-fatigue alerts. A constant low classifier gets 96.3% ordinary accuracy while detecting zero high-fatigue answers. The mental-fatigue classifier detects zero of three high-fatigue answers. Neither target meets the predefined 80% balanced/70% each-recall gate.

Only one test person has both classes for each target. Person-bootstrap intervals are conditional on resamples containing both classes; they do not establish variability of high-fatigue detection when only one positive reference exists. These results cannot establish a general fatigue monitor or cross-device/workplace transfer.

Actual selected artifacts are saved locally under `models/fatigueset-physical-v1/` and `models/fatigueset-mental-v1/`, with `production_enabled=False`. Data, weights and participant-level predictions remain ignored. The author site releases data for research; an explicit redistribution/commercial license was not identified.

Run `python3 scripts/download_fatigueset.py`; then `.venv/bin/python scripts/run_fatigueset.py prepare`; run `run --target physical` and `run --target mental` separately. Completed runs refuse replacement; use `verify --target physical` / `verify --target mental` to replay artifacts and check metrics.
