"""Anonymous offline stress-label benchmark; no product integration or diagnosis."""
from __future__ import annotations
import json
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits
from . import personalization as learning
from .swell import read_workbook, prepare_frame, FEATURES
from .short_window_report import independent_metrics
from .transfer_training import sha, write_json
from .schema import SEED

ALGORITHMS = ['logit1', 'rbf1', 'extra', 'cat4']
OUT = 'results/swell-stress-v1'
PROTOCOL = 'experiments/013-swell-stress-protocol.json'


def prepare(root):
    old = json.loads((root/'experiments/005-swell-protocol.json').read_text())
    workbook = root/old['workbook_name']
    assert sha(workbook) == old['workbook_sha256']
    source, _ = read_workbook(workbook)
    data, _ = prepare_frame(source)
    stress = source[['PP', 'timestamp', 'Stress']].copy()
    stress['window_end'] = pd.to_datetime(stress.timestamp, format='%Y%m%dT%H%M%S%f', errors='raise').astype('int64')/1e9
    stress['participant'] = stress.PP
    stress['stress'] = pd.to_numeric(stress.Stress, errors='raise')
    assert not np.isinf(stress.stress).any() and not ((stress.stress < 0) | (stress.stress > 10)).any()
    data = data.merge(stress[['participant', 'window_end', 'stress']], on=['participant', 'window_end'], how='left', validate='one_to_one')
    data = data[data.participant.isin(old['split']['development'])].copy()
    assert not set(data.participant) & set(old['split']['test'])
    assert data.groupby('unit_id').stress.nunique().max() <= 1
    audit = {'original_development_people': old['split']['development'], 'excluded_test_people': old['split']['test'],
             'development_usable_minutes': len(data), 'development_usable_blocks': int(data.unit_id.nunique()),
             'middle_minutes': int(((data.stress > 10/3) & (data.stress < 20/3)).sum()),
             'missing_rating_minutes': int(data.stress.isna().sum()), 'workbook_sha256': sha(workbook)}
    data['outcome'] = np.where(data.stress <= 10/3, 0., np.where(data.stress >= 20/3, 1., np.nan))
    data = data[data.outcome.notna()].copy().reset_index(drop=True);data['row_id'] = data.index
    assert data.outcome.nunique() == 2 and data.participant.nunique() >= 5
    data.outcome = data.outcome.astype(int)
    cols = ['row_id', 'participant', 'unit_id', 'window_end', 'outcome', 'stress', *FEATURES]
    data = data[cols]
    path = root/'data/prepared/swell-stress-v1/minutes.csv.gz';path.parent.mkdir(parents=True, exist_ok=True)
    data.to_csv(path, index=False, compression={'method':'gzip', 'mtime':0})
    audit.update(people=int(data.participant.nunique()), blocks=int(data.unit_id.nunique()), minutes=len(data),
                 label_blocks=data.drop_duplicates('unit_id').outcome.value_counts().to_dict(),
                 feature_availability=data[FEATURES].notna().mean().to_dict(), data_sha256=sha(path))
    write_json(root/OUT/'audit.json', audit)
    return data, audit


def fit(frame, algorithm):
    assert algorithm in ALGORITHMS
    config = {'profile': 'native_swell', 'algorithm': algorithm}
    artifact = {'columns': list(FEATURES), 'config': config, 'production_enabled': False,
                'target': 'self_reported_stress_low_high', 'score_is_calibrated_confidence': False,
                'training_people': sorted(frame.participant.unique()),
                'training_units': sorted(frame.unit_id.unique()), 'fitting_row_ids': frame.row_id.tolist()}
    if frame.outcome.nunique() == 1:
        artifact['constant'] = int(frame.outcome.iloc[0])
    else:
        model = learning.classifier(config)
        model.fit(frame[FEATURES], frame.outcome, **{model.steps[-1][0]+'__sample_weight': learning.training_weights(frame)})
        artifact['model'] = model
    return artifact


def folds(people, count):
    return [list(fold) for fold in np.array_split(np.random.default_rng(SEED).permutation(sorted(people)), min(count, len(people)))]


def metrics(frame, arm):
    result = independent_metrics(frame, arm)
    cm = np.asarray(result['confusion_matrix_person_task_weighted'])
    denom = cm.sum(0)+cm.sum(1)
    result['macro_f1'] = float(np.mean(np.divide(2*np.diag(cm), denom, out=np.zeros(2), where=denom > 0)))
    return result


def select(training):
    inner = folds(training.participant.unique(), 3)
    candidates = []
    for algorithm in ALGORITHMS:
        rows = []
        for valid_ids in inner:
            fitting = training[~training.participant.isin(valid_ids)]
            validation = training[training.participant.isin(valid_ids)].copy()
            assert not set(fitting.participant) & set(validation.participant)
            artifact = fit(fitting, algorithm)
            validation['score'] = learning.predict(artifact, validation);rows.append(validation)
        frame = pd.concat(rows, ignore_index=True)
        candidates.append({'algorithm':algorithm, 'balanced_accuracy':metrics(frame, 'score')['balanced_accuracy']})
    winner = max(candidates, key=lambda item: -1 if item['balanced_accuracy'] is None else item['balanced_accuracy'])
    return {'algorithm':winner['algorithm'], 'candidates':candidates, 'inner_validation_people':inner}


def run(root):
    out = root/OUT
    if (out/'evaluation.json').exists():
        raise ValueError('Completed evaluation exists; verify saved results instead')
    preserved = [root/'experiments/005-swell-protocol.json', root/'results/swell-v1/report.json',
                 root/'results/swell-v1/frozen-selection.json', root/'src/neurasign_engine/swell.py',
                 root/'src/neurasign_engine/personalization.py', root/'src/neurasign_engine/short_window_report.py']
    freeze = {'protocol_sha256':sha(root/PROTOCOL), 'training_code_sha256':sha(Path(__file__)),
              'preserved_files':{str(path.relative_to(root)):sha(path) for path in preserved}}
    write_json(out/'run-start.json', freeze)
    data, audit = prepare(root)
    outer = folds(data.participant.unique(), 5)
    selections = []
    with threadpool_limits(limits=1):
        for i, valid_ids in enumerate(outer):
            training = data[~data.participant.isin(valid_ids)]
            chosen = select(training)
            selections.append({'fold':i, 'training_people': sorted(training.participant.unique()),
                               'validation_people':valid_ids, **chosen})
            print(json.dumps({'swell_stress_selection':i+1, 'of':len(outer), 'algorithm':chosen['algorithm']}), flush=True)
    write_json(out/'frozen-selection.json', {'run':freeze, 'data_sha256':audit['data_sha256'], 'selections':selections})
    results = [];artifacts = []
    with threadpool_limits(limits=1):
        for selection in selections:
            i = selection['fold'];ids = selection['validation_people']
            training = data[~data.participant.isin(ids)];validation = data[data.participant.isin(ids)].copy()
            validation['majority'] = learning.majority(training)
            for arm, algorithm in [('fixed', 'logit1'), ('selected', selection['algorithm'])]:
                artifact = fit(training, algorithm)
                validation[arm] = learning.predict(artifact, validation)
                path = root/f'models/swell-stress-v1/fold-{i}-{arm}.joblib';path.parent.mkdir(parents=True, exist_ok=True)
                joblib.dump(artifact, path)
                artifacts.append({'fold':i, 'arm':arm, 'file':str(path.relative_to(root)), 'sha256':sha(path)})
            validation['fold'] = i;results.append(validation)
    predictions = pd.concat(results, ignore_index=True).sort_values('row_id')
    path = out/'predictions.csv.gz';predictions.to_csv(path, index=False, compression={'method':'gzip', 'mtime':0})
    report = {'arms':{arm:metrics(predictions, arm) for arm in ('majority', 'fixed', 'selected')},
              'audit':audit, 'scope':'Development nested person-grouped CV only; chest ECG/finger EDA, not wrist transfer.'}
    write_json(out/'report.json', report)
    write_json(out/'evaluation.json', {'predictions_sha256':sha(path), 'selection_sha256':sha(out/'frozen-selection.json'), 'artifacts':artifacts})
    lines = ['# Experiment 013: SWELL self-reported stress', '',
             '**Separate offline research benchmark. No production integration or wrist-device accuracy claim.**', '',
             'The target is the actual `Stress` questionnaire rating. Research cutoffs are ≤3⅓ (low) and ≥6⅔ (high), '
             'with middle ratings excluded. Experimental condition is neither the target nor a predictor. '
             'The only inputs are HR, RMSSD and SCL from chest ECG and finger conductance.', '',
             f"The comparison retains {audit['people']} of the original 20 development people, {audit['blocks']} blocks and {audit['minutes']} minutes. "
             f"It excludes {audit['middle_minutes']} middle-rated minutes and {audit['missing_rating_minutes']} missing ratings among "
             f"{audit['development_usable_minutes']} minutes with physiological data. The original five test people remain closed.", '',
             'Each outer fold holds out whole people. Three inner person-disjoint folds choose among logistic regression, RBF SVM, '
             'ExtraTrees and CatBoost, with preprocessing fitted only on the respective training data. All outer choices were saved '
             'before computing their out-of-fold predictions. Results weight people equally, then blocks equally.', '',
             '| Arm | Accuracy | Balanced accuracy | Low recall | High recall | Macro F1 | Within-person balanced |',
             '|---|---:|---:|---:|---:|---:|---:|']
    for arm, values in report['arms'].items():
        lines.append('| '+arm+' | '+' | '.join('n/a' if values[k] is None else f'{values[k]:.1%}' for k in
                     ('accuracy','balanced_accuracy','low_recall','high_recall','macro_f1','within_person_balanced_accuracy'))+' |')
    lines += ['', f"Only {report['arms']['selected']['people_with_both_classes']} evaluated people have both low and high blocks. "
              'Within-person balanced accuracy excludes single-class people, so the pooled balanced measure is primary here.', '',
              'These are repeated block ratings, not independently labeled minutes or instantaneous stress. Development participants '
              'appeared in earlier research; this is not an untouched external test. No fatigue/readiness labels are created. '
              'The source remains subject to its original research-use license. Scores are not calibrated confidence.', '',
              'Reproduce with `scripts/run_swell_stress.py run`; inspect the completed run with `scripts/run_swell_stress.py verify`. '
              'Saved artifacts, predictions, frozen folds and reports live in ignored `models/swell-stress-v1/` and `results/swell-stress-v1/`.']
    (root/'experiments/013-swell-stress-results.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps({a:{k:v[k] for k in ('accuracy','balanced_accuracy','low_recall','high_recall')} for a,v in report['arms'].items()}), flush=True)


def verify(root):
    out = root/OUT;selection = json.loads((out/'frozen-selection.json').read_text())
    evaluation = json.loads((out/'evaluation.json').read_text());report = json.loads((out/'report.json').read_text())
    freeze = selection['run']
    assert sha(Path(__file__)) == freeze['training_code_sha256'] and sha(root/PROTOCOL) == freeze['protocol_sha256']
    for path, digest in freeze['preserved_files'].items():
        assert sha(root/path) == digest
    source = root/'data/prepared/swell-stress-v1/minutes.csv.gz'
    assert sha(source) == selection['data_sha256']
    assert sha(out/'predictions.csv.gz') == evaluation['predictions_sha256']
    assert sha(out/'frozen-selection.json') == evaluation['selection_sha256']
    data = pd.read_csv(source);pred = pd.read_csv(out/'predictions.csv.gz')
    assert set(data.row_id) == set(pred.row_id) and not pred.row_id.duplicated().any()
    assert not set(data.participant) & set(report['audit']['excluded_test_people'])
    for choice in selection['selections']:
        training = data[~data.participant.isin(choice['validation_people'])]
        assert set(choice['training_people']) == set(training.participant)
        assert not set(choice['training_people']) & set(choice['validation_people'])
        assert sorted(p for ids in choice['inner_validation_people'] for p in ids) == sorted(choice['training_people'])
        assert choice['algorithm'] == max(choice['candidates'],key=lambda x:-1 if x['balanced_accuracy'] is None else x['balanced_accuracy'])['algorithm']
        saved = pred[pred.fold == choice['fold']]
        assert set(saved.participant) == set(choice['validation_people'])
        np.testing.assert_array_equal(saved.majority, np.full(len(saved), learning.majority(training)))
    for record in evaluation['artifacts']:
        path = root/record['file'];assert sha(path) == record['sha256']
        artifact = joblib.load(path)
        assert artifact['columns'] == FEATURES and artifact['production_enabled'] is False
        choice = selection['selections'][record['fold']]
        assert artifact['training_people'] == choice['training_people']
        saved = pred[pred.fold == record['fold']].copy()
        assert not set(artifact['fitting_row_ids']) & set(saved.row_id)
        saved['outcome'] = 1-saved.outcome;saved['stress'] = -999;saved['participant'] = 'irrelevant'
        with threadpool_limits(limits=1):
            np.testing.assert_allclose(learning.predict(artifact,saved),saved[record['arm']],atol=1e-12,rtol=0)
    checks = 0
    for arm in ('majority','fixed','selected'):
        assert metrics(pred,arm) == report['arms'][arm]
        reference = learning.metrics(pred,pred[arm])
        for key in ('accuracy','balanced_accuracy','within_person_balanced_accuracy','low_recall','high_recall'):
            np.testing.assert_allclose(reference[key],report['arms'][arm][key],atol=1e-12,rtol=0);checks += 1
    result = {'status':'passed','artifact_replays':len(evaluation['artifacts']),'independent_metric_checks':checks,
              'previous_files_unchanged':True,'person_disjoint_nested_folds':True,'report_sha256':sha(out/'report.json')}
    write_json(out/'verification.json', result);print(json.dumps(result),flush=True)
