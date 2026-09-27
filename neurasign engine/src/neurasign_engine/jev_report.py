"""Score saved Jev replies and retain historical protocols as separate tables."""
from collections import Counter
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .jev_benchmark import KEYS, MODEL, MODES, NAMES, digest, metrics, parse_answer, prepare
from .schema import TARGETS, SEED
from .training import save_json, weights


def paired_change(rows, target, first, second):
    d = rows[KEYS].copy()
    d["reduction"] = abs(rows[target]-rows[second])-abs(rows[target]-rows[first])
    people = d.groupby(["participant", "unit_id"]).reduction.mean().groupby("participant").mean()
    boot = np.random.default_rng(SEED).choice(people.to_numpy(), size=(5000, len(people)), replace=True).mean(axis=1)
    return {"mae_reduction": float(people.mean()), "descriptive_95_percent_range": np.quantile(boot, [.025, .975]).tolist(),
            "participants_improved": int((people > 0).sum()), "participants": len(people),
            "caution": "Descriptive participant bootstrap, not calibrated confidence or a new independent validation; shared-training CV folds for UNIVERSE and only five SWELL people."}


def historical(root):
    """Recompute comparable percentage definitions, without pooling protocols."""
    rows = []
    for version in ("multioutput-v1", "multioutput-v2", "causal-v3", "swell-v1"):
        report = json.loads((root / "results" / version / "report.json").read_text())
        for target in TARGETS:
            if version == "multioutput-v1":
                data = pd.read_csv(root / f"results/{version}/{target}-heldout-units.csv")
                roles = {"selected": "prediction"}
            elif version == "multioutput-v2":
                data = pd.read_csv(root / f"results/{version}/{target}-nested-predictions.csv")
                roles = {"selected": "tuned", "original_procedure": "original", "constant": "constant"}
            elif version == "causal-v3":
                data = pd.read_csv(root / f"results/{version}/{target}-predictions.csv.gz")
                roles = {name: name for name in ("selected", "learned", "constant")}
            else:
                roles = {name: "prediction" for name in ("selected", "learned", "constant", "native_learned", "prior_rest_learned")}
            for role, column in roles.items():
                if version == "swell-v1":
                    data = pd.read_csv(root / f"results/{version}/{target}__{role}.csv.gz")
                dataset = "swell" if version == "swell-v1" else "universe"
                score = metrics(data, target, data[column], dataset)
                rows.append({"experiment": version, "dataset": dataset, "method": role, "target": target, **score})
                if version == "causal-v3":
                    expected = report["targets"][target][role]["participant_macro_mae"]
                elif version == "multioutput-v1":
                    expected = report["targets"][target]["test"]["participant_macro_mae"]
                elif version == "multioutput-v2":
                    expected = report["targets"][target][column]["participant_macro_mae"]
                else:
                    expected = report["targets"][target]["heldout"][role]["participant_macro_mae"]
                assert abs(score["mae"]-expected) < 1e-8
    audit = json.loads((root / "results/information-v4/ablation.json").read_text())
    for target, variants in audit["targets"].items():
        for name, result in variants.items():
            percent = result["weighted_exact_level_accuracy"] if target == "mental_effort" else result["within_tolerance_fraction"]
            rows.append({"experiment": "information-v4", "dataset": "universe", "method": name, "target": target,
                         "mae": result["participant_macro_mae"], "agreement_percent": 100*percent,
                         "rows": result["windows"], "blocks": result["units"], "participants": result["participants"]})
    return rows


def score(root):
    protocol = prepare(root)
    output = root / "results/jev-v1"
    index = pd.read_csv(output / "request-index.csv")
    replies = [json.loads(line) for line in (output / "responses.jsonl").read_text().splitlines()]
    assert len({r["request_id"] for r in replies}) == len(replies)
    assert {r["request_id"] for r in replies} == set(index.request_id)
    replies = {r["request_id"]: r for r in replies}
    report = {"protocol": protocol, "datasets": {}, "usage": {}, "failures": [],
              "responses_sha256": digest(output / "responses.jsonl"), "reporter_sha256": digest(__file__)}
    flat = []
    for dataset in ("universe", "swell"):
        report["datasets"][dataset] = {}
        for target in TARGETS:
            data = pd.read_csv(output / f"{dataset}-{target}-local.csv.gz")
            local_columns = [c for c in data if c not in KEYS + [target]]
            for mode in MODES:
                preds = []
                for _, record in index[(index.dataset == dataset) & (index["mode"] == mode)].iterrows():
                    reply = replies[record.request_id]
                    try:
                        prediction, confidence = parse_answer(reply.get("response", {}), dataset, target)
                        reason = None
                    except (ValueError, KeyError, TypeError, OverflowError):
                        prediction, confidence, reason = np.nan, np.nan, "invalid_or_missing_answer"
                        report["failures"].append({"request_id": record.request_id, "target": target, "reason": reason})
                    preds.append({**{k: record[k] for k in KEYS}, mode: prediction, mode+"_confidence": confidence})
                data = data.merge(pd.DataFrame(preds), on=KEYS, validate="one_to_one")
            assert len(data) > 0
            data.to_csv(output / f"{dataset}-{target}-predictions.csv.gz", index=False)
            complete = data.dropna(subset=list(MODES)).copy()
            result = {"eligible_rows": len(data), "paired_rows": len(complete), "coverage": {}, "metrics": {}, "comparisons": {}}
            for mode in MODES:
                available = data[mode].notna()
                result["coverage"][mode] = {"valid_rows": int(available.sum()), "eligible_rows": len(data),
                    "weighted_percent": float(np.average(available, weights=weights(data))*100)}
                valid = data[available]
                result["coverage"][mode]["mean_internal_confidence"] = float(np.average(valid[mode+"_confidence"], weights=weights(valid))) if len(valid) else None
            if len(complete):
                for method in local_columns + list(MODES):
                    value = metrics(complete, target, complete[method], dataset)
                    result["metrics"][method] = value
                    flat.append({"experiment": "jev-v1-matched", "dataset": dataset, "method": method, "target": target, **value})
                for mode in MODES:
                    for baseline in ("constant", "learned"):
                        result["comparisons"][f"{mode}_vs_{baseline}"] = paired_change(complete, target, mode, baseline)
            report["datasets"][dataset][target] = result
    for dataset in ("universe", "swell"):
        for mode in MODES:
            values = [r for key, r in replies.items() if key.startswith(dataset+":") and key.endswith(":"+mode)]
            latency = [r["elapsed_seconds"] for r in values]
            token_usage = {name: sum(r.get("response", {}).get("usage", {}).get(name, 0) for r in values)
                           for name in ("input_tokens", "output_tokens")}
            report["usage"][dataset+":"+mode] = {"requests": len(values), "received": sum(r["status"] == "received" for r in values),
                "attempts": sum(len(r["attempts"]) for r in values),
                "models": dict(Counter(r.get("response", {}).get("model", "none") for r in values)),
                "latency_median_seconds": float(np.median(latency)), "latency_p95_seconds": float(np.quantile(latency, .95)),
                **token_usage}
    report["transport_attempt_statuses"] = dict(Counter(str(a.get("http_status", a.get("error_type"))) for r in replies.values() for a in r["attempts"]))
    report["input_tokens"] = sum(v["input_tokens"] for v in report["usage"].values())
    report["estimated_list_price_usd"] = report["input_tokens"] * .042 / 1_000_000
    report["price_source"] = "https://docs.typesafe.ai/models ; $0.042 per million input tokens, outputs free, checked 2026-09-26; estimate, not invoice; excludes connectivity probe and unknown failed-request billing."
    history = historical(root)
    pd.DataFrame(flat).to_csv(output / "matched-comparison.csv", index=False)
    pd.DataFrame(history + flat).to_csv(output / "all-experiments.csv", index=False)
    report["historical_report_sha256"] = {p: digest(root / p) for p in [
        "results/multioutput-v1/report.json", "results/multioutput-v2/report.json", "results/causal-v3/report.json",
        "results/information-v4/ablation.json", "results/swell-v1/report.json"]}
    save_json(output / "report.json", report)
    write_markdown(root, report, history)
    return report


def table(lines, records, methods):
    columns = ["mental_effort", "mental_demand", "physical_demand", "temporal_demand", "effort", "perceived_performance"]
    lines += ["| Method | Mental effort | Mental demand | Physical demand | Time pressure | General effort | Self-rating |",
              "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for method, label in methods:
        values = {r["target"]: r for r in records if r["method"] == method}
        lines.append("| " + label + " | " + " | ".join(f"{values[t]['agreement_percent']:.2f}%" if t in values else "n/a" for t in columns) + " |")


def write_markdown(root, report, history):
    output = root / "results/jev-v1"
    matched = pd.read_csv(output / "matched-comparison.csv").to_dict("records")
    lines = ["# Experiment 006: real Jev dataset benchmark", "",
        f"Completed {report['protocol']['requests']:,} real requests to pinned `{MODEL}`: two frozen prompt variants across 472 UNIVERSE windows and 431 SWELL minutes. "
        "The connectivity probe is excluded. No synthetic responses or local fallbacks were used. No model or heuristic was promoted into the app.", "",
        "## Reading the numbers", "",
        "Agreement means **exact rounded level** for UNIVERSE mental effort (1–5), **within ±10 points** for its five 0–100 ratings, "
        "and **within ±1 native workbook point** for SWELL. These tolerances are not interchangeable definitions of correctness, "
        "and 100 minus MAE is not accuracy. All percentages here give equal weight to people, then questionnaire blocks, then observations. "
        "Historical v1/v2 mental-effort percentages have been recomputed with this weighting and can differ from their earlier pooled percentages.", "",
        "A constant predicts a training-set mean or median without using the current physiology. A learned model is selected from nonconstant candidates "
        "using training participants. 'Selected procedure' allows constants to win. Jev zero-shot uses measurements and definitions; eight-shot additionally "
        "receives eight labeled windows from eight different training people. This is in-context prompting, not training Jev's weights.", "",
        "## Interpretation of this run", "",
        "Both Jev variants have higher mean absolute error than the constant comparator for all six UNIVERSE outputs. "
        "Eight examples improve several agreement percentages, but do not establish useful physiological inference. "
        "For example, eight-shot time-pressure agreement is 33.98% versus the constant's 14.44%, while its MAE is worse: "
        "33.86 versus 27.61 points. A tolerance percentage alone hides the size of errors outside the tolerance.", "",
        "In SWELL, eight-shot physical demand is the clearest exploratory improvement: 65.29% within one point and MAE 1.44, "
        "versus 53.33% and MAE 1.75 for the constant. The descriptive participant-bootstrap MAE improvement range is "
        "approximately 0.02–0.61 points, based on only five people and without adjustment for multiple comparisons. "
        "Other outputs and prompt variants are mixed. This is a hypothesis to replicate, not validated general-purpose live interpretation. "
        "No prompt was changed after inspecting these results.", "",
        "## Direct comparison: same observations", ""]
    for dataset in ("universe", "swell"):
        lines += ["### " + dataset.upper(), ""]
        lines += [("One middle available causal window from each of 472 questionnaire intervals, 19 development people. Mental-effort labels exist for 338 windows. "
                   "Local predictions are the existing out-of-fold v3 predictions at exactly these instants. Entire corresponding outer validation folds were excluded from Jev examples. "
                   "This is a previously inspected development benchmark, not a fresh final test.")
                  if dataset == "universe" else
                  ("All 431 eligible held-out minutes from 15 blocks and five people. Jev examples come only from the original 20 development people. "
                   "All current physiological features and available differences from preceding rest are provided. This is a previously inspected test benchmark. "
                   "Chest ECG and finger EDA, precomputed offline, do not establish transfer to live wrist devices."), ""]
        methods = [("constant", "Constant comparator"), ("selected", "Local selected procedure"), ("learned", "Local learned procedure")]
        if dataset == "swell":
            methods += [("native_learned", "Local native features"), ("prior_rest_learned", "Local with prior-rest differences")]
        methods += [("zero_shot", "Jev: no examples"), ("eight_shot", "Jev: eight examples")]
        table(lines, [r for r in matched if r["dataset"] == dataset], methods)
        lines += ["", "Mean absolute errors on the original numeric scales:", "",
                  "| Target | Constant | Local learned | Jev: no examples | Jev: eight examples |",
                  "| --- | ---: | ---: | ---: | ---: |"]
        for target, result in report["datasets"][dataset].items():
            values = result["metrics"]
            lines.append("| " + NAMES[target] + " | " + " | ".join(f"{values[m]['mae']:.4f}" if m in values else "n/a" for m in ("constant", "learned", "zero_shot", "eight_shot")) + " |")
        lines += [""]
    lines += ["## Historical experiments: separate evaluation protocols", "",
              "These rows describe earlier complete evaluations, **not** a fair leaderboard against the sampled UNIVERSE Jev run. "
              "V1 uses five original test people and offline feature processing; v2 uses nested folds of 19 development people and complete-task summaries; "
              "v3 uses individual causal windows from those 19 development people. V1/v2 average predictions across tasks before scoring; v3 scores each window before averaging errors.", ""]
    historical_rows = []
    for experiment in ("multioutput-v1", "multioutput-v2", "causal-v3"):
        for row in history:
            if row["experiment"] == experiment:
                historical_rows.append({**row, "method": experiment+"/"+row["method"]})
    table(lines, historical_rows, [
        ("multioutput-v1/selected", "V1: published offline features (Ridge / boosting)"),
        ("multioutput-v2/selected", "V2: full-task tuning, selected procedure"),
        ("multioutput-v2/constant", "V2: constant comparator"),
        ("causal-v3/selected", "V3: all windows, selected procedure"),
        ("causal-v3/learned", "V3: all windows, learned procedure"),
        ("causal-v3/constant", "V3: all windows, constant comparator")])
    lines += ["", "### All information-audit variants", "",
              "Fixed Ridge/boosting diagnostic models, five participant folds, all v3 validation windows. "
              "Variants were diagnostic comparisons, not independently validated winners. Native IBI was inventoried only; it has no trained-model score.", ""]
    variants = sorted({r["method"] for r in history if r["experiment"] == "information-v4"})
    table(lines, [r for r in history if r["experiment"] == "information-v4"], [(x, x) for x in variants])
    lines += ["", "## Method inventory", "",
        "- V1: Ridge and histogram gradient boosting against a mean constant.",
        "- V2: 18 configurations across mean/median constants, Ridge, RBF SVR, histogram gradient boosting and Extra Trees; task means or 50 task statistics.",
        "- V3: eight configurations: constants, Ridge, histogram gradient boosting and a 32/16-unit neural network; causal wrist features.",
        "- Information audit: fixed Ridge and boosting with all training windows, relaxed quality gates and individual signal removals; 132 target/configuration results.",
        "- SWELL: ten configurations across constants, Ridge, RBF SVR and boosting; native physiology or added preceding-rest differences.",
        "- Jev: two fixed prompts, zero-shot and eight-shot. No fine-tuning or test-driven prompt search.",
        "- Demo formulas, Gemini, native IBI model and additional external datasets: no corresponding label-accuracy benchmark completed; no percentage claimed.", "",
        "Candidate-selection MAEs remain in each experiment's original development/fold reports. "
        "The tables report evaluated selection procedures or explicitly fixed models; they do not invent independent accuracies for every candidate tried during tuning.", "",
        "## API operation and verification", "",
        "| Dataset / prompt | Requests | Responses | Median latency | P95 latency | Input tokens |",
        "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for name, use in report["usage"].items():
        lines.append(f"| {name} | {use['requests']} | {use['received']} | {use['latency_median_seconds']:.3f} s | {use['latency_p95_seconds']:.3f} s | {use['input_tokens']:,} |")
    lines += ["", f"Input tokens: {report['input_tokens']:,}. Estimated list-price cost: ${report['estimated_list_price_usd']:.4f}, "
              "using the [documented price](https://docs.typesafe.ai/models) checked on 2026-09-26; this is not an invoice. "
              f"Invalid/missing target answers: {len(report['failures'])}. The machine-readable report includes coverage, paired comparisons and internal confidence, which is not physiological accuracy.", "",
              "All six questions are sent together. Jev selects explicit rating categories (UNIVERSE 0–100 step10 or effort 1–5; SWELL 0–10 step1 or RSME 0–15 step1). "
              "No arithmetic interpolation of probability scores is used. Local models retain their continuous predictions. "
              "The provider [documents limitations with numeric precision](https://docs.typesafe.ai/model-jaggedness/jev-1.13); "
              "this experiment tests two specific physiological prompts, not every possible use of Jev.", "",
              "Payloads contain physiological features and measurement definitions only, plus optional training examples. "
              "Current labels, task names, conditions, participant IDs and timestamps are excluded. API credentials are read only into the authorization header, "
              "never saved into artifacts. Requests, responses, datasets and models remain Git-ignored. "
              "Prompts, sampling, mappings, source hashes and comparator predictions were frozen before calls. "
              "Transport failures never become fallback predictions. Quantization, missingness and task-level weak labels limit interpretation.", "",
              "UNIVERSE performance direction remains unverified; the prompt explicitly avoids asserting that higher means better. "
              "SWELL RSME and physiological exports retain their original units. SWELL's research-only source license remains applicable. "
              "Public-dataset exposure during provider pretraining cannot be ruled out. Neither benchmark validates real employees, instantaneous mental states, diagnoses or device compatibility.", "",
              "```bash", ".venv/bin/python scripts/benchmark_jev.py --prepare-only",
              ".venv/bin/python scripts/benchmark_jev.py", ".venv/bin/python scripts/report_jev.py",
              ".venv/bin/python scripts/verify_jev.py", "```", "",
              "Saved outputs: `results/jev-v1/report.json`, `matched-comparison.csv`, `all-experiments.csv`, "
              "per-target predictions, frozen request manifest and original API responses. "
              "The original engine, models, splits and prior reports are unchanged.", ""]
    (root / "experiments/006-jev-results.md").write_text("\n".join(lines))
