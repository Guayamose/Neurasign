# Experiment 005: SWELL physiological workbook

The user-provided workbook was imported and evaluated separately from UNIVERSE. This is a completed offline research benchmark. No SWELL model was promoted into the application.

## Dataset and applicable inputs

- Source: `Behavioral-features - per minute (1).xlsx`; SHA-256 `9ae1fc82569e9b16f363fb8b0106c859422a6a379ac577b4e8268f51cf20a044`.
- 3,139 minute rows, 172 columns and 25 participants. Rows represent 52.32 hours, not necessarily uninterrupted recording.
- 2,688 labeled minutes across 75 person/condition blocks. Each questionnaire answer is repeated throughout its block; relaxation has no questionnaire labels.
- 2,197 minutes (36.62 hours) across 73 blocks retained with at least one physiological value. 491 labeled minutes with all three physiological columns missing were excluded. Only 1,221 labeled minutes contain all three physiological values.
- Predictors: HR, RMSSD and SCL only. No questionnaire, participant ID, condition, block number, timestamp, camera, keyboard, mouse or Kinect measurement is a predictor.
- Stress, emotion/affect, frustration and the combined NASA-TLX score were excluded as targets and predictors.

| Input | Meaning in source | Missing across workbook |
| --- | --- | ---: |
| HR | Heart rate | 52.53% |
| RMSSD | Exported heart-variability feature | 52.53% |
| SCL | Skin conductance level | 17.87% |

The [authors' paper](https://www.cs.ru.nl/~skoldijk/Papers/ICMI%202014%20paper_final_cr.pdf) describes Mobi chest ECG and finger electrodes for skin conductance. These are not wrist-PPG/wrist-EDA measurements. The workbook contains precomputed minute summaries, so this benchmark does not validate our causal raw-signal extraction or transfer to consumer wrist devices.

## Scale handling

The five NASA-TLX subscales use workbook values on 0–10 scales. Performance is the supplied recoded self-rating; it is not objective productivity. Mental effort is an RSME rating, not UNIVERSE's ordinal 1–5 target. It ranges from 1.3 to 11.3 in retained data, with 5 blocks above 10. The source questionnaire shows an RSME ruler extending to 150, while its exported values and the paper use different presentations. We preserve the workbook numbers and do not silently cap RSME at 10 or convert it into a five-level label. The correspondence between exported units and the questionnaire ruler remains a source-documentation limitation.

Predictor values also retain source units. The importer does not guess a conversion from SCL/RMSSD into the application's canonical telemetry units.

## Protocol

A seeded participant split fixed 20 development people and five held-out people before model fitting. All model choices were completed on five participant-grouped development folds before scoring any held-out output. The five-person test was evaluated once. The protocol and selected settings are saved for review; the training command refuses to overwrite a completed test evaluation.

Candidates: mean/median constants; Ridge with alpha 10 or 100; RBF SVR with C=1; absolute-loss histogram gradient boosting with 100 iterations, seven leaves and regularization. Learned models were tested with two profiles: the three native features, or native features plus differences from preceding relaxation references. Ten candidate configurations were compared for each of six targets.

For each person/block and signal, a reference needs at least three valid relaxation minutes before work starts. The reference is their median; no labels, later relaxation data or other participants enter it. Missing reference features remain missing. This profile requires a preceding recorded relaxation period, which is a specific deployment requirement rather than universal personalization.

Population imputation and scaling are fitted on training folds only. Every available training minute is used. Participants have equal total fitting weight, and blocks have equal weight within a participant. Error is calculated per minute before averaging within blocks and then people. One-point agreement and two-point agreement are reported explicitly; neither is a clinical correctness measure or probability of confidence.

Development people: PP1, PP10, PP11, PP12, PP13, PP14, PP15, PP17, PP18, PP19, PP2, PP20, PP22, PP23, PP24, PP25, PP3, PP4, PP6, PP7. Held-out people: PP16, PP21, PP5, PP8, PP9.

## Held-out results

The learned model in this table is the best nonconstant candidate selected on development data. The constant is selected on the same development data. These comparisons remain visible even when the overall selection preferred a constant. All rows below use the same 431 eligible held-out minutes from 15 blocks and five people.

| Target | Learned MAE | Constant MAE | Learned within ±1 point | Constant within ±1 point |
| --- | ---: | ---: | ---: | ---: |
| Mental effort (RSME) | 2.9174 | 2.6600 | 16.89% | 6.67% |
| Mental demand | 2.7568 | 2.4386 | 5.41% | 6.67% |
| Physical demand | 1.9852 | 1.7533 | 39.99% | 53.33% |
| Time pressure | 1.7502 | 1.8733 | 49.91% | 26.67% |
| General effort | 2.4846 | 2.0667 | 16.77% | 26.67% |
| Self-rated performance | 1.9077 | 2.0778 | 36.83% | 13.33% |

These scores are conditional on at least one physiological measurement being present. They are participant/block-weighted percentages, not a pooled count of independent minute labels. The same ±1 exported-point tolerance is used for RSME for transparency; it is not asserted to be 10% of that instrument's scale.

### Personal-reference comparison

Both profile-specific candidates below were selected before test scoring. Lower MAE is better.

| Target | Native-profile MAE | Prior-rest-profile MAE | Overall development choice |
| --- | ---: | ---: | --- |
| Mental effort (RSME) | 2.6956 | 2.9174 | prior_rest_ridge_100 |
| Mental demand | 2.7568 | 2.5850 | native_ridge_10 |
| Physical demand | 1.9852 | 1.8864 | constant_median |
| Time pressure | 1.7502 | 1.8918 | constant_median |
| General effort | 2.0903 | 2.4846 | constant_median |
| Self-rated performance | 1.9077 | 2.2776 | constant_mean |

The learned models improve held-out mean error for time pressure and self-rated performance, but worsen it for the other four outputs. Every descriptive participant-bootstrap improvement range includes zero. Five held-out people provide limited precision; these results do not establish a reliable six-output interpreter. Personal-reference features do not yield a consistent improvement across outputs.

Overall development selection chose learned models for mental effort and mental demand, and constants for the other four. The two selected learned models lose to their constant comparators on this test. The better test results for two other learned outputs cannot be used to retroactively change the frozen selection and still call the same test independent.

## Artifacts and verification

`results/swell-v1/` holds the import audit, development scores, frozen choices, detailed test metrics and 30 prediction tables. `models/swell-v1-research.joblib` contains the heads chosen before test scoring, trained on development participants only. All recordings, the user workbook, prepared data, results and models are ignored by Git. The original workbook and UNIVERSE engine remain unchanged.

```bash
.venv/bin/python -m unittest discover -s tests -p 'test_swell.py' -v
.venv/bin/python scripts/train_swell.py
.venv/bin/python scripts/verify_swell.py
```

Recorded experiment time: 16.2 seconds. The workbook was read directly with the Python standard library; no spreadsheet macros or formulas were executed.

## Source and usage

Koldijk, Sappelli, Verberne, Neerincx and Kraaij (2014), *The SWELL Knowledge Work Dataset for Stress and User Modeling Research*. [Official dataset record](https://doi.org/10.17026/dans-x55-69zp). The publisher lists **CC-BY-NC-SA-4.0**. This experiment is research-only and is not permission to deploy the dataset or derived artifact commercially. The user-supplied workbook is the training source; separately downloaded source documentation and the published physiology CSV are references, not replacement training rows.
