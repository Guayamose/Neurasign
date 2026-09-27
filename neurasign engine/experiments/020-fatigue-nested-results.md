# Experiment 020: nested DailySense fatigue improvements

Exploratory development evidence from **28 people and 357 daily answers**. Four outer participant folds evaluate the complete selection procedure; three inner participant folds choose models, ensembles and classification thresholds. The historical eight test people are excluded throughout.

Labels remain observed daily fatigue VAS ≥50 versus <50 and the original 0–100 rating. No middle ratings were removed. This evaluates daily fatigue, not instantaneous states or clinical fitness for duty.

## Classification

| Planned arm | Balanced accuracy | Person-weighted accuracy | Raw accuracy | Low recall | High recall | Within-person BA |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| training_constant | 50.0% | 59.4% | 59.4% | 0.0% | 100.0% | 50.0% |
| fixed_cardiac_extra5 | 66.7% | 67.3% | 67.5% | 63.7% | 69.7% | 61.4% |
| inner_selected | 63.7% | 63.8% | 64.1% | 63.4% | 64.1% | 61.1% |

## Regression

| Planned arm | MAE / 100 | RMSE | R² | Within ±10 |
| --- | ---: | ---: | ---: | ---: |
| training_constant | 19.822 | 23.647 | -0.013 | 26.3% |
| fixed_cardiac_extra5 | 18.862 | 23.192 | 0.025 | 32.3% |
| inner_selected | 18.496 | 23.769 | -0.024 | 37.3% |

## Interpretation and checks

- classification: selected balanced_accuracy 95% participant-bootstrap interval 55.85–71.72; paired selected-minus-fixed interval -10.32–3.64. Exploratory gate passed: False.
- regression: selected mae 95% participant-bootstrap interval 14.70–22.50; paired selected-minus-fixed interval -1.84–1.12. Exploratory gate passed: False.

Every arm covers all 357 eligible answers. The fixed cardiac ExtraTrees uses experiment 018 settings; improved candidates compare robust transforms, compact intact-channel physiology and preceding physiological baseline deviations. Thirty-six candidates across both targets, plus the fixed references and a deterministic diverse ensemble, were specified before fitting. Every transform requiring population statistics is fitted inside its training fold. No target history, identities, dates or other questionnaire answers enter the predictor matrix.

The DailySense publisher archives match their published MD5, but many nested signal files are damaged. Only individually CRC-valid channels were used; missing channels remain missing. In particular, most BVP files are unavailable. Sensor windows stop at 21:30 Asia/Tokyo on SignalDate; no later samples enter. Baselines use only earlier sensor days. The nested comparison does not establish transfer across devices or to live employee monitoring.

Historical test outcomes remain unchanged. These outer-fold scores are from a different cohort and must not be represented as a measured gain over experiment 018’s test score. Final development artifacts are saved with `production_enabled=False` and were not scored on the old test people.

## Reproduction

From `neurasign engine/`, after verified DailySense preparation:

```sh
.venv/bin/python scripts/run_fatigue_nested.py prepare
.venv/bin/python scripts/run_fatigue_nested.py run
.venv/bin/python scripts/run_fatigue_nested.py verify
.venv/bin/python scripts/run_fatigue_nested.py report
.venv/bin/python -m unittest discover -s tests -p test_fatigue_nested.py -v
```

The protocol is immutable, and completed or started runs refuse replacement. Verification independently recomputes outer metrics, training-only constants, label mappings, grouped exclusions and artifact predictions. Data, individual predictions and fitted artifacts remain ignored.

Source: [DailySense dataset](https://zenodo.org/records/10816004), CC BY 4.0.
