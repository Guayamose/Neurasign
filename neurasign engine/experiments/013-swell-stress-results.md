# Experiment 013: SWELL self-reported stress

**Separate offline research benchmark. No production integration or wrist-device accuracy claim.**

The target is the actual `Stress` questionnaire rating. Research cutoffs are ≤3⅓ (low) and ≥6⅔ (high), with middle ratings excluded. Experimental condition is neither the target nor a predictor. The only inputs are HR, RMSSD and SCL from chest ECG and finger conductance.

The comparison retains 17 of the original 20 development people, 41 blocks and 1235 minutes. It excludes 531 middle-rated minutes and 0 missing ratings among 1766 minutes with physiological data. The original five test people remain closed.

Each outer fold holds out whole people. Three inner person-disjoint folds choose among logistic regression, RBF SVM, ExtraTrees and CatBoost, with preprocessing fitted only on the respective training data. All outer choices were saved before computing their out-of-fold predictions. Results weight people equally, then blocks equally.

| Arm | Accuracy | Balanced accuracy | Low recall | High recall | Macro F1 | Within-person balanced |
|---|---:|---:|---:|---:|---:|---:|
| majority | 88.2% | 50.0% | 100.0% | 0.0% | 46.9% | 50.0% |
| fixed | 79.5% | 75.5% | 80.7% | 70.2% | 66.0% | 45.2% |
| selected | 73.8% | 50.6% | 81.0% | 20.2% | 50.0% | 45.2% |

Only 2 evaluated people have both low and high blocks. Within-person balanced accuracy excludes single-class people, so the pooled balanced measure is primary here.

These are repeated block ratings, not independently labeled minutes or instantaneous stress. Development participants appeared in earlier research; this is not an untouched external test. No fatigue/readiness labels are created. The source remains subject to its original research-use license. Scores are not calibrated confidence.

Reproduce with `scripts/run_swell_stress.py run`; inspect the completed run with `scripts/run_swell_stress.py verify`. Saved artifacts, predictions, frozen folds and reports live in ignored `models/swell-stress-v1/` and `results/swell-stress-v1/`.
