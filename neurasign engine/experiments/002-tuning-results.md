# Development-only representation and model search

Status: completed offline exploratory experiment; no live deployment.

Only the original 19 development participants were used: 34,040 windows and 467 labeled intervals. The original five test participants were excluded before feature analysis, model selection and evaluation.

## What changed

Each questionnaire interval contributes one row. Candidate representations are the means of ten physiological features, or their mean, median, standard deviation and 10th/90th percentiles (50 features). No task identity, duration, participant identity or answers enter predictors.

The fixed search includes ridge regularization, RBF support-vector regression, shallow gradient boosting with squared/absolute loss, and extra trees. Participant-weighted mean and median constants are eligible to win. Targets retain their original scales; internal 0–1 scaling uses those declared scale bounds, not population statistics.

## Evaluation

Five outer participant folds evaluate the entire selection procedure. Three inner participant folds choose models and representations using only each outer training partition. All learned preprocessing stays inside fitting folds. The original window-level ridge/boosting procedure is reselected within the same inner folds for a matched comparison. Every score below averages interval errors within participant, then across participants; lower is better.

These are development nested-validation scores, not the first experiment's five-person test scores. Do not compare the numbers across those two populations.

| Output | Original procedure MAE | Tuned procedure MAE | Constant procedure MAE | Change vs original |
| --- | ---: | ---: | ---: | ---: |
| mental_effort | 0.891 | 0.869 | 0.881 | +0.022 |
| mental_demand | 23.946 | 24.273 | 24.471 | -0.327 |
| physical_demand | 22.882 | 19.009 | 19.010 | +3.874 |
| temporal_demand | 28.167 | 26.316 | 27.597 | +1.851 |
| perceived_performance | 20.817 | 21.066 | 20.623 | -0.249 |
| effort | 20.946 | 20.920 | 20.915 | +0.027 |

Positive change means lower MAE. A tuned procedure may choose a constant: that is not evidence that physiology predicts the target.

## Stability and final fit

| Output | People improved vs original | Descriptive 95% interval for MAE reduction | Final candidate |
| --- | ---: | --- | --- |
| mental_effort | 10/19 | -0.087 to +0.131 | constant_median |
| mental_demand | 8/19 | -1.993 to +1.505 | distribution_svr_1 |
| physical_demand | 11/19 | +0.985 to +6.777 | constant_median |
| temporal_demand | 14/19 | +0.021 to +3.558 | distribution_svr_10 |
| perceived_performance | 7/19 | -0.734 to +0.254 | distribution_boost_absolute_error |
| effort | 8/19 | -0.512 to +0.604 | distribution_svr_1 |

Bootstrap intervals resample participant errors and are descriptive only: folds share training participants, and this is a follow-up exploratory study. They are not confirmatory significance tests.

Point-estimate MAE improves over the original procedure for 4/6 outputs. For 6/6 outputs, the descriptive range for improvement over the constant procedure includes zero. Retain this experiment for research; these results do not establish a clear physiological prediction benefit. In particular, lower errors obtained by selecting a constant do not demonstrate signal interpretation.

A final five-fold search across all 19 development participants selects each persisted head. Its tuning score is not an independent evaluation of that exact fitted artifact. No original test participants are included in any persisted model.

## Limits and next evidence

- Complete-interval aggregation requires the interval to finish and know its boundaries. It cannot be substituted for a live rolling window.
- Published source features already include noncausal processing. This experiment tests an offline representation hypothesis, not real-time performance.
- Only 19 development people constrain generalization. More models cannot create missing physiological information or finer-grained ground truth.
- Ratings remain self-reports, not observed states, productivity, fatigue or diagnoses. Emotion/mental-health outputs and the composite containing frustration remain excluded.
- Future live work needs causal signal extraction, timestamped references and evaluation on new participants/devices; the already inspected five-person test cannot become fresh evidence.

## Reproduce

```bash
.venv/bin/python scripts/tune_multioutput.py
```

The versioned protocol is `002-tuning-protocol.json`. Detailed fold predictions, search scores and hashes are in ignored `results/multioutput-v2/`. The separate research artifact is `models/multioutput-v2-interval-research.joblib`; v1 remains unchanged.

Method references: [nested model selection](https://scikit-learn.org/stable/auto_examples/model_selection/plot_nested_cross_validation_iris.html), [participant groups](https://scikit-learn.org/stable/modules/cross_validation.html#cross-validation-iterators-for-grouped-data).
