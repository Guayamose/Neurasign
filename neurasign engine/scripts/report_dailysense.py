#!/usr/bin/env python3
"""Publish aggregate DailySense evidence from completed immutable evaluations."""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]


def main():
    reports = {kind: json.loads((ROOT/f'results/dailysense-{kind}-v1/report.json').read_text())
               for kind in ('classification', 'regression')}
    c, r = reports['classification'], reports['regression']
    cm = c['selected']['confusion_counts']
    integrity = json.loads((ROOT/'data/prepared/dailysense-v1/verification.json').read_text())
    rejected = integrity['channel_integrity_counts']
    within = c['selected']['within_person_balanced_accuracy']
    within_text = f'{within:.1%}' if within is not None else 'unavailable'
    lines = [
        '# Experiment 018: DailySense observed daily fatigue', '',
        '**Daily questionnaire prediction from preceding wrist signals. No instantaneous-state or production claim.**', '',
        'Source: [DailySense, Hitachi public release](https://zenodo.org/records/10816004), CC BY 4.0. '
        'The source study contains 36 people in two separate cohorts monitored for 14 days. '
        'The target is the original `drm_vas1` fatigue VAS, from 0 (none) to 100 (worst). '
        'The regression preserves that scale; classification uses the fixed research midpoint ≥50 versus <50, '
        'without removing middle ratings. This is not a clinical cutoff.', '',
        'The scheduled survey cutoff is 21:30 Asia/Tokyo on `SignalDate`. Delayed completion does not '
        'allow next-day signals into an earlier label. Each row represents one original daily answer. '
        'Inputs summarize preceding HR, native IBI, BVP, EDA, skin temperature and acceleration; '
        'profiles compare cardiac daily summaries, autonomic daily summaries, daily plus last-hour summaries, '
        'and deviations from strictly earlier seven-day sensor histories. No target history or other questionnaire enters the model.', '',
        'Both complete outer ZIPs match publisher MD5. Many nested archives contain damaged compressed '
        'channels: independent fresh range retrieval reproduced the problem. Each inner CSV must pass its '
        'own size/CRC verification before parsing. Damaged channels remain missing; healthy channels are retained. '
        'Day inclusion requires at least 60 minutes with three verified channels, including cardiac and '
        'autonomic evidence, and at least five paired days per person. Detailed exclusions and source hashes '
        'are retained in the ignored preparation audit. '
        f'Of 579 source recordings, 578 were cached and one malformed recording was excluded. '
        f'Among cached recordings, {rejected["BVP.csv_rejected"]} BVP streams and '
        f'{rejected["ACC.csv_rejected"]} acceleration streams failed verification; '
        'each of HR, EDA, temperature and IBI remained valid in at least 558 recordings.', '',
        f'The retained cohort contains {c["development_people"]+c["test_people"]} people and '
        f'{c["development_rows"]+c["test_rows"]} daily answers. '
        f'{c["development_people"]} people / {c["development_rows"]} days are used for development; '
        f'{c["test_people"]} reserved people / {c["test_rows"]} days are scored once. '
        'Both targets use the same person split. Four person-disjoint development folds compare 40 '
        'profile/algorithm configurations per target plus one top-three ensemble. '
        'Imputation, scaling and fitting are confined to the training folds. '
        'All evaluation metrics give each person equal weight.', '',
        '| Classifier | Person-weighted accuracy | Balanced accuracy | Low recall | High-fatigue recall |',
        '|---|---:|---:|---:|---:|',
    ]
    for key in ('selected', 'baseline'):
        m = c[key]
        lines.append(f'| {key} | {m["accuracy"]:.1%} | {m["balanced_accuracy"]:.1%} | {m["low_recall"]:.1%} | {m["high_recall"]:.1%} |')
    lines += [
        '', f'Test references: {sum(cm[0])} low and {sum(cm[1])} high. '
        f'Selected confusion counts: true low {cm[0][0]}, false high {cm[0][1]}, '
        f'false low {cm[1][0]}, true high {cm[1][1]}. '
        f'Raw unweighted accuracy is {(cm[0][0]+cm[1][1])/sum(map(sum, cm)):.1%} '
        f'({cm[0][0]+cm[1][1]}/{sum(map(sum, cm))}); the table gives each person equal weight. '
        f'The selected classifier is `{", ".join(c["selection"])}`. '
        f'Within-person balanced accuracy is {within_text} among '
        f'{c["selected"]["people_with_both_classes"]} test people with both classes.', '',
        '| Regressor | MAE /100 | RMSE /100 | R² | Within ±5 points | Within ±10 points |',
        '|---|---:|---:|---:|---:|---:|',
    ]
    for key in ('selected', 'baseline'):
        m = r[key]
        lines.append(f'| {key} | {m["mae"]:.2f} | {m["rmse"]:.2f} | {m["r2"]:.3f} | {m["agreement_within_5"]:.1%} | {m["agreement_within_10"]:.1%} |')
    lines += [
        '', f'The selected regressor is `{", ".join(r["selection"])}`. '
        '**Regression tolerance agreement is not classification accuracy or calibrated confidence.**', '',
        f'Person-bootstrap 95% intervals: balanced accuracy '
        f'{c["uncertainty"]["person_bootstrap_95"][0]:.1%}–{c["uncertainty"]["person_bootstrap_95"][1]:.1%}; '
        f'regression MAE {r["uncertainty"]["person_bootstrap_95"][0]:.2f}–{r["uncertainty"]["person_bootstrap_95"][1]:.2f} points.', '',
        f'Predefined classification gate (balanced accuracy ≥80%, both recalls ≥70%): '
        f'**{"reached" if c["research_gate_met"] else "not reached"}**. '
        f'Regression gate (MAE ≤8, ≥20% improvement over the training-mean constant, R² ≥0.25): '
        f'**{"reached" if r["research_gate_met"] else "not reached"}**.', '',
        'A small reserved cohort, daily retrospective labels, source signal damage and a single wrist-device '
        'family limit interpretation. This evaluation does not validate second-by-second fatigue, '
        'new wearable brands or fitness for duty.', '',
        'Reproduce: install `requirements-fatigue.txt`; run `scripts/download_dailysense.py`, '
        '`scripts/prepare_dailysense.py cache`, then `scripts/run_dailysense.py prepare` and `run`. '
        'Use `scripts/run_dailysense.py verify` to replay completed artifacts without reopening selection. '
        'The trained artifacts are in ignored `models/dailysense-classification-v1/` and '
        '`models/dailysense-regression-v1/`; both carry `production_enabled=False`.',
    ]
    (ROOT/'experiments/018-dailysense-results.md').write_text('\n'.join(lines)+'\n')


if __name__ == '__main__':
    main()
