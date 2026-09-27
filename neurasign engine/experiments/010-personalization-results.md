# Experiment 010: personal calibration across laboratory sessions

**Lab1 training and selection; Lab2 evaluation. Wrist signals only. Research, not production validation.**

**Assessment:** Personalization did not meet the prespecified research criterion. In the informative mental-demand comparison (17 people), the Lab1-selected general model scores 57.1% within-person balanced accuracy, the personal model 58.6%, and the hybrid 60.1%. The paired improvements over general include zero in their exploratory 95% intervals. With relaxation periods excluded, the hybrid scores 54.3% among the 13 people who still have both classes. Calibration used a median 60 minutes of labeled evidence; this does not establish a short onboarding procedure or reliable workplace interpretation.

The comparison asks whether knowing a person's labeled first session helps classify their second session. Every outcome uses the original questionnaire response. Task names, difficulty, participant IDs, EEG and other questionnaire fields are excluded from predictors.

## Population and labels

The [preregistered protocol](010-personalization-protocol.json) tests mental effort (1–2 low, 4–5 high) and mental demand (0–33⅓ low, 66⅔–100 high). Middle responses and missing labels are excluded and their coverage is reported. The [source-data note](010-data-audit-note.md) records a material limitation discovered before fitting: the mental-effort question is absent from 15 of the 19 Lab1 source CSVs. Only two people permit the first comparison; 17 permit the separate mental-demand comparison. No missing answer is filled with another target or inferred from task difficulty.

| Target | Paired people | People with ≥2 calibration tasks per class | Scored Lab2 windows / all available | Label coverage within paired people |
|---|---:|---:|---:|---:|
| mental_effort | 2 | 1 | 936 / 8,412 | 94.5% |
| mental_demand | 17 | 12 | 6,708 / 8,412 | 79.7% |

## Results

Accuracy weights people equally, then tasks equally within each person. **Within-person balanced accuracy** averages low and high recall separately for each person, then averages people who have both classes. A constant prediction scores 50% on that measure even if high ratings are much more common. This is two-class discrimination, not exact questionnaire-score prediction or calibrated confidence.

The low/high recall columns below use the pooled person/task-weighted confusion matrix. Their average is the pooled balanced accuracy recorded in the full results, which can differ from the primary within-person balanced accuracy when class proportions differ between people.

### mental_demand

| Model | Accuracy | Within-person balanced accuracy | Low recall | High recall |
|---|---:|---:|---:|---:|
| Other-person majority | 69.2% | 50.0% | 0.0% | 100.0% |
| Own-session majority | 68.1% | 50.0% | 36.4% | 82.2% |
| General · fixed logistic | 51.4% | 52.6% | 47.5% | 53.1% |
| Personal · fixed logistic | 59.2% | 57.1% | 54.6% | 61.3% |
| Hybrid · fixed logistic | 54.5% | 56.5% | 49.4% | 56.8% |
| General · Lab1-selected | 56.6% | 57.1% | 70.0% | 50.7% |
| Personal · Lab1-selected | 62.7% | 58.6% | 55.7% | 65.8% |
| Hybrid · Lab1-selected | 54.8% | 60.1% | 67.6% | 49.1% |

Paired differences below use within-person balanced accuracy; positive means the calibrated arm performs better. Intervals resample people, not the overlapping windows.

| Calibrated arm | Gain over general (percentage points, 95% interval) | Gain over own-session majority (percentage points, 95% interval) |
|---|---:|---:|
| Personal · fixed logistic | +4.5 [-1.5, +10.8] | +7.1 [+1.1, +13.6] |
| Hybrid · fixed logistic | +3.9 [-1.5, +9.1] | +6.5 [+0.3, +12.6] |
| Personal · Lab1-selected | +1.5 [-4.9, +8.0] | +8.6 [+1.9, +15.5] |
| Hybrid · Lab1-selected | +3.0 [-1.0, +7.7] | +10.1 [+4.2, +16.5] |

Prespecified provisional research signal: Personal · Lab1-selected = not met, Hybrid · Lab1-selected = not met. The criterion requires ≥70% balanced accuracy, ≥5-point improvement over general, positive paired intervals against general and the personal constant, and ≥10 evaluated people with both classes. It is not a deployment certification.

### mental_effort

| Model | Accuracy | Within-person balanced accuracy | Low recall | High recall |
|---|---:|---:|---:|---:|
| Other-person majority | 88.2% | 50.0% | 0.0% | 100.0% |
| Own-session majority | 88.2% | 50.0% | 0.0% | 100.0% |
| General · fixed logistic | 76.8% | 51.8% | 19.1% | 84.6% |
| Personal · fixed logistic | 62.3% | 61.0% | 58.9% | 62.7% |
| Hybrid · fixed logistic | 24.0% | 57.0% | 100.0% | 13.8% |
| General · Lab1-selected | 76.8% | 51.8% | 19.1% | 84.6% |
| Personal · Lab1-selected | 41.9% | 57.0% | 75.2% | 37.4% |
| Hybrid · Lab1-selected | 24.0% | 57.0% | 100.0% | 13.8% |

Paired differences below use within-person balanced accuracy; positive means the calibrated arm performs better. Intervals resample people, not the overlapping windows.

| Calibrated arm | Gain over general (percentage points, 95% interval) | Gain over own-session majority (percentage points, 95% interval) |
|---|---:|---:|
| Personal · fixed logistic | +9.2 [-1.1, +19.5] | +11.0 [+6.9, +15.1] |
| Hybrid · fixed logistic | +5.2 [-6.4, +16.8] | +7.0 [+1.6, +12.3] |
| Personal · Lab1-selected | +5.3 [-9.0, +19.5] | +7.0 [-1.0, +15.1] |
| Hybrid · Lab1-selected | +5.2 [-6.4, +16.8] | +7.0 [+1.6, +12.3] |

Prespecified provisional research signal: Personal · Lab1-selected = not met, Hybrid · Lab1-selected = not met. The criterion requires ≥70% balanced accuracy, ≥5-point improvement over general, positive paired intervals against general and the personal constant, and ≥10 evaluated people with both classes. It is not a deployment certification.

## Coverage and context checks

The following restrictions were specified before outcome inspection and use the same saved predictions, without refitting or selecting a winner.

| Target / subgroup | Evaluated people (both classes) | General selected | Personal selected | Hybrid selected |
|---|---:|---:|---:|---:|
| mental_effort / adequate_calibration | 1 (1) | 58.0% | 49.0% | 51.6% |
| mental_effort / active_tasks_only | 2 (0) | n/a | n/a | n/a |
| mental_demand / adequate_calibration | 12 (12) | 57.2% | 58.7% | 60.6% |
| mental_demand / active_tasks_only | 17 (13) | 53.9% | 50.5% | 54.3% |

Adequate calibration means at least two labeled Lab1 tasks per class. Active-only excludes the relaxation video. People with only one remaining class still contribute to accuracy and coverage but cannot support a within-person two-class balanced accuracy.

## Calibration burden and fitting

- mental_effort: median 60.0 minutes of labeled physiological evidence (range 50.0–70.0), median 6.0 labeled tasks, 0 people with only one calibration class. Minutes are the union of observed evidence intervals, not the sum of overlapping windows.
- mental_demand: median 60.0 minutes of labeled physiological evidence (range 40.0–90.0), median 6.0 labeled tasks, 3 people with only one calibration class. Minutes are the union of observed evidence intervals, not the sum of overlapping windows.

The bounded search used 688 Lab1 candidate fold fits and 114 final learned-arm fits/fallbacks. The same fixed logistic model is reported in all arms to isolate personalization from model choice. The additional selected models consider logistic regression, RBF SVM, ExtraTrees and CatBoost with raw or history-relative feature profiles. General selection uses person-disjoint Lab1 folds; personal selection uses whole-task Lab1 folds. Insufficient calibration groups trigger the declared fixed-model or single-class fallback. Hybrid fitting allocates half the pre-class-balancing weight to own Lab1 and half to other people.

## Interpretation limits

- Original five UNIVERSE test people and the Mobile test remain closed. Lab2 has appeared in prior development experiments, so this is a new session-separated development comparison, not fresh independent validation.
- Both sessions repeat the same experimental task families. Success here would not prove transfer to arbitrary workplace activities, other wearable brands or unseen task types.
- Ratings label whole tasks; repeating them on 60-second windows does not create instantaneous ground truth. Low/high cutoffs omit ambiguous middle ratings rather than solving them.
- Personalization requires labeled calibration. This experiment uses the available first session and does not establish that a few onboarding minutes suffice. The phone app remains a sensor gateway.
- The UNIVERSE publication's 71%/74% figures use a different personalized multimodal protocol including EEG and different labels/splits. They are not a directly comparable target for this wrist-only session transfer.

## Reproduce and inspect

From `neurasign engine/`, with the existing `requirements-transfer.txt` environment:

```bash
.venv/bin/python scripts/run_personalization.py prepare
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python scripts/run_personalization.py select
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python scripts/run_personalization.py evaluate
.venv/bin/python scripts/run_personalization.py report
.venv/bin/python scripts/run_personalization.py verify
```

The evaluation stage refuses to overwrite an existing evaluation manifest. Predictions, individual results, candidate selections and the comparison figure are in ignored `results/personalization-v1/`; trained research artifacts are in ignored `models/personalization-v1/`. No interpretation was integrated into the product.

Verification passed: 144 independently recalculated metrics, 88 paired intervals and 114 complete saved-artifact prediction replays. Inference is unchanged after replacing evaluation labels, and all fitted row IDs belong to Lab1. All 53 tests pass. The frozen source dataset, 27 experiment 008 code files, previous external test report and experiment 009 results remain unchanged. `results/personalization-v1/source-label-audit.json` records the 36 verified source questionnaire files behind the label-availability finding.

Reference: [UNIVERSE original study](https://doi.org/10.1038/s41597-024-03738-7), [author code](https://github.com/HPI-CH/UNIVERSE). This is an adapted experiment, not an exact replication of the authors' code.
