"""Independent arithmetic audit of experiment020; never retrains models.

Prediction replay uses the saved pipeline. Metrics, constants, threshold choices
and split audits do not call the experiment's metric or selection functions.
"""
import hashlib
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def calculate(frame, prediction, classification):
    """Arithmetic deliberately separate from training/scoring implementation."""
    target = frame.target.to_numpy()
    _, inverse, counts = np.unique(frame.participant.to_numpy(), return_inverse=True, return_counts=True)
    weights = 1/counts[inverse].astype(float)
    weights /= weights.sum()
    prediction = np.asarray(prediction)
    if not classification:
        absolute = np.abs(target-prediction)
        return {'mae': float(np.dot(weights, absolute)),
                'rmse': float(np.sqrt(np.dot(weights, absolute**2))),
                'r2': float(1-np.dot(weights, absolute**2)/np.dot(weights, (target-np.dot(weights, target))**2)),
                'agreement_within_5': float(weights[absolute <= 5].sum()),
                'agreement_within_10': float(weights[absolute <= 10].sum()), 'coverage': 1.}
    recalls = [float(weights[(target == c) & (prediction == c)].sum()/weights[target == c].sum()) for c in (0, 1)]
    precisions = [float(weights[(target == c) & (prediction == c)].sum()/weights[prediction == c].sum()) if np.any(prediction == c) else 0. for c in (0, 1)]
    f1 = [2*r*p/(r+p) if r+p else 0. for r, p in zip(recalls, precisions)]
    person_scores = []
    for person in sorted(set(frame.participant)):
        mask = frame.participant.to_numpy() == person
        if len(set(target[mask])) == 2:
            person_scores.append(sum(float(np.mean(prediction[mask & (target == c)] == c)) for c in (0, 1))/2)
    return {'person_weighted_accuracy': float(weights[target == prediction].sum()),
            'unweighted_accuracy': float(np.mean(target == prediction)), 'balanced_accuracy': sum(recalls)/2,
            'low_recall': recalls[0], 'high_recall': recalls[1], 'low_precision': precisions[0],
            'high_precision': precisions[1], 'macro_f1': sum(f1)/2,
            'confusion_counts': [[int(np.count_nonzero((target == a) & (prediction == b))) for b in (0, 1)] for a in (0, 1)],
            'within_person_balanced_accuracy': float(np.mean(person_scores)) if person_scores else None,
            'people_with_both_classes': len(person_scores), 'coverage': 1.}


def verify(root):
    from .fatigue_nested import artifact_prediction, features, predict
    root = Path(root)
    name = 'fatigue-nested-v1'
    protocol_path = root/'experiments/020-fatigue-nested-protocol.json'
    protocol = json.loads(protocol_path.read_text())
    checks, replay_count = [], 0

    def check(condition, label):
        assert condition, label
        checks.append(label)

    def equal(actual, expected, label):
        if actual is None or expected is None:
            check(actual is expected, label)
        else:
            check(bool(np.allclose(actual, expected, rtol=1e-9, atol=1e-10)), label)

    def metrics_equal(actual, expected, label):
        check(set(actual) == set(expected), label+':keys')
        for key, value in actual.items():
            equal(value, expected[key], label+':'+key)

    for path, digest in {**protocol['code_sha256'], **protocol['preserved_sha256']}.items():
        check(_sha(root/path) == digest, 'immutable '+path)
    check(_sha(root/protocol['data']) == protocol['data_sha256'], 'prepared checksum')
    source_path = root/'data/prepared/dailysense-v1/answers.csv.gz'
    check(_sha(source_path) == protocol['input_sha256'], 'original source checksum')
    source = pd.read_csv(source_path)
    source = source[source.participant.isin(protocol['people'])].copy()
    data = pd.read_csv(root/protocol['data'])
    check(len(data) == 357 and data.participant.nunique() == 28, 'cohort')
    check(set(data.participant).isdisjoint(protocol['historical_test_people_excluded']), 'old test excluded')
    check(data.row_id.is_unique and data.unit_id.is_unique, 'one reference per day')
    source = source.set_index('row_id').loc[data.row_id].reset_index()
    equal(data.rating, source.rating, 'original labels unchanged')
    generated, profiles = features(source, protocol['profiles']['cardiac_day'])
    check(profiles == protocol['profiles'], 'profile mapping')
    for profile, columns in profiles.items():
        check(not set(columns).intersection({'row_id', 'participant', 'unit_id', 'date', 'rating', 'target'}), 'excluded fields '+profile)
        check(np.allclose(data[columns], generated[columns], equal_nan=True), 'feature replay '+profile)
    check(len(protocol['candidates']) == 18, 'candidate budget')
    validated_people = []
    for outer in protocol['outer_folds']:
        tr, va = set(outer['training_people']), set(outer['validation_people'])
        check(not tr & va and tr | va == set(protocol['people']), 'outer split')
        validated_people.extend(va)
        inner_valid = []
        for inner in outer['inner_folds']:
            itr, iva = set(inner['training_people']), set(inner['validation_people'])
            check(not itr & iva and itr | iva == tr and not (itr | iva) & va, 'inner split')
            inner_valid.extend(iva)
        check(len(inner_valid) == len(set(inner_valid)) and set(inner_valid) == tr, 'inner people exactly once')
    check(len(validated_people) == len(set(validated_people)) and set(validated_people) == set(protocol['people']), 'outer people exactly once')

    def audit_selection(selection, inner_table, expected_folds, kind):
        check(selection['folds'] == expected_folds, 'frozen inner fold list')
        classification = kind == 'classification'
        rows = []
        for row in selection['comparisons']:
            score = inner_table[row['key']].to_numpy()
            if row['key'] == 'diverse_top3':
                equal(score, inner_table[row['members']].mean(axis=1), 'ensemble averages inner predictions')
            if classification:
                options = [(calculate(inner_table, score >= t, True), t) for t in protocol['thresholds']]
                metric, threshold = sorted(options, key=lambda x: (-x[0]['balanced_accuracy'], -min(x[0]['low_recall'], x[0]['high_recall']), abs(x[1]-.5), x[1]))[0]
                equal(threshold, row['threshold'], 'inner threshold independently selected')
            else:
                metric = calculate(inner_table, score, False)
            metrics_equal(metric, row['metrics'], 'inner candidate '+row['key'])
            rows.append(row)
        key = 'balanced_accuracy' if classification else 'mae'
        ranked = sorted(rows[:-1], key=lambda r: (-r['metrics'][key] if classification else r['metrics'][key], r['key']))
        diverse, families = [], set()
        for row in ranked:
            family = row['algorithm'].split('_')[0]
            if family not in families:
                diverse.append(row['key']); families.add(family)
            if len(diverse) == 3:
                break
        ensemble = rows[-1]
        check(ensemble['members'] == diverse, 'predeclared diverse ensemble')
        improved = ensemble['metrics'][key] > ranked[0]['metrics'][key] if classification else ensemble['metrics'][key] < ranked[0]['metrics'][key]
        expected_selection = diverse if improved else [ranked[0]['key']]
        check(selection['selected'] == expected_selection, 'selection based only on inner scores')
        equal(selection['threshold'], ensemble['threshold'] if improved else ranked[0]['threshold'], 'selected threshold')

    for kind in ('classification', 'regression'):
        classification = kind == 'classification'
        frame = data.copy()
        frame['target'] = (frame.rating >= 50).astype(int) if classification else frame.rating
        out = root/'results'/name/kind
        start = json.loads((out/'run-start.json').read_text())
        manifest = json.loads((out/'manifest.json').read_text())
        report = json.loads((out/'report.json').read_text())
        prediction_path = out/'outer-predictions.csv.gz'
        predictions = pd.read_csv(prediction_path)
        check(start['protocol_sha256'] == _sha(protocol_path), kind+' protocol frozen')
        check(manifest['predictions_sha256'] == _sha(prediction_path), kind+' predictions checksum')
        check(predictions.row_id.is_unique and set(predictions.row_id) == set(frame.row_id), kind+' full outer coverage')
        expected = frame.set_index('row_id').loc[predictions.row_id]
        equal(predictions.target, expected.target, kind+' original target')
        check(np.array_equal(predictions.participant, expected.participant), kind+' correct identity alignment')
        for item in manifest['models']:
            fold_id = item['fold']
            fold = protocol['outer_folds'][fold_id]
            pred = predictions[predictions.fold == fold_id]
            train = frame[frame.participant.isin(fold['training_people'])]
            valid = frame.set_index('row_id').loc[pred.row_id].reset_index()
            check(set(valid.participant) == set(fold['validation_people']), kind+' outer rows correct')
            saved = joblib.load(root/item['path'])
            check(_sha(root/item['path']) == item['sha256'], kind+' model checksum')
            check(saved['training_people'] == fold['training_people'], kind+' model fitted people')
            check(saved['outer_people_excluded'] == fold['validation_people'], kind+' outer exclusion stored')
            check(saved['production_enabled'] is False, kind+' disabled artifact')
            equal(artifact_prediction(saved, valid), pred.inner_selected, kind+' selected artifact replay')
            equal(predict(saved['fixed_model'], valid, saved['fixed_columns'], kind), pred.fixed_cardiac_extra5, kind+' fixed artifact replay')
            replay_count += 2
            constant = sum(train[train.participant == p].target.mean() for p in set(train.participant))/train.participant.nunique()
            equal(pred.training_constant, constant, kind+' training-only constant')
            selection_path = out/f'fold-{fold_id}-selection.json'
            check(item['selection_sha256'] == _sha(selection_path), kind+' selection checksum')
            selection = json.loads(selection_path.read_text())
            inner = pd.read_csv(out/f'fold-{fold_id}-inner.csv.gz')
            check(inner.row_id.is_unique and set(inner.row_id) == set(train.row_id), kind+' inner contains training only')
            expected_inner = train.set_index('row_id').loc[inner.row_id]
            equal(inner.target, expected_inner.target, kind+' inner original target')
            audit_selection(selection, inner, fold['inner_folds'], kind)
            if classification:
                equal(saved['threshold'], selection['threshold'], 'artifact threshold')
                equal(pred.threshold, selection['threshold'], 'outer frozen threshold')
            for arm in protocol['arms']:
                if classification:
                    threshold = selection['threshold'] if arm == 'inner_selected' else .5
                    equal(pred[arm+'_decision'], (pred[arm] >= threshold).astype(int), 'outer decision threshold')
                p = pred[arm+'_decision' if classification else arm]
                metrics_equal(calculate(pred, p, classification), report['folds'][fold_id]['metrics'][arm], kind+' fold metrics')
        for arm in protocol['arms']:
            p = predictions[arm+'_decision' if classification else arm]
            metrics_equal(calculate(predictions, p, classification), report['outer_metrics'][arm], kind+' pooled metrics')
        final = joblib.load(root/manifest['final_model'])
        check(_sha(root/manifest['final_model']) == manifest['final_model_sha256'], 'final model checksum')
        check(final['training_people'] == protocol['people'] and final['production_enabled'] is False, 'final development only artifact')
        final_selection_path = out/'final-selection.json'
        check(_sha(final_selection_path) == manifest['final_selection_sha256'], 'final selection checksum')
        final_inner = pd.read_csv(out/'final-inner.csv.gz')
        check(final_inner.row_id.is_unique and set(final_inner.row_id) == set(frame.row_id), 'final selection development only')
        audit_selection(json.loads(final_selection_path.read_text()), final_inner, protocol['final_inner_folds'], kind)
        check(final['historical_test_people_excluded'] == protocol['historical_test_people_excluded'], 'final artifact old exclusion')
        selected = report['outer_metrics']['inner_selected']
        gate = (selected['balanced_accuracy'] >= .8 and min(selected['low_recall'], selected['high_recall']) >= .7 if classification
                else selected['mae'] <= 8 and selected['mae'] <= .8*report['outer_metrics']['training_constant']['mae'] and selected['r2'] >= .25)
        check(report['exploratory_gate_met'] == gate, 'gate matches predefined rule')
    result = {'status': 'passed', 'independent_checks': len(checks), 'artifact_replays': replay_count,
              'historical_test_people_excluded': True, 'training_only_constants': True,
              'inner_selections_independently_recomputed': True}
    output = root/'results'/name/'verification.json'
    output.write_text(json.dumps(result, indent=2)+'\n')
    return result
