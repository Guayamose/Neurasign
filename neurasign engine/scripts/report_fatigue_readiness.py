#!/usr/bin/env python3
"""Publish aggregate results from saved experiments 015/016 evidence, without fitting."""
from pathlib import Path
import json

ROOT=Path(__file__).resolve().parents[1]


def report_fatigue():
    lines=['# Experiment 015: FatigueSet wrist fatigue labels','',
           'Original [FatigueSet](https://www.esense.io/datasets/fatigueset/) wrist recordings and physical/mental fatigue VAS answers. '
           'Twelve people and 36 sessions supply 108 potential reference answers; 103 have sufficient wrist features. '
           'The classifier target is the fixed research midpoint: VAS ≥50 versus <50. No middle answers are discarded. '
           'This threshold is not a clinical definition of fatigue.','',
           'Nine people are used for development; three reserved people provide 27 answers for the single final evaluation. '
           'Fifty classifier/profile configurations per target compare logistic regression, RBF SVM, ExtraTrees and CatBoost. '
           'Four person-disjoint development folds select balanced accuracy; a top-three ensemble is also eligible. '
           'All choices are frozen before test scoring. Preprocessing is trained within each fold.','',
           'Inputs are E4 wrist BVP, HR, IBI, EDA, temperature and acceleration, with cardiac/autonomic/all-signal profiles, '
           '60-second/180-second evidence and optional deviations from the first 60 seconds of baseline physiology. '
           'No EEG, chest signals, task phase, time, demographics, identity or questionnaire answers enter the features. '
           'Each questionnaire uses its own UTC submission marker to resolve changing relative-clock offsets. '
           'Features end before the response and no response is copied into thousands of independent labels.','',
           '| Target | Test accuracy | Balanced accuracy | Low recall | High recall | Test low/high answers |','|---|---:|---:|---:|---:|---:|']
    for target in ('physical','mental'):
        report=json.loads((ROOT/f'results/fatigueset-{target}-v1/report.json').read_text());m=report['selected'];cm=m['confusion_counts']
        lines.append(f"| {target} fatigue | {m['accuracy']:.1%} | {m['balanced_accuracy']:.1%} | {m['low_recall']:.1%} | {m['high_recall']:.1%} | {sum(cm[0])}/{sum(cm[1])} |")
    lines+=['','**The physical-fatigue 82.7% balanced result is based on only one high-fatigue answer.** '
            'Its ordinary accuracy is 66.7% and low-state recall 65.4%; nine low answers become false high-fatigue alerts. '
            'A constant low classifier gets 96.3% ordinary accuracy while detecting zero high-fatigue answers. '
            'The mental-fatigue classifier detects zero of three high-fatigue answers. Neither target meets the predefined 80% balanced/70% each-recall gate.','',
            'Only one test person has both classes for each target. Person-bootstrap intervals are conditional on resamples containing both classes; '
            'they do not establish variability of high-fatigue detection when only one positive reference exists. '
            'These results cannot establish a general fatigue monitor or cross-device/workplace transfer.','',
            'Actual selected artifacts are saved locally under `models/fatigueset-physical-v1/` and `models/fatigueset-mental-v1/`, '
            'with `production_enabled=False`. Data, weights and participant-level predictions remain ignored. '
            'The author site releases data for research; an explicit redistribution/commercial license was not identified.','',
            'Run `python3 scripts/download_fatigueset.py`; then `.venv/bin/python scripts/run_fatigueset.py prepare`; '
            'run `run --target physical` and `run --target mental` separately. Completed runs refuse replacement; '
            'use `verify --target physical` / `verify --target mental` to replay artifacts and check metrics.']
    (ROOT/'experiments/015-fatigueset-results.md').write_text('\n'.join(lines)+'\n')


def report_readiness():
    r=json.loads((ROOT/'results/readiness-oura-v1/report.json').read_text());m=r['selected'];b=r['baseline']
    lines=['# Experiment 016: Oura daily readiness score approximation','',
           '**This predicts a vendor-generated daily score, not independently observed real-time employee readiness.**','',
           'Source: [IFH Affect/Dryad author archive mirrored by Zenodo](https://zenodo.org/records/10458511), CC0. '
           'The download contains 24 participant directories, while the paper and author loader specify par_1..par_21. '
           'Only that published cohort is considered; one has no sleep data and two have fewer than 10 aligned days. '
           f'The retained 18 people provide {r["development_rows"]+r["test_rows"]} daily observations. '
           f'Four people / {r["test_rows"]} days are reserved before model selection; the other 14 people supply {r["development_rows"]} development days.','',
           'The exact target is `oura/readiness.csv:score` on 1–100, with 0 treated as missing. '
           'Every readiness contributor and every other vendor `score` column is excluded from predictors. '
           'There is no target history, identity, demographic, mood or questionnaire input. '
           'Features use completed-sleep HR/HRV, respiration, temperature, sleep durations and stages, '
           'prior activity ending before the sleep cutoff, and strictly earlier 7/14-day physiological histories. '
           'Within-night variation uses only samples recorded by sleep end.','',
           'The source README describes sleep dates as prior-day dates, but 3,985 of 3,997 archive records end on their exported date '
           'in America/Los_Angeles. The pipeline requires that timestamp agreement and excludes the 12 mismatches. '
           'Date alignment was established before scoring; no shift was selected to maximize results. '
           'This remains an offline daily comparison: the source does not supply the exact publication time of each readiness score.','',
           'Four person-disjoint development folds compare 30 configurations of Ridge, RBF SVR, ExtraTrees and CatBoost across '
           'three feature profiles. Development MAE selects a three-model ensemble: SVR C10 and CatBoost depths 5/3 with '
           'sleep, physiology, prior activity and history. The ensemble is frozen before the single held-out evaluation.','',
           '| Metric, equal weight per person | Selected ensemble | Training-mean baseline |','|---|---:|---:|',
           f'| MAE, points out of 100 | {m["mae"]:.2f} | {b["mae"]:.2f} |',
           f'| RMSE, points out of 100 | {m["rmse"]:.2f} | {b["rmse"]:.2f} |',
           f'| R² | {m["r2"]:.3f} | {b["r2"]:.3f} |',
           f'| Within ±5 points | {m["agreement_within_5"]:.1%} | {b["agreement_within_5"]:.1%} |',
           f'| Within ±10 points | {m["agreement_within_10"]:.1%} | {b["agreement_within_10"]:.1%} |','',
           '**The 93.4% figure is agreement within ±10 points of Oura, not classification accuracy or physiological ground truth.** '
           'The MAE falls 54.4% relative to the constant baseline. The predefined research gate '
           '(MAE ≤8, at least 20% improvement, and R² ≥0.25) is met. Four held-out people still give limited population evidence. '
           'The 95% person-bootstrap MAE interval is 3.11–5.11 points; it does not measure device-transfer uncertainty.','',
           'The selected trained artifact is `models/readiness-oura-v1/selected.joblib`, with `production_enabled=False`. '
           'It requires completed overnight/daily summaries and does not operate on a one-second live wrist window. '
           'The company dashboard and demo remain unchanged.','',
           'Reproduce: `python3 scripts/download_readiness_oura.py`; then `.venv/bin/python scripts/run_readiness_oura.py prepare` '
           'and `run`. Inspect the completed immutable evaluation using `verify`.']
    (ROOT/'experiments/016-readiness-oura-results.md').write_text('\n'.join(lines)+'\n')


if __name__=='__main__':
    report_fatigue();report_readiness()
