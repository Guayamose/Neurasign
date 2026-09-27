#!/usr/bin/env python3
"""Read-only source/metric audit of frozen019; no model fitting or time repair.

Detailed anonymous research rows stay in ignored JSON. Public reports should use
only aggregate counts and the same-prediction sensitivity summary.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
NAME = 'readiness-refinement-v1'
EVIDENCE = f'results/{NAME}/source-timing-independent-audit.json'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def metrics(frame, arm):
    """Independent equal-person regression arithmetic; no engine imports."""
    y = frame.target.to_numpy(float)
    p = frame[arm].to_numpy(float)
    _, inverse, counts = np.unique(frame.participant, return_inverse=True, return_counts=True)
    w = 1/(len(counts)*counts[inverse])
    error = y-p
    squared = np.dot(w, error**2)
    variance = np.dot(w, (y-np.dot(w, y))**2)
    return {'mae': float(np.dot(w, abs(error))), 'rmse': float(np.sqrt(squared)),
            'r2': float(1-squared/variance),
            'agreement_within_5': float(np.dot(w, abs(error) <= 5)),
            'agreement_within_10': float(np.dot(w, abs(error) <= 10))}


def inspect_sources(root, protocol, data):
    records, total, errors = [], 0, []
    trajectories = [c for c in data if '_trajectory_' in c]
    oldnight = [c for c in data if c.startswith(('heart_rate_night_', 'heart_rmssd_night_'))
                or c in ('heart_rate_late_minus_early', 'heart_rmssd_late_minus_early')]
    for person in protocol['people']:
        path = root/'data/external/ifh_readiness/extracted'/person/'oura/sleep.csv'
        source = pd.read_csv(path)
        total += len(source)
        prepared = data[data.participant == person].set_index('date')
        included = source[source.date.isin(prepared.index)]
        errors.extend(((included.bedtime_end_timestamp-included.bedtime_start_timestamp)/1000-included.duration).tolist())
        for _, row in source[source.bedtime_start_timestamp >= source.bedtime_end_timestamp].iterrows():
            inside = row.date in prepared.index
            target = prepared.loc[row.date] if inside else None
            interval = (row.bedtime_end_timestamp-row.bedtime_start_timestamp)/1000
            records.append({'participant': person, 'source_date': row.date,
                'source_path': str(path.relative_to(root)),
                'start_ms': int(row.bedtime_start_timestamp), 'end_ms': int(row.bedtime_end_timestamp),
                'start_utc': pd.Timestamp(row.bedtime_start_timestamp, unit='ms', tz='UTC').isoformat(),
                'end_utc': pd.Timestamp(row.bedtime_end_timestamp, unit='ms', tz='UTC').isoformat(),
                'published_duration_seconds': float(row.duration), 'endpoint_duration_seconds': float(interval),
                'duration_discrepancy_seconds': float(interval-row.duration),
                'in_experiment019': inside, 'row_id': str(target.row_id) if inside else None,
                'new_trajectory_all_missing': bool(target[trajectories].isna().all()) if inside else None,
                'old_night_statistics_all_missing': bool(target[oldnight].isna().all()) if inside else None})
    return {'raw_sleep_rows': total, 'prepared_rows': len(data),
            'invalid_raw_interval_count': len(records),
            'invalid_prepared_interval_count': sum(row['in_experiment019'] for row in records),
            'invalid_intervals': records,
            'prepared_duration_discrepancy_counts': {str(k): int(v) for k, v in pd.Series(errors).value_counts().items()},
            'affected_prepared_row_ids': [row['row_id'] for row in records if row['in_experiment019']]}


def audit(root, require_results=False):
    root = Path(root)
    protocol_path = root/'experiments/019-readiness-refinement-protocol.json'
    protocol = json.loads(protocol_path.read_text())
    data_path = root/'data/prepared'/NAME/'days.csv.gz'
    data = pd.read_csv(data_path)
    checks = []

    def check(condition, label):
        assert condition, label
        checks.append(label)

    def equal(actual, expected, label):
        check(bool(np.allclose(actual, expected, rtol=1e-9, atol=1e-10)), label)

    check(sha(data_path) == protocol['data_sha256'], 'prepared checksum')
    previous_path = root/'data/prepared/readiness-oura-v1/days.csv.gz'
    check(sha(previous_path) == protocol['prior_prepared_sha256'], 'prior prepared checksum')
    previous = pd.read_csv(previous_path).set_index('row_id').loc[data.row_id]
    equal(data.target, previous.target, 'original source targets unchanged')
    check(np.allclose(data[protocol['profiles']['original']], previous[protocol['profiles']['original']], equal_nan=True),
          'fixed reference source features unchanged')
    for path, digest in {**protocol['code_sha256'], **protocol['source_sha256']}.items():
        check(sha(root/path) == digest, 'frozen '+path)
    check(set(data.participant) == set(protocol['people']), 'development cohort')
    check(set(data.participant).isdisjoint(protocol['old_test_people_excluded']), 'old test excluded')
    blocked = {'target', 'participant', 'row_id', 'date', 'feature_cutoff_ms'}
    check(all(not blocked.intersection(cols) and not any('score' in c for c in cols)
              for cols in protocol['profiles'].values()), 'no target identity or score inputs')
    evidence = {'type': 'Independent read-only source timing and saved-result audit',
                'scope': 'Experiment019 development people only; no timestamp correction, refitting or reselection',
                'people': len(protocol['people']), **inspect_sources(root, protocol, data),
                'interpretation': 'Invalid endpoints disagree with published duration by one day. No endpoint is repaired or assumed correct. Raw overnight trajectories are missing for affected scored rows. Invalid raw rows may also enter later physiological histories, so excluding affected scored rows is not a complete corrected-feature analysis.',
                'prepared_sha256': sha(data_path), 'protocol_sha256': sha(protocol_path),
                'script_sha256': sha(__file__)}
    out = root/'results'/NAME
    if (out/'run-start.json').exists():
        freeze = json.loads((out/'run-start.json').read_text())
        check(freeze['protocol_sha256'] == sha(protocol_path), 'protocol unchanged since run start')
        check(freeze['data_sha256'] == protocol['data_sha256'], 'same frozen data')
        check(freeze['code_sha256'] == protocol['code_sha256'], 'same frozen code')
    outer_people = []
    for fold in protocol['folds']:
        tr, va = set(fold['training_people']), set(fold['validation_people'])
        check(not tr & va and tr | va == set(protocol['people']), 'outer split')
        outer_people.extend(va)
        inner_people = []
        for inner in fold['inner']:
            it, iv = set(inner['training_people']), set(inner['validation_people'])
            check(not it & iv and it | iv == tr, 'inner split')
            inner_people.extend(iv)
        check(len(inner_people) == len(set(inner_people)) and set(inner_people) == tr, 'inner once per person')
    check(len(outer_people) == len(set(outer_people)) and set(outer_people) == set(protocol['people']), 'outer once per person')
    pred_path = out/'outer-predictions.csv.gz'
    if pred_path.exists():
        pred = pd.read_csv(pred_path)
        check(pred.row_id.is_unique and set(pred.row_id) == set(data.row_id), 'complete original predictions')
        actual = data.set_index('row_id').loc[pred.row_id]
        equal(pred.target, actual.target, 'original labels')
        check(np.array_equal(pred.participant, actual.participant), 'person alignment')
        result = {arm: metrics(pred, arm) for arm in ('constant', 'fixed', 'selected')}
        constants = []
        for fold in protocol['folds']:
            train = data[data.participant.isin(fold['training_people'])]
            valid = pred[pred.fold == fold['fold']]
            check(set(valid.participant) == set(fold['validation_people']), 'outer prediction people')
            constant = float(train.groupby('participant').target.mean().mean())
            equal(valid.constant, constant, 'training-only constant')
            constants.append({'fold': fold['fold'], 'value': constant, 'training_people': len(fold['training_people'])})
            folder = out/f'outer-{fold["fold"]}'
            selection = json.loads((folder/'selection.json').read_text())
            comparisons, inner_predictions = [], {}
            for item in selection['comparison']:
                config = item['configuration']
                key = config['profile']+':'+config['algorithm']
                cached = pd.read_csv(folder/(key.replace(':', '-')+'.csv.gz'))
                check(cached.row_id.is_unique and set(cached.row_id) == set(train.row_id), 'inner predictions use training rows only')
                truth = train.set_index('row_id').loc[cached.row_id].copy()
                truth['prediction'] = cached.prediction.to_numpy()
                value = metrics(truth, 'prediction')['mae']
                equal(value, item['mae'], 'independent candidate MAE')
                comparisons.append((value, config))
                inner_predictions[key] = pd.Series(cached.prediction.to_numpy(), index=cached.row_id)
            ranked = sorted(comparisons, key=lambda x: x[0])
            top = [config for _, config in ranked[:3]]
            check(top == selection['ensemble_top3']['members'], 'ensemble is inner top three')
            ensemble_frame = train.copy()
            ensemble_frame['prediction'] = np.mean([inner_predictions[c['profile']+':'+c['algorithm']].loc[train.row_id].to_numpy() for c in top], axis=0)
            ensemble = metrics(ensemble_frame, 'prediction')['mae']
            equal(ensemble, selection['ensemble_top3']['mae'], 'ensemble MAE')
            check(selection['selected'] == (top if ensemble < ranked[0][0] else [ranked[0][1]]), 'selection rule reproduced')
        retained = pred[~pred.row_id.astype(str).isin(evidence['affected_prepared_row_ids'])].copy()
        sensitivity = {arm: metrics(retained, arm) for arm in ('constant', 'fixed', 'selected')}
        evidence['outer_metrics_independently_recomputed'] = result
        evidence['outer_training_constants'] = constants
        evidence['predictions_sha256'] = sha(pred_path)
        evidence['same_prediction_sensitivity'] = {
            'purpose': 'Post-hoc sensitivity only; original models, thresholds, selection and predictions unchanged.',
            'removed_rows': len(pred)-len(retained), 'remaining_rows': len(retained),
            'remaining_people': retained.participant.nunique(),
            'metrics': sensitivity,
            'selected_relative_mae_improvement_over_fixed': 1-sensitivity['selected']['mae']/sensitivity['fixed']['mae'],
            'scope_limit': 'Does not repair raw histories or remove invalid training examples; not a corrected-pipeline benchmark.'}
        report_path = out/'report.json'
        if report_path.exists():
            report = json.loads(report_path.read_text())
            manifest = json.loads((out/'evaluation.json').read_text())
            check(manifest['predictions_sha256'] == sha(pred_path), 'final prediction checksum')
            for path, digest in manifest['selection_sha256'].items():
                check(sha(root/path) == digest, 'final selection checksum '+path)
            for arm, values in result.items():
                for metric, value in values.items():
                    equal(value, report['outer'][arm][metric], 'saved outer '+arm+' '+metric)
            person_order = pred.participant.unique()
            errors = np.array([[np.mean(abs(g.target-g.selected)), np.mean(abs(g.target-g.fixed))]
                               for person in person_order for g in [pred[pred.participant == person]]])
            rng = np.random.default_rng(protocol.get('seed', 20260927))
            draws = np.array([errors[rng.choice(len(person_order), len(person_order), replace=True)].mean(axis=0) for _ in range(1000)])
            equal(np.quantile(draws[:, 0], [.025, .975]), report['uncertainty']['selected_mae_95'], 'independent person bootstrap')
            equal(np.quantile(draws[:, 0]-draws[:, 1], [.025, .975]), report['uncertainty']['paired_mae_difference_95'], 'independent paired bootstrap')
            evidence['saved_report_verified'] = True
        else:
            evidence['saved_report_verified'] = False
    else:
        check(not require_results, 'Original outer predictions are required')
        evidence['sensitivity_status'] = 'Pending original outer predictions; no model fitting will be performed.'
    evidence['independent_checks_passed'] = len(checks)
    path = root/EVIDENCE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(evidence, indent=2, allow_nan=False)+'\n')
    return {'evidence': EVIDENCE, 'checks': len(checks), 'invalid_raw_intervals': evidence['invalid_raw_interval_count'],
            'invalid_prepared_intervals': evidence['invalid_prepared_interval_count'],
            'sensitivity_complete': 'same_prediction_sensitivity' in evidence,
            'saved_report_verified': evidence.get('saved_report_verified', False)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--require-results', action='store_true')
    args = parser.parse_args()
    print(json.dumps(audit(ROOT, args.require_results)), flush=True)


if __name__ == '__main__':
    main()
