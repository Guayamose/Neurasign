#!/usr/bin/env python3
"""Render only the saved aggregate evidence for experiment019."""
from pathlib import Path
import json
ROOT=Path(__file__).resolve().parents[1]


def main():
    p=json.loads((ROOT/'experiments/019-readiness-refinement-protocol.json').read_text())
    r=json.loads((ROOT/'results/readiness-refinement-v1/report.json').read_text())
    audit_path=ROOT/'results/readiness-refinement-v1/source-timing-independent-audit.json'
    audit=json.loads(audit_path.read_text())
    assert audit.get('saved_report_verified'), 'Run audit_readiness_refinement.py after final results first'
    u=r['uncertainty']
    lines=[
        '# Experiment 019: richer physiological context for daily readiness', '',
        '**Exploratory nested development evaluation. The original four test people remain excluded.**', '',
        f'This evaluates {r["rows"]} daily observations from {r["people"]} previously studied development people. '
        'Four outer folds hold out complete people; three inner folds select configurations using only the outer-training people. '
        'All preprocessing and physiological model fitting stay inside the training folds. '
        'Prior experiments informed the candidate design, so this is not fresh external validation. '
        'The earlier 3.98-point test MAE remains a separate result on a different cohort.', '',
        'Target: the observed 1–100 Oura daily readiness score in '
        '[IFH Affect](https://zenodo.org/records/10458511), CC0. '
        'It is a vendor-score approximation, not an independently measured instantaneous employee state. '
        'No vendor score, readiness contributor, target history, identity or questionnaire is a predictor.', '',
        'The original 50 features are compared with 261 physiological/context features: sleep-stage fractions, '
        'sleep timing phase, strictly preceding 7/14/28-day personal physiology references, previous activity, '
        'and raw overnight HR/HRV recovery trajectories. Measurements use the published sleep-end cutoff, '
        'subject to the source timing qualification below. '
        'Calendar dates and absolute timestamps are used for alignment only.', '',
        'Eighteen registered profile/algorithm configurations compare ridge, spline ridge, RBF SVR, '
        'CatBoost with squared or absolute loss, and histogram gradient boosting with absolute loss. '
        'A mean of the top three inner models may win on inner MAE. The fixed historical reference refits '
        'the experiment016 SVR C10 / CatBoost depth3 / CatBoost depth5 ensemble on exactly the same outer-training people, '
        'preserving its original preprocessing. The constant predicts only the outer-training person-weighted mean.', '',
        '| Planned arm | MAE /100 | RMSE /100 | R² | Within ±5 points | Within ±10 points |',
        '|---|---:|---:|---:|---:|---:|',
    ]
    for arm in ['constant','fixed','selected']:
        m=r['outer'][arm]
        lines.append(f'| {arm} | {m["mae"]:.3f} | {m["rmse"]:.3f} | {m["r2"]:.3f} | {m["agreement_within_5"]:.1%} | {m["agreement_within_10"]:.1%} |')
    lines += [
        '', '**All metrics weight people equally. Tolerance percentages are not classification accuracy.**', '',
        f'Relative selected MAE reduction against the fixed reference: {r["relative_mae_improvement_over_fixed"]:.1%}. '
        f'The 95% person-bootstrap MAE interval is {u["selected_mae_95"][0]:.3f}–{u["selected_mae_95"][1]:.3f}. '
        f'The paired selected-minus-fixed MAE interval is {u["paired_mae_difference_95"][0]:.3f}–{u["paired_mae_difference_95"][1]:.3f}; '
        'negative differences favor the new procedure. These intervals condition on the frozen outer predictions.', '',
        f'Predeclared research gate (≥10% improvement, MAE ≤4, R² ≥0.5): **{"reached" if r["research_gate_met"] else "not reached"}**.', '',
        '| Outer fold | Inner-selected configuration(s) |', '|---|---|',
    ]
    for index,selection in enumerate(r['outer_selections']):
        lines.append(f'| {index+1} | '+', '.join(f'`{c["profile"]}:{c["algorithm"]}`' for c in selection)+' |')
    sensitivity=audit['same_prediction_sensitivity']
    lines += [
        '', '## Source timing audit and sensitivity', '',
        f'The independent source audit found {audit["invalid_raw_interval_count"]} reversed sleep intervals among '
        f'{audit["raw_sleep_rows"]} source sleep records from these development participants. '
        f'{audit["invalid_prepared_interval_count"]} occur among the {r["rows"]} scored daily rows. '
        'Each reversed interval differs from its published duration by exactly one day. '
        'Neither endpoint was shifted or repaired. Both affected scored rows have missing raw overnight heart '
        'trajectories and retain their published aggregate sleep measurements. The other scored intervals '
        'match their published durations exactly.', '',
        f'A post-hoc sensitivity check excludes those {sensitivity["removed_rows"]} scored rows and recomputes '
        f'aggregate metrics on {sensitivity["remaining_rows"]} rows from {sensitivity["remaining_people"]} people, '
        'using exactly the same saved predictions. Models, training data and selection are unchanged:', '',
        '| Same predictions, affected scored rows excluded | MAE /100 | R² | Within ±10 points |',
        '|---|---:|---:|---:|',
    ]
    for arm in ['constant','fixed','selected']:
        m=sensitivity['metrics'][arm]
        lines.append(f'| {arm} | {m["mae"]:.3f} | {m["r2"]:.3f} | {m["agreement_within_10"]:.1%} |')
    lines += [
        '', 'This sensitivity does not repair physiological histories or remove invalid training rows. '
        'Invalid source records may also contribute to later physiological histories. It therefore does not '
        'establish a fully corrected timing pipeline. The original frozen results remain the primary report.', '',
        'Detailed source checks and independently recomputed metrics are recorded locally in ignored '
        '`results/readiness-refinement-v1/source-timing-independent-audit.json`; no individual records are published here.',
    ]
    lines += [
        '', 'Final development-only fit: '+', '.join(f'`{c["profile"]}:{c["algorithm"]}`' for c in r['final_selection'])+'. '
        'This artifact is saved for reproducibility, not selected by its outer score or evaluated again on the old test cohort. '
        'All artifacts carry `production_enabled=False`.', '',
        'Reproduce from the engine directory after experiment016 data preparation:', '',
        '```sh', '.venv/bin/python scripts/run_readiness_refinement.py prepare',
        '.venv/bin/python scripts/run_readiness_refinement.py run',
        '.venv/bin/python scripts/run_readiness_refinement.py verify',
        '.venv/bin/python scripts/audit_readiness_refinement.py --require-results',
        '.venv/bin/python scripts/report_readiness_refinement.py', '```', '',
        'The immutable protocol records source, code and prepared-data hashes. Verification replays every outer artifact, '
        'checks excluded people, independently recomputes metrics and outer-training constants, '
        'and recomputes every inner candidate MAE. Raw data, participant predictions and fitted weights stay ignored.',
    ]
    (ROOT/'experiments/019-readiness-refinement-results.md').write_text('\n'.join(lines)+'\n')


if __name__=='__main__':main()
