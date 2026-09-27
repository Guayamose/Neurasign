"""Render measured SWELL results with the source and evaluation limitations."""
import hashlib
import json
from pathlib import Path

from .training import save_json


def write_report(root: Path, report):
    output = root / "results/swell-v1"
    # The shared paired-change helper includes a CV-specific prose caption.
    # This experiment uses a fixed holdout; correct only that caption, preserving
    # all scores, predictions, selections and the frozen experiment protocol.
    if "reporting_correction" not in report:
        report["reporting_correction"] = {
            "original_report_sha256": hashlib.sha256((output / "report.json").read_bytes()).hexdigest(),
            "change": "Replaced inherited cross-validation bootstrap caution with fixed-holdout small-sample caution; no numerical changes."}
        for result in report["targets"].values():
            result["learned_change_vs_constant"]["caution"] = (
                "Exploratory bootstrap of five held-out participants. Small-sample descriptive range; "
                "not independent confirmation after multiple comparisons or per-prediction confidence.")
        save_json(output / "report.json", report)
    a = report["data_audit"]
    names = {"mental_effort": "Mental effort (RSME)", "mental_demand": "Mental demand",
             "physical_demand": "Physical demand", "temporal_demand": "Time pressure",
             "effort": "General effort", "perceived_performance": "Self-rated performance"}
    lines = ["# Experiment 005: SWELL physiological workbook", "",
        "The user-provided workbook was imported and evaluated separately from UNIVERSE. "
        "This is a completed offline research benchmark. No SWELL model was promoted into the application.", "",
        "## Dataset and applicable inputs", "",
        f"- Source: `{report['protocol']['workbook_name']}`; SHA-256 `{report['protocol']['workbook_sha256']}`.",
        f"- {a['source_rows']:,} minute rows, {a['source_columns']} columns and {len(a['participants'])} participants. "
        f"Rows represent {a['represented_hours']:.2f} hours, not necessarily uninterrupted recording.",
        f"- {a['labeled_minutes']:,} labeled minutes across {a['labeled_blocks']} person/condition blocks. "
        "Each questionnaire answer is repeated throughout its block; relaxation has no questionnaire labels.",
        f"- {a['usable_minutes']:,} minutes ({a['usable_hours']:.2f} hours) across {a['usable_blocks']} blocks retained with at least one physiological value. "
        f"{a['all_physiology_missing_labeled_minutes']} labeled minutes with all three physiological columns missing were excluded. "
        f"Only {a['complete_physiology_labeled_minutes']:,} labeled minutes contain all three physiological values.",
        "- Predictors: HR, RMSSD and SCL only. No questionnaire, participant ID, condition, block number, timestamp, camera, keyboard, mouse or Kinect measurement is a predictor.",
        "- Stress, emotion/affect, frustration and the combined NASA-TLX score were excluded as targets and predictors.", "",
        "| Input | Meaning in source | Missing across workbook |", "| --- | --- | ---: |"]
    for feature, meaning in (("HR", "Heart rate"), ("RMSSD", "Exported heart-variability feature"), ("SCL", "Skin conductance level")):
        lines.append(f"| {feature} | {meaning} | {100*a['missing_fraction_all_minutes'][feature]:.2f}% |")
    lines += ["", "The [authors' paper](https://www.cs.ru.nl/~skoldijk/Papers/ICMI%202014%20paper_final_cr.pdf) "
              "describes Mobi chest ECG and finger electrodes for skin conductance. "
              "These are not wrist-PPG/wrist-EDA measurements. The workbook contains precomputed minute summaries, "
              "so this benchmark does not validate our causal raw-signal extraction or transfer to consumer wrist devices.", "",
              "## Scale handling", "",
              "The five NASA-TLX subscales use workbook values on 0–10 scales. Performance is the supplied recoded self-rating; "
              "it is not objective productivity. Mental effort is an RSME rating, not UNIVERSE's ordinal 1–5 target. "
              f"It ranges from {a['target_ranges_observed']['mental_effort'][0]:g} to {a['target_ranges_observed']['mental_effort'][1]:g} in retained data, "
              f"with {a['mental_effort_above_10_blocks']} blocks above 10. "
              "The source questionnaire shows an RSME ruler extending to 150, while its exported values and the paper use different presentations. "
              "We preserve the workbook numbers and do not silently cap RSME at 10 or convert it into a five-level label. "
              "The correspondence between exported units and the questionnaire ruler remains a source-documentation limitation.", "",
              "Predictor values also retain source units. The importer does not guess a conversion from SCL/RMSSD into the application's canonical telemetry units.", "",
              "## Protocol", "",
              "A seeded participant split fixed 20 development people and five held-out people before model fitting. "
              "All model choices were completed on five participant-grouped development folds before scoring any held-out output. "
              "The five-person test was evaluated once. The protocol and selected settings are saved for review; the training command refuses to overwrite a completed test evaluation.", "",
              "Candidates: mean/median constants; Ridge with alpha 10 or 100; RBF SVR with C=1; "
              "absolute-loss histogram gradient boosting with 100 iterations, seven leaves and regularization. "
              "Learned models were tested with two profiles: the three native features, or native features plus differences from preceding relaxation references. "
              "Ten candidate configurations were compared for each of six targets.", "",
              "For each person/block and signal, a reference needs at least three valid relaxation minutes before work starts. "
              "The reference is their median; no labels, later relaxation data or other participants enter it. "
              "Missing reference features remain missing. This profile requires a preceding recorded relaxation period, which is a specific deployment requirement rather than universal personalization.", "",
              "Population imputation and scaling are fitted on training folds only. Every available training minute is used. "
              "Participants have equal total fitting weight, and blocks have equal weight within a participant. "
              "Error is calculated per minute before averaging within blocks and then people. "
              "One-point agreement and two-point agreement are reported explicitly; neither is a clinical correctness measure or probability of confidence.", "",
              f"Development people: {', '.join(report['protocol']['split']['development'])}. "
              f"Held-out people: {', '.join(report['protocol']['split']['test'])}.", "",
              "## Held-out results", "",
              "The learned model in this table is the best nonconstant candidate selected on development data. "
              "The constant is selected on the same development data. These comparisons remain visible even when the overall selection preferred a constant. "
              "All rows below use the same 431 eligible held-out minutes from 15 blocks and five people.", "",
              "| Target | Learned MAE | Constant MAE | Learned within ±1 point | Constant within ±1 point |",
              "| --- | ---: | ---: | ---: | ---: |"]
    for target, result in report["targets"].items():
        learned, constant = result["heldout"]["learned"], result["heldout"]["constant"]
        lines.append(f"| {names[target]} | {learned['participant_macro_mae']:.4f} | {constant['participant_macro_mae']:.4f} | "
                     f"{100*learned['within_one_point_fraction']:.2f}% | {100*constant['within_one_point_fraction']:.2f}% |")
    lines += ["", "These scores are conditional on at least one physiological measurement being present. "
              "They are participant/block-weighted percentages, not a pooled count of independent minute labels. "
              "The same ±1 exported-point tolerance is used for RSME for transparency; it is not asserted to be 10% of that instrument's scale.", "",
              "### Personal-reference comparison", "",
              "Both profile-specific candidates below were selected before test scoring. Lower MAE is better.", "",
              "| Target | Native-profile MAE | Prior-rest-profile MAE | Overall development choice |",
              "| --- | ---: | ---: | --- |"]
    for target, result in report["targets"].items():
        lines.append(f"| {names[target]} | {result['heldout']['native_learned']['participant_macro_mae']:.4f} | "
                     f"{result['heldout']['prior_rest_learned']['participant_macro_mae']:.4f} | {result['choices']['selected']['name']} |")
    lines += ["", "The learned models improve held-out mean error for time pressure and self-rated performance, "
              "but worsen it for the other four outputs. Every descriptive participant-bootstrap improvement range includes zero. "
              "Five held-out people provide limited precision; these results do not establish a reliable six-output interpreter. "
              "Personal-reference features do not yield a consistent improvement across outputs.", "",
              "Overall development selection chose learned models for mental effort and mental demand, and constants for the other four. "
              "The two selected learned models lose to their constant comparators on this test. "
              "The better test results for two other learned outputs cannot be used to retroactively change the frozen selection and still call the same test independent.", "",
              "## Artifacts and verification", "",
              "`results/swell-v1/` holds the import audit, development scores, frozen choices, detailed test metrics and 30 prediction tables. "
              "`models/swell-v1-research.joblib` contains the heads chosen before test scoring, trained on development participants only. "
              "All recordings, the user workbook, prepared data, results and models are ignored by Git. "
              "The original workbook and UNIVERSE engine remain unchanged.", "",
              "```bash", ".venv/bin/python -m unittest discover -s tests -p 'test_swell.py' -v",
              ".venv/bin/python scripts/train_swell.py", ".venv/bin/python scripts/verify_swell.py", "```", "",
              f"Recorded experiment time: {report['elapsed_seconds']:.1f} seconds. "
              "The workbook was read directly with the Python standard library; no spreadsheet macros or formulas were executed.", "",
              "## Source and usage", "",
              "Koldijk, Sappelli, Verberne, Neerincx and Kraaij (2014), *The SWELL Knowledge Work Dataset for Stress and User Modeling Research*. "
              "[Official dataset record](https://doi.org/10.17026/dans-x55-69zp). "
              "The publisher lists **CC-BY-NC-SA-4.0**. This experiment is research-only and is not permission to deploy the dataset or derived artifact commercially. "
              "The user-supplied workbook is the training source; separately downloaded source documentation and the published physiology CSV are references, not replacement training rows.", ""]
    (root / "experiments/005-swell-results.md").write_text("\n".join(lines))
