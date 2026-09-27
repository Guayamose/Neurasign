# Experiment 012: anonymous self-reported stress benchmark

**Result: insufficient evidence for a reliable stress classifier or an 80% accuracy claim. No model was enabled in the product.**

This separate academic benchmark classifies the original UNIVERSE `Mental stress level` answers. Levels 1–2 mean low, 4–5 mean high, and neutral 3/missing answers are excluded. These are retrospective task answers, not measured instantaneous stress or clinical ground truth.

Only **2 people** have eligible labeled windows in both laboratory sessions; **2** have both low and high labels in Lab2. This cannot satisfy the protocol requirement for an informative cohort of at least ten people with both evaluation classes. High ordinary accuracy on an imbalanced cohort cannot establish discrimination.

## Source and coverage

| Session | People in physiological input | Task intervals | Windows | Missing stress windows | Neutral windows | Low windows | High windows |
|---|---:|---:|---:|---:|---:|---:|---:|
| Lab1 | 19 | 167 | 9160 | 7346 | 552 | 494 | 768 |
| Lab2 | 17 | 153 | 8412 | 0 | 2915 | 3080 | 2417 |

Lab1 fitting has 4 people and 1262 eligible windows. The paired Lab2 evaluation contains 16 task answers and 881 windows, drawn from 991 physiological windows in those people before excluding missing/neutral labels. Windows repeat task answers and are not independent labeled cases.

Questionnaires were checksum-verified against the acquisition manifest and joined through original causal provenance. Malformed or conflicting segment answers are quarantined. No other questionnaire enters a predictor. The original five UNIVERSE test participants and Mobile holdout remain closed.

## Frozen comparison

All fitting and selection use Lab1. General models exclude the evaluation person’s original participant fold; personal models use their own Lab1; hybrid models combine own and other-person Lab1 with the registered weighting. Fixed models use logistic regression; selected models choose among logistic, RBF SVC, ExtraTrees and CatBoost with whole-person or whole-task Lab1 validation. No configuration or cutoff was changed after Lab2 scoring.

Metrics weight people equally and tasks equally within each person. Balanced accuracy averages low/high recall; within-person balanced accuracy includes only people with both Lab2 classes. Model scores are not calibrated confidence.

### all paired

| Arm | Ordinary accuracy | Balanced accuracy | Within-person balanced accuracy | Low recall | High recall |
|---|---:|---:|---:|---:|---:|
| generic_constant | 68.8% | 50.0% | 50.0% | 0.0% | 100.0% |
| personal_constant | 68.8% | 71.8% | 50.0% | 80.0% | 63.6% |
| generic_fixed | 35.6% | 37.9% | 52.5% | 44.0% | 31.7% |
| personal_fixed | 67.2% | 65.1% | 63.0% | 59.5% | 70.7% |
| hybrid_fixed | 37.4% | 53.8% | 53.2% | 97.5% | 10.1% |
| generic_selected | 35.6% | 37.9% | 52.5% | 44.0% | 31.7% |
| personal_selected | 63.7% | 68.0% | 59.5% | 79.4% | 56.5% |
| hybrid_selected | 37.4% | 53.8% | 53.2% | 97.5% | 10.1% |

This subset has 2 people, 16 tasks, 881 windows and 2 people with both classes.

### active tasks only

| Arm | Ordinary accuracy | Balanced accuracy | Within-person balanced accuracy | Low recall | High recall |
|---|---:|---:|---:|---:|---:|
| generic_constant | 78.6% | 50.0% | 50.0% | 0.0% | 100.0% |
| personal_constant | 71.4% | 81.8% | 50.0% | 100.0% | 63.6% |
| generic_fixed | 29.2% | 25.9% | 45.0% | 20.0% | 31.7% |
| personal_fixed | 66.2% | 60.1% | 46.8% | 49.4% | 70.7% |
| hybrid_fixed | 28.4% | 52.9% | 47.9% | 95.8% | 10.1% |
| generic_selected | 29.2% | 25.9% | 45.0% | 20.0% | 31.7% |
| personal_selected | 61.1% | 67.1% | 41.4% | 77.7% | 56.5% |
| hybrid_selected | 28.4% | 52.9% | 47.9% | 95.8% | 10.1% |

This subset has 2 people, 14 tasks, 771 windows and 1 people with both classes.

## Limits and artifacts

Lab2 has already appeared in prior development experiments, so this is a reused development comparison, not a fresh external test. Source stress coverage is sparse in Lab1. Single-class calibration produces explicitly marked constant artifacts. Rest exclusion is a descriptive task-context check and cannot supply missing classes or justify model selection.

No readiness or fatigue reference was created. No claim about employees, individual health, diagnosis, live monitoring or deployment follows from these results. More signal windows cannot supply missing independent target answers.

The protocol is [012-stress-protocol.json](012-stress-protocol.json). Prepared data, source-line provenance, selections, predictions and non-production artifacts live in ignored `data/prepared/stress-v1/`, `results/stress-v1/` and `models/stress-v1/`. The verifier independently recalculates metrics, checks person/task/session separation, confirms preserved files and replays saved model predictions.

Run `.venv/bin/python scripts/run_stress_benchmark.py verify` from the engine directory to inspect the completed artifacts. Stages are `prepare`, `select`, `evaluate`, `report`, `verify`; completed preparation, selection and evaluation refuse replacement.
