"""Experiment 010: calibrate on Lab1, predict the separate Lab2 session."""
from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
import json
from pathlib import Path
import warnings

import joblib
import numpy as np
import pandas as pd
from scipy.special import expit
from sklearn.ensemble import ExtraTreesClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import FunctionTransformer, RobustScaler
from sklearn.svm import SVC
from threadpoolctl import threadpool_limits

from .schema import SEED, TARGETS
from .transfer_features import FEATURES
from .transfer_training import sha, write_json, thin

OUTPUTS = ['mental_effort', 'mental_demand']
ALGORITHMS = ['logit0.1', 'logit1', 'logit10', 'rbf0.1', 'rbf1', 'rbf10', 'extra', 'cat4']
CONFIGS = [{'profile': p, 'algorithm': a} for p in ['all', 'history'] for a in ALGORITHMS]
FIXED = {'profile': 'all', 'algorithm': 'logit1'}
ARMS = ['generic_constant', 'personal_constant', 'generic_fixed', 'personal_fixed', 'hybrid_fixed',
        'generic_selected', 'personal_selected', 'hybrid_selected']


def labels(values, target):
    low, high = (2, 4) if target == 'mental_effort' else (100/3, 200/3)
    value = np.asarray(values, float)
    return np.where(value <= low, 0., np.where(value >= high, 1., np.nan))


def columns(config):
    result = FEATURES + ([f+'__delta' for f in FEATURES] if config['profile'] == 'history' else [])
    assert not set(result) & (set(TARGETS) | {'outcome', 'participant', 'session', 'source_end', 'unit_id'})
    return result


def observation_weights(frame):
    """Each person contributes one unit, divided equally over tasks and windows."""
    tasks = frame.groupby('participant').unit_id.transform('nunique').to_numpy()
    windows = frame.groupby(['participant', 'unit_id']).unit_id.transform('size').to_numpy()
    w = 1./(tasks*windows)
    return w/w.sum()


def training_weights(frame, personal_id=None):
    w = observation_weights(frame)
    if personal_id is not None:
        own = frame.participant.to_numpy() == personal_id
        if not own.any() or own.all():
            raise ValueError('Hybrid requires own and other-person calibration')
        w[own] *= .5/w[own].sum()
        w[~own] *= .5/w[~own].sum()
    y = frame.outcome.to_numpy(int)
    if len(np.unique(y)) == 2:
        for label in (0, 1):
            mask = y == label
            w[mask] *= .5/w[mask].sum()
    return w/w.mean()


def majority(frame):
    w = observation_weights(frame)
    return int(np.sum(w*frame.outcome.to_numpy()) > .5)


def classifier(config):
    algorithm = config['algorithm']
    if algorithm.startswith('logit'):
        estimator = LogisticRegression(C=float(algorithm[5:]), max_iter=2000, random_state=SEED)
    elif algorithm.startswith('rbf'):
        estimator = SVC(C=float(algorithm[3:]), kernel='rbf', gamma='scale', probability=False)
    elif algorithm == 'extra':
        estimator = ExtraTreesClassifier(n_estimators=150, max_depth=6, min_samples_leaf=5,
                                          random_state=SEED, n_jobs=1)
    elif algorithm == 'cat4':
        from catboost import CatBoostClassifier
        estimator = CatBoostClassifier(iterations=200, depth=4, learning_rate=.04, l2_leaf_reg=10,
                    loss_function='Logloss', random_seed=SEED, thread_count=1, verbose=False, allow_writing_files=False)
    else:
        raise ValueError(algorithm)
    return make_pipeline(SimpleImputer(strategy='median', add_indicator=True, keep_empty_features=True),
                         RobustScaler(quantile_range=(10, 90)),
                         FunctionTransformer(np.tanh, feature_names_out='one-to-one'), estimator)


def fit_model(training, config, personal_id=None):
    if set(training.session) != {'Lab1'} or training.outcome.isna().any():
        raise ValueError('Only labeled Lab1 rows may fit any model or preprocessing')
    fitting = thin(training)
    artifact = {'config': config, 'columns': columns(config), 'training_session': 'Lab1',
                'training_people': sorted(training.participant.unique()),
                'training_units': sorted(training.unit_id.unique()),
                'fitting_row_ids': fitting.row_id.tolist(), 'personal_id': personal_id,
                'production_enabled': False, 'score_is_calibrated_confidence': False}
    if training.outcome.nunique() == 1:
        artifact['constant'] = int(training.outcome.iloc[0])
    else:
        model = classifier(config)
        weight_key = model.steps[-1][0]+'__sample_weight'
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', category=RuntimeWarning)
            model.fit(fitting[artifact['columns']], fitting.outcome.to_numpy(int),
                      **{weight_key: training_weights(fitting, personal_id)})
        artifact['model'] = model
    return artifact


def predict(artifact, frame):
    if 'constant' in artifact:
        return np.full(len(frame), artifact['constant'], dtype=float)
    model = artifact['model']
    x = frame[artifact['columns']]
    if artifact['config']['algorithm'].startswith('rbf'):
        score = expit(model.decision_function(x))
    else:
        score = model.predict_proba(x)[:, list(model.classes_).index(1)]
    score = np.asarray(score, float)
    assert np.isfinite(score).all() and ((score >= 0) & (score <= 1)).all()
    return score


def metrics(frame, scores):
    score = np.asarray(scores, float)
    assert len(score) == len(frame) and np.isfinite(score).all()
    y = frame.outcome.to_numpy(int);predicted = (score >= .5).astype(int)
    w = observation_weights(frame)
    cm = np.zeros((2, 2));np.add.at(cm, (y, predicted), w)
    recall = [float(cm[i, i]/cm[i].sum()) if cm[i].sum() else None for i in (0, 1)]
    people = {}
    for person, group in frame.assign(predicted=predicted).groupby('participant'):
        task = group.assign(correct=(group.outcome == group.predicted)).groupby(['unit_id', 'outcome']).correct.mean().reset_index()
        perclass = task.groupby('outcome').correct.mean()
        people[person] = {'accuracy': float(task.correct.mean()),
                         'balanced_accuracy': float(perclass.mean()) if len(perclass) == 2 else None,
                         'low_recall': float(perclass.get(0)) if 0 in perclass else None,
                         'high_recall': float(perclass.get(1)) if 1 in perclass else None,
                         'tasks': len(task), 'windows': len(group)}
    balanced_people = [v['balanced_accuracy'] for v in people.values() if v['balanced_accuracy'] is not None]
    return {'accuracy': float(np.trace(cm)),
            'balanced_accuracy': float(np.mean(recall)) if all(x is not None for x in recall) else None,
            'within_person_balanced_accuracy': float(np.mean(balanced_people)) if balanced_people else None,
            'people_with_both_classes': len(balanced_people), 'low_recall': recall[0], 'high_recall': recall[1],
            'confusion_matrix_person_task_weighted': cm.tolist(), 'people': len(people),
            'tasks': int(frame.unit_id.nunique()), 'windows': len(frame), 'per_person': people}


def union_seconds(ends, width=60.):
    total = 0.;left = right = None
    for end in sorted(ends):
        start = end-width
        if right is None or start > right:
            if right is not None:
                total += right-left
            left, right = start, end
        else:
            right = max(right, end)
    return total+(0. if right is None else right-left)


def prepare(root):
    source = root/'data/prepared/transfer-v1/universe.csv.gz'
    frame = pd.read_csv(source)
    split = json.loads((root/'experiments/split-v1.json').read_text())
    assert set(frame.participant) <= set(split['development'])
    frame['row_id'] = frame.index
    frame = frame[frame.session.isin(['Lab1', 'Lab2'])].copy()
    assert not frame.duplicated(['participant', 'session', 'source_end']).any()
    destination = root/'data/prepared/personalization-v1'
    destination.mkdir(parents=True, exist_ok=True)
    result = {'input_sha256': sha(source), 'protocol_sha256': sha(root/'experiments/010-personalization-protocol.json'),
              'targets': {}, 'files': {}, 'original_test_excluded': split['test']}
    for target in OUTPUTS:
        selected = frame.copy();selected['outcome'] = labels(selected[target], target)
        selected = selected[selected.outcome.notna()].copy()
        selected.outcome = selected.outcome.astype(int)
        assert selected.groupby('unit_id').outcome.nunique().max() == 1
        train = selected[selected.session == 'Lab1']
        available = sorted(set(train.participant) & set(selected.loc[selected.session == 'Lab2', 'participant']))
        evaluation = selected[(selected.session == 'Lab2') & selected.participant.isin(available)]
        people = {}
        for person in available:
            one = train[train.participant == person];two = evaluation[evaluation.participant == person]
            counts = one.drop_duplicates('unit_id').outcome.value_counts()
            original = frame[(frame.participant == person) & (frame.session == 'Lab1')]
            people[person] = {'lab1_tasks_low': int(counts.get(0, 0)), 'lab1_tasks_high': int(counts.get(1, 0)),
                             'adequate_calibration': bool(min(counts.get(0, 0), counts.get(1, 0)) >= 2),
                             'single_class_calibration': one.outcome.nunique() == 1,
                             'calibration_evidence_minutes': union_seconds(one.source_end)/60,
                             'full_lab1_evidence_minutes': union_seconds(original.source_end)/60,
                             'calibration_span_minutes': float((one.source_end.max()-one.source_end.min()+60)/60),
                             'lab1_labeled_windows': len(one), 'lab2_scored_windows': len(two),
                             'lab2_tasks_low': int(two.loc[two.outcome == 0, 'unit_id'].nunique()),
                             'lab2_tasks_high': int(two.loc[two.outcome == 1, 'unit_id'].nunique())}
        for name, data in [('lab1', train), ('lab2', evaluation)]:
            path = destination/(target+'-'+name+'.csv.gz')
            # Only the current target and explicitly permitted predictors are kept.
            cols = [*FEATURES, *[f+'__delta' for f in FEATURES],
                    'participant', 'session', 'unit_id', 'window_end', 'source_end', 'row_id', target, 'outcome']
            data[cols].to_csv(path, index=False, compression={'method': 'gzip', 'mtime': 0})
            result['files'][path.name] = sha(path)
        result['targets'][target] = {'paired_people': available, 'people': people,
            'lab1_total_windows': int((frame.session == 'Lab1').sum()), 'lab1_scored_windows': len(train),
            'lab1_missing_label_windows': int(((frame.session == 'Lab1') & frame[target].isna()).sum()),
            'lab2_total_windows': int((frame.session == 'Lab2').sum()),
            'lab2_extreme_label_windows_before_pairing': int((selected.session == 'Lab2').sum()),
            'lab2_scored_windows': len(evaluation), 'lab2_scored_tasks': int(evaluation.unit_id.nunique()),
            'lab2_windows_in_paired_people': int(((frame.session == 'Lab2') & frame.participant.isin(available)).sum()),
            'adequately_calibrated_people': [p for p, v in people.items() if v['adequate_calibration']]}
        print(json.dumps({'target': target, 'paired_people': len(available), 'scored_windows': len(evaluation),
                          'adequate_calibration': len(result['targets'][target]['adequately_calibrated_people'])}), flush=True)
    write_json(destination/'audit.json', result)


def load_frame(root, target, session):
    assert session in ('lab1', 'lab2')
    base = root/'data/prepared/personalization-v1'
    audit = json.loads((base/'audit.json').read_text())
    path = base/(target+'-'+session+'.csv.gz')
    assert sha(path) == audit['files'][path.name]
    frame = pd.read_csv(path)
    assert set(frame.session) == {session.capitalize()}
    return frame


def tuning_splits(training, personal):
    """Validation tasks/people are whole groups, never shuffled window fragments."""
    assert set(training.session) == {'Lab1'}
    if personal:
        assert training.participant.nunique() == 1
        units = training[['unit_id', 'outcome']].drop_duplicates().sort_values('unit_id').reset_index(drop=True)
        counts = units.outcome.value_counts()
        n = min(3, int(counts.get(0, 0)), int(counts.get(1, 0)))
        if n < 2:
            return []
        result = []
        for _, valid in StratifiedKFold(n, shuffle=True, random_state=SEED).split(units.unit_id, units.outcome):
            ids = set(units.iloc[valid].unit_id)
            result.append((training[~training.unit_id.isin(ids)], training[training.unit_id.isin(ids)]))
        return result
    people = sorted(training.participant.unique())
    if len(people) < 2:
        return []
    folds = np.array_split(np.random.default_rng(SEED).permutation(people), min(3, len(people)))
    return [(training[~training.participant.isin(ids)], training[training.participant.isin(ids)]) for ids in folds]


def select_configuration(training, personal):
    partitions = tuning_splits(training, personal)
    if not partitions:
        return {'config': FIXED, 'reason': 'insufficient_Lab1_groups_for_tuning', 'candidates': [], 'folds': []}
    scored = []
    for config in CONFIGS:
        rows = []
        for fitting, validation in partitions:
            assert not set(fitting.unit_id) & set(validation.unit_id)
            artifact = fit_model(fitting, config)
            row = validation.copy();row['score'] = predict(artifact, validation);rows.append(row)
        predictions = pd.concat(rows, ignore_index=True)
        score = metrics(predictions, predictions.score)['balanced_accuracy']
        scored.append({'config': config, 'balanced_accuracy': score})
    chosen = max(scored, key=lambda r: -1 if r['balanced_accuracy'] is None else r['balanced_accuracy'])
    return {'config': chosen['config'], 'reason': 'Lab1_grouped_validation', 'candidates': scored,
            'folds': [{'training_units': sorted(a.unit_id.unique()), 'validation_units': sorted(b.unit_id.unique()),
                       'training_people': sorted(a.participant.unique()), 'validation_people': sorted(b.participant.unique())}
                      for a, b in partitions]}


def selection_job(root_string, target, mode, key, ids):
    root = Path(root_string);frame = load_frame(root, target, 'lab1')
    training = frame[frame.participant.isin(ids)] if mode == 'personal' else frame[~frame.participant.isin(ids)]
    with threadpool_limits(limits=1):
        selected = select_configuration(training, mode == 'personal')
    result = {'target': target, 'mode': mode, 'key': key, 'training_people': sorted(training.participant.unique()),
              'training_units': sorted(training.unit_id.unique()), **selected}
    write_json(root/'results/personalization-v1/selection'/(target+'__'+mode+'__'+str(key)+'.json'), result)
    return result


def select(root):
    out = root/'results/personalization-v1';out.mkdir(parents=True, exist_ok=True)
    audit = json.loads((root/'data/prepared/personalization-v1/audit.json').read_text())
    folds = json.loads((root/'results/transfer-v1/universe/protocol.json').read_text())['folds']
    freeze = {'protocol_sha256': sha(root/'experiments/010-personalization-protocol.json'),
              'data_audit_sha256': sha(root/'data/prepared/personalization-v1/audit.json'),
              'training_code_sha256': sha(Path(__file__)), 'folds': folds}
    existing = out/'selection-run.json'
    if existing.exists():
        assert json.loads(existing.read_text()) == freeze
    else:
        write_json(existing, freeze)
    jobs = []
    for target in OUTPUTS:
        available = audit['targets'][target]['paired_people']
        for fold, ids in enumerate(folds):
            if set(ids) & set(available):
                jobs.append((str(root), target, 'generic', fold, ids))
        for person in available:
            jobs.append((str(root), target, 'personal', person, [person]))
    results = []
    with ProcessPoolExecutor(max_workers=6) as pool:
        futures = []
        for job in jobs:
            _, t, m, k, _ = job
            cache = out/'selection'/(t+'__'+m+'__'+str(k)+'.json')
            if cache.exists():
                results.append(json.loads(cache.read_text()))
            else:
                futures.append(pool.submit(selection_job, *job))
        for future in as_completed(futures):
            result = future.result();results.append(result)
            print(json.dumps({'selections_completed': len(results), 'of': len(jobs), 'target': result['target'],
                              'mode': result['mode'], 'key': result['key'], 'config': result['config']}), flush=True)
    write_json(out/'frozen-selection.json', {'frozen_utc': datetime.now(timezone.utc).isoformat(),
        'evaluation_started': False, 'run': freeze, 'selections': results,
        'old_test_report_sha256': sha(root/'results/transfer-v1/final/test-report.json'),
        'old_papagei_report_sha256': sha(root/'results/papagei-v1/report.json')})


def evaluation_job(root_string, target, person, fold, excluded, generic_config, personal_config):
    root = Path(root_string);train = load_frame(root, target, 'lab1');evaluation = load_frame(root, target, 'lab2')
    evaluation = evaluation[evaluation.participant == person]
    generic = train[~train.participant.isin(excluded)]
    personal = train[train.participant == person]
    hybrid = pd.concat([generic, personal], ignore_index=True)
    assert person not in set(generic.participant) and set(personal.participant) == {person}
    metadata = evaluation[['participant', 'session', 'unit_id', 'source_end', 'window_end', 'row_id', target, 'outcome']].copy()
    metadata['fold'] = fold
    artifacts = []
    with threadpool_limits(limits=1):
        for arm in ARMS:
            if arm.endswith('constant'):
                data = generic if arm.startswith('generic') else personal
                score = np.full(len(evaluation), majority(data), dtype=float)
            else:
                mode, variant = arm.split('_')
                data = {'generic': generic, 'personal': personal, 'hybrid': hybrid}[mode]
                config = FIXED if variant == 'fixed' else personal_config if mode == 'personal' else generic_config
                artifact = fit_model(data, config, person if mode == 'hybrid' else None)
                score = predict(artifact, evaluation)
                path = root/'models/personalization-v1'/target/person/(arm+'.joblib')
                path.parent.mkdir(parents=True, exist_ok=True)
                joblib.dump(artifact, path)
                artifacts.append({'arm': arm, 'file': str(path.relative_to(root)), 'sha256': sha(path),
                                  'training_people': artifact['training_people'], 'training_units': artifact['training_units'],
                                  'single_class_fallback': 'constant' in artifact, 'config': config})
            metadata[arm] = score
    out = root/'results/personalization-v1/predictions';out.mkdir(parents=True, exist_ok=True)
    path = out/(target+'__'+person+'.csv.gz')
    metadata.to_csv(path, index=False, compression={'method': 'gzip', 'mtime': 0})
    return {'target': target, 'person': person, 'fold': fold, 'prediction_file': str(path.relative_to(root)),
            'predictions_sha256': sha(path), 'artifacts': artifacts}


def evaluate(root):
    out = root/'results/personalization-v1'
    selection_path = out/'frozen-selection.json'
    selected = json.loads(selection_path.read_text())
    assert sha(Path(__file__)) == selected['run']['training_code_sha256']
    assert not (out/'evaluation.json').exists(), 'Evaluation already saved; verify saved predictions instead.'
    lookup = {(r['target'], r['mode'], str(r['key'])): r['config'] for r in selected['selections']}
    audit = json.loads((root/'data/prepared/personalization-v1/audit.json').read_text())
    jobs = []
    for target in OUTPUTS:
        for person in audit['targets'][target]['paired_people']:
            fold = next(i for i, ids in enumerate(selected['run']['folds']) if person in ids)
            jobs.append((str(root), target, person, fold, selected['run']['folds'][fold],
                         lookup[(target, 'generic', str(fold))], lookup[(target, 'personal', person)]))
    results = []
    write_json(out/'evaluation-start.json', {'started_utc': datetime.now(timezone.utc).isoformat(),
                                           'selection_sha256': sha(selection_path)})
    with ProcessPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(evaluation_job, *job) for job in jobs]
        for future in as_completed(futures):
            result = future.result();results.append(result)
            print(json.dumps({'evaluated': len(results), 'of': len(jobs), 'target': result['target'], 'person': result['person']}), flush=True)
    write_json(out/'evaluation.json', {'selection_sha256': sha(selection_path), 'jobs': results})
