"""Render the measured v4 audit without choosing a winning model after evaluation."""
from pathlib import Path
import json

from .information_audit import VARIANTS
from .schema import TARGETS


def write_information_report(root: Path, report):
    q, a = report["quality"], report["ablation"]["targets"]
    c = q["counts"]
    names = {"v3_gates": "Original gates, 20 windows/task", "all_training_windows": "All training windows",
             "relax_motion": "Ignore motion gate", "relax_motion_periodicity": "Ignore motion + periodicity gates",
             "without_eda": "Remove EDA", "without_temperature": "Remove temperature",
             "without_motion": "Remove acceleration", "without_device_hr": "Remove device HR",
             "without_pulse_wave": "Remove all pulse-wave features", "without_pulse_intervals": "Remove pulse intervals"}
    lines = ["# Experiment 004: useful-information audit", "",
        "This is a completed development diagnostic, not a new production model or an independent confirmation of accuracy.", "",
        "## Measured findings", "",
        "- Fitting all available windows changes errors only slightly with the two fixed models. It does not establish a reliable six-output interpreter.",
        "- Relaxing pulse gates recovers numerical features but does not produce a consistent error reduction across targets and models.",
        "- Removing acceleration increases physical-demand error by 1.28 points for the linear model and 1.33 points for the trees. "
        "This is evidence of a useful contribution in these models, although their full physical-demand predictions still lose to the median constant.",
        "- Removing temperature improves some outputs and worsens mental demand. Channel usefulness is target-dependent; no global channel deletion is justified by this comparison.",
        "- The audit tests these particular extracted features and models. It does not prove that the raw recordings contain no further predictive information.", "",
        "## Labels and actual recording duration", "",
        "Every window already inherits the questionnaire rating of its source task. The audit verifies that ratings are constant within each task. "
        "This supports weakly supervised window prediction; it cannot measure within-task transition timing against an instantaneous reference that was never recorded.", "",
        f"- {c['windows']:,} overlapping windows from {c['intervals']} questionnaire intervals and {c['participants']} development participants.",
        f"- Source segments cover **{c['development_labeled_signal_hours']:.3f} hours**; accepted window coverage is **{c['window_union_hours']:.3f} hours**.",
        f"- Summing all 60-second windows would incorrectly count **{c['naive_sum_overlapping_window_hours']:.3f} hours** because windows overlap.",
        f"- The previous 20-window-per-task fitting sample has {c['v3_fitting_windows_before_target_mask']:,} windows covering "
        f"{c['v3_fitting_window_union_hours_before_target_mask']:.3f} source hours before target-specific missing-label masking. "
        "The audit compares this sample with fitting every available labeled window.",
        "- Source-clock intervals are merged within participant/session; the five original test people remain excluded.", "",
        "| Session | Accepted coverage, hours | Windows | Pulse intervals available |", "| --- | ---: | ---: | ---: |"]
    for name, info in c["by_session"].items():
        lines.append(f"| {name} | {info['window_union_hours']:.3f} | {info['windows']:,} | {100*info['pulse_available_fraction']:.2f}% |")
    lines += ["", "Hours supply physiological variation; they do not create extra independently rated tasks or additional people. "
              "Both the duration and the number of independent people matter. These diagnostics do not establish a sample-size ceiling.", "",
              "## Pulse masking and signal checks", "",
              "The earlier extraction considered 41,205 windows, rejected 12 for gaps, and removed 124 duplicated recording instants. "
              "It did not reject half the recordings. On the final 41,069 rows, seven pulse-related features are missing in 20,344 windows (49.536%); "
              "the remaining 36 features are present. Counts from the earlier audit include pre-deduplication rows and therefore differ slightly.", "",
              "| Diagnostic group | Windows | All windows | Median pulse/device-HR difference | Difference ≤10 bpm |",
              "| --- | ---: | ---: | ---: | ---: |"]
    for name, info in q["pulse_groups"].items():
        difference = info["device_hr_disagreement_median_bpm"]
        agreement = info["within_10_bpm_fraction"]
        lines.append(f"| {name} | {info['windows']:,} | {100*info['fraction']:.2f}% | " +
                     (f"{difference:.2f} bpm" if difference is not None else "n/a") + " | " +
                     (f"{100*agreement:.2f}%" if agreement is not None else "n/a") + " |")
    lines += ["", "Recovery groups overlap. Ignoring motion retains the periodicity and beat-count checks; ignoring both gates still requires "
              "at least 20 valid intervals and ≥80% of intervals between 300 and 2,000 ms. No production quality gate has been relaxed.", "",
              "Device HR is corroborating evidence from the same optical sensor, not independent ECG ground truth. "
              "A large difference suggests an unstable measurement; agreement alone cannot validate pulse-interval variability.", "",
              f"The audit flags {q['gate_counts']['clipping_gate']:,} windows for acceleration near its measurement limit, "
              f"{q['gate_counts']['dynamic_motion_gate']:,} for high acceleration variation, and "
              f"{q['gate_counts']['periodicity_gate']:,} for low pulse periodicity. These groups overlap. "
              f"EDA is flat within 0.001 µS across {q['gate_counts']['eda_flat']:,} windows. "
              f"Temperature is outside 30–40 °C for most samples in {q['gate_counts']['temperature_majority_outside_30_40']:,} windows. "
              "These are screening flags, not proof that every affected channel is unusable or that a participant has a physiological condition.", "",
              "Three source checks (UN_121/Lab2 arithmetic easy, UN_110/Lab2 N-back hard, UN_103/Lab2 arithmetic hard) "
              "match the full labeled BVP and acceleration sequences to original CSV samples exactly after reversing the counts-to-g conversion. "
              "High acceleration values are present in those original recordings. This rules out our conversion as their cause in those three cases; "
              "it does not identify the underlying device or recording problem. The ignored `native-acc-check.json` records positions and ranges.", "",
              "## Fixed-model ablations", "",
              "Five participant-disjoint folds, two fixed learned models, ten fixed input/training variants and two constant baselines. "
              "All variants receive the same validation windows and targets. Median imputation and scaling are fitted only on each training fold. "
              "Removing device HR also removes the derived pulse/HR difference to avoid retaining that signal indirectly. "
              "The all-window variant keeps total fitting weight unchanged to avoid silently changing L2 regularization strength.", "",
              "The metric is absolute error on each window, averaged within task, then participant, then across people. "
              "Mental effort uses 1–5; all other targets use 0–100. Smaller is better. These fixed-model results differ from v3's nested model-selection procedure.", ""]
    for model, title in (("ridge_100", "Regularized linear model"), ("boost_squared_7", "Gradient-boosted trees")):
        lines += [f"### {title}", "", "| Variant | Mental effort | Mental demand | Physical demand | Time pressure | Performance rating | Effort |",
                  "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
        for baseline in ("constant_mean", "constant_median"):
            scores = [a[t]["v3_gates/" + baseline]["participant_macro_mae"] for t in TARGETS]
            lines.append("| " + baseline.replace("_", " ") + " | " + " | ".join(f"{v:.4f}" for v in scores) + " |")
        for variant in VARIANTS:
            scores = [a[t][variant + "/" + model]["participant_macro_mae"] for t in TARGETS]
            lines.append("| " + names[variant] + " | " + " | ".join(f"{v:.4f}" for v in scores) + " |")
        lines.append("")
    native_path = root / "results/information-v4/native-ibi-inventory.json"
    if native_path.exists():
        native = json.loads(native_path.read_text())
        lines += ["## Additional source inventory: native beat intervals", "",
                  "After defining the ablation protocol, a separate source inventory checked original Empatica `IBI.csv` files. "
                  "This exploratory inventory does not change any ablation, target or fitted model.", "",
                  f"The 19 development participants have {native['files_considered']} native IBI files. "
                  f"{native['files_parsed']} passed strict parsing and contain **{native['observed_intervals']:,} observed beat intervals**; "
                  f"{native['files_excluded']} files contain embedded headers and were explicitly excluded rather than silently repaired. "
                  f"{native['files_with_gaps_over_60_seconds']} of the parsed files have interevent gaps longer than one minute. "
                  "These counts include unlabeled recording time and are not a measure of labeled-window coverage.", "",
                  "The current causal engine derives intervals from the BVP waveform; it does not consume these manufacturer intervals. "
                  "They are a concrete untested input, not a demonstrated accuracy improvement. A next experiment should align their native "
                  "clock to the verified BVP/task segments, compute variability only over valid consecutive beats without bridging gaps, "
                  "and compare coverage and held-out-person errors against the current detector. The same optical source means these intervals "
                  "are not independent ECG ground truth.", "",
                  "Reproduce with `.venv/bin/python scripts/audit_native_ibi.py`. Digests, file-level counts and exclusions are in ignored "
                  "`results/information-v4/native-ibi-inventory.json`.", ""]
    lines += ["All ablation settings were recorded before fitting in [the protocol](004-information-protocol.json). "
              "The comparisons are exploratory on reused development people. We report all variants, select no winner, "
              "and do not treat the best cell among many comparisons as independently established improvement. "
              "The machine-readable report includes paired participant changes and descriptive bootstrap ranges; these are not per-prediction confidence values.", "",
              "## Reproduce and inspect", "", "```bash", ".venv/bin/python scripts/audit_native_ibi.py",
              ".venv/bin/python scripts/audit_information.py",
              ".venv/bin/python scripts/verify_information_audit.py",
              ".venv/bin/python -m unittest discover -s tests -p 'test_information_audit.py' -v", "```", "",
              "Ignored artifacts under `results/information-v4/`: `report.json`, `quality.json`, `diagnostics.csv.gz`, "
              "`extraction.json`, `ablation.json`, and per-variant predictions. Raw-source digests are checked before loading. "
              "The unmasked pulse features are cross-checked against every corresponding v3 row. Runtime v3, its frozen data, trained artifact and dashboard are unchanged.", "",
              f"Measured run time: {report['elapsed_seconds']:.1f} seconds. No external training API was used.", "",
              "## Research references", "",
              "The [UNIVERSE paper](https://www.nature.com/articles/s41597-024-03738-7) reports 159.70 wrist-recording hours across all 24 people. "
              "Its signal-quality analysis reports BVP passing its own spectral-entropy check for 68.94% of lab and 51.18% of uncontrolled data. "
              "Its criteria and population differ from ours, so these figures cannot validate our gate. The authors also discuss fit/contact and possible sensor-cap issues. "
              "Neither observation establishes the cause of a particular local flagged window.", "",
              "[Empatica's raw-data specification](https://www.empatica.com/blog/decoding-wearable-sensor-signals-what-to-expect-from-your-e4-data/) "
              "confirms acceleration counts divided by 64 give g, and that its HR output averages 10-second spans. "
              "That smoothing is another reason detector/device-HR differences cannot be interpreted as independent measurement errors.", "",
              "The authors' [published classifier driver](https://github.com/HPI-CH/UNIVERSE/blob/0502dd32bfcb18d5960f8faa51a26f75ca4d6322/Machine%20learning/main_ml.py) "
              "includes EEG, per-person binary problems and full-participant label thresholds in its Wild example. Its "
              "[split implementation](https://github.com/HPI-CH/UNIVERSE/blob/0502dd32bfcb18d5960f8faa51a26f75ca4d6322/Machine%20learning/classification.py) "
              "uses shuffled KFold for the corresponding example. That setup is not evidence of six-target, wrist-only generalization to unseen people. "
              "We do not reproduce its affective composite target.", ""]
    (root / "experiments/004-information-results.md").write_text("\n".join(lines))
