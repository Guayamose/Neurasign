"""Experiment 011: matched one-second evidence versus sixty-second evidence.

All model selection uses Lab1 only. Existing experiments and holdouts are read-only.
"""
from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from functools import lru_cache
import json
from pathlib import Path
import warnings

import joblib
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

from . import personalization as prior
from .personalization import ARMS, predict
from .short_window_features import SHORT_FEATURES
from .transfer_features import FEATURES
from .transfer_training import sha, thin, write_json

PROFILES = ['short1', 'short60', 'legacy60']
TARGETS = ['mental_demand', 'mental_effort']
ALGORITHMS = ['logit1', 'rbf1', 'extra', 'cat4']
META = ['participant', 'session', 'unit_id', 'source_end', 'window_end', 'row_id', 'outcome']
OUT = 'results/short-window-v1'
PROTOCOL = 'experiments/011-short-window-protocol.json'
AUDIT = 'data/prepared/short-window-v1/audit.json'


def feature_columns(profile):
    if profile not in PROFILES:
        raise ValueError('Unknown evidence profile')
    return list(FEATURES if profile == 'legacy60' else SHORT_FEATURES)


@lru_cache(maxsize=16)
def _short_table(root_string, width):
    return pd.read_csv(Path(root_string)/f'data/prepared/short-window-v1/window-{width}.csv.gz').set_index('row_id', verify_integrity=True)


def load_frame(root, profile, target, session):
    if target not in TARGETS or session not in ('lab1', 'lab2'):
        raise ValueError('Unknown target or session')
    base = prior.load_frame(root, target, session)
    columns = feature_columns(profile)
    if profile == 'legacy60':
        return base[[*META, target, *columns]].copy()
    short = _short_table(str(root), 1 if profile == 'short1' else 60).loc[base.row_id].reset_index()
    for key in ('participant', 'session', 'unit_id', 'row_id'):
        assert np.array_equal(base[key].to_numpy(), short[key].to_numpy()), key
    for key in ('window_end', 'source_end', target):
        np.testing.assert_allclose(base[key], short[key], rtol=0, atol=1e-6, equal_nan=True)
    frame = base[[*META, target]].copy().reset_index(drop=True)
    frame[columns] = short[columns].to_numpy()
    return frame


def fit(training, profile, algorithm, personal_id=None):
    if set(training.session) != {'Lab1'} or training.outcome.isna().any():
        raise ValueError('Fitting requires labeled Lab1 data only')
    if algorithm not in ALGORITHMS:
        raise ValueError('Algorithm outside the frozen search')
    cols = feature_columns(profile)
    assert not set(cols) & (set(TARGETS) | set(META))
    fitting = thin(training)
    config = {'profile': profile, 'algorithm': algorithm}
    artifact = {'config': config, 'columns': cols, 'training_session': 'Lab1',
                'training_people': sorted(training.participant.unique()),
                'training_units': sorted(training.unit_id.unique()),
                'fitting_row_ids': fitting.row_id.tolist(), 'personal_id': personal_id,
                'evidence_seconds': 1 if profile == 'short1' else 60,
                'production_enabled': False, 'score_is_calibrated_confidence': False}
    if training.outcome.nunique() == 1:
        artifact['constant'] = int(training.outcome.iloc[0])
    else:
        model = prior.classifier(config)
        with warnings.catch_warnings(), threadpool_limits(limits=1):
            warnings.simplefilter('ignore', category=RuntimeWarning)
            model.fit(fitting[cols], fitting.outcome.to_numpy(int),
                      **{model.steps[-1][0]+'__sample_weight': prior.training_weights(fitting, personal_id)})
        artifact['model'] = model
    return artifact


def choose(training, profile, personal):
    partitions = prior.tuning_splits(training, personal)
    if not partitions:
        return {'config': {'profile': profile, 'algorithm': 'logit1'},
                'reason': 'insufficient_Lab1_groups_for_tuning', 'candidates': [], 'folds': []}
    candidates = []
    for algorithm in ALGORITHMS:
        rows = []
        for fitting, validation in partitions:
            assert not set(fitting.unit_id) & set(validation.unit_id)
            artifact = fit(fitting, profile, algorithm)
            part = validation.copy();part['score'] = predict(artifact, validation);rows.append(part)
        predictions = pd.concat(rows, ignore_index=True)
        candidates.append({'config': {'profile': profile, 'algorithm': algorithm},
                           'balanced_accuracy': prior.metrics(predictions, predictions.score)['balanced_accuracy']})
    winner = max(candidates, key=lambda row: -1 if row['balanced_accuracy'] is None else row['balanced_accuracy'])
    return {'config': winner['config'], 'reason': 'Lab1_grouped_validation', 'candidates': candidates,
            'folds': [{'training_units': sorted(a.unit_id.unique()), 'validation_units': sorted(b.unit_id.unique()),
                       'training_people': sorted(a.participant.unique()), 'validation_people': sorted(b.participant.unique())}
                      for a, b in partitions]}


def selection_job(root_string, profile, target, mode, key, ids):
    root = Path(root_string);frame = load_frame(root, profile, target, 'lab1')
    training = frame[frame.participant.isin(ids)] if mode == 'personal' else frame[~frame.participant.isin(ids)]
    with threadpool_limits(limits=1):
        selected = choose(training, profile, mode == 'personal')
    result = {'profile': profile, 'target': target, 'mode': mode, 'key': key,
              'training_people': sorted(training.participant.unique()),
              'training_units': sorted(training.unit_id.unique()), **selected}
    write_json(root/OUT/'selection'/f'{profile}__{target}__{mode}__{key}.json', result)
    return result


def preserved_files(root):
    paths = list((root/'src/neurasign_engine').glob('*.py')) + list((root/'scripts').glob('*.py'))
    paths += list((root/'experiments').glob('*'))
    paths += list((root/'data/prepared/personalization-v1').glob('*'))
    paths += [root/p for p in ['results/personalization-v1/report.json',
                              'results/personalization-v1/evaluation.json',
                              'results/personalization-v1/frozen-selection.json',
                              'results/transfer-v1/final/test-report.json',
                              'results/papagei-v1/report.json',
                              'data/prepared/transfer-v1/universe.csv.gz',
                              'data/prepared/causal-v3/provenance.json']]
    return {str(path.relative_to(root)): sha(path) for path in paths if path.is_file()
            and not path.name.startswith(('short_window', 'run_short_window', '011-'))}


def select(root):
    out = root/OUT;out.mkdir(parents=True, exist_ok=True)
    audit = json.loads((root/'data/prepared/personalization-v1/audit.json').read_text())
    folds = json.loads((root/'results/personalization-v1/frozen-selection.json').read_text())['run']['folds']
    freeze = {'protocol_sha256': sha(root/PROTOCOL), 'data_audit_sha256': sha(root/AUDIT),
              'training_code_sha256': sha(Path(__file__)), 'preserved_files': preserved_files(root), 'folds': folds,
              'feature_code_sha256': sha(Path(__file__).with_name('short_window_features.py')),
              'feature_files': {f'window-{w}.csv.gz': sha(root/f'data/prepared/short-window-v1/window-{w}.csv.gz') for w in (1, 60)}}
    manifest = out/'selection-run.json'
    if manifest.exists():
        assert json.loads(manifest.read_text()) == freeze, 'Frozen inputs changed'
    else:
        write_json(manifest, freeze)
    assert not (out/'evaluation.json').exists(), 'Evaluation already saved; verify instead of reselecting.'
    jobs = []
    for profile in PROFILES:
        for target in TARGETS:
            people = audit['targets'][target]['paired_people']
            for fold, ids in enumerate(folds):
                if set(ids) & set(people):
                    jobs.append((str(root), profile, target, 'generic', fold, ids))
            jobs.extend((str(root), profile, target, 'personal', person, [person]) for person in people)
    results = []
    with ProcessPoolExecutor(max_workers=6) as pool:
        futures = []
        for job in jobs:
            _, p, t, mode, key, _ = job
            cache = out/'selection'/f'{p}__{t}__{mode}__{key}.json'
            if cache.exists():
                results.append(json.loads(cache.read_text()))
            else:
                futures.append(pool.submit(selection_job, *job))
        for future in as_completed(futures):
            result = future.result();results.append(result)
            print(json.dumps({'selected': len(results), 'of': len(jobs), 'profile': result['profile'],
                              'target': result['target'], 'mode': result['mode'], 'config': result['config']}), flush=True)
    write_json(out/'frozen-selection.json', {'frozen_utc': datetime.now(timezone.utc).isoformat(),
                                            'run': freeze, 'selections': results})


def evaluation_job(root_string, profile, target, person, fold, excluded, generic_config, personal_config):
    root = Path(root_string);training = load_frame(root, profile, target, 'lab1')
    evaluation = load_frame(root, profile, target, 'lab2')
    evaluation = evaluation[evaluation.participant == person]
    generic = training[~training.participant.isin(excluded)]
    personal = training[training.participant == person]
    hybrid = pd.concat([generic, personal], ignore_index=True)
    assert person not in set(generic.participant) and set(personal.participant) == {person}
    metadata = evaluation[[*META, target]].copy();metadata['fold'] = fold
    artifacts = []
    with threadpool_limits(limits=1):
        for arm in ARMS:
            if arm.endswith('constant'):
                frame = generic if arm.startswith('generic') else personal
                scores = np.full(len(evaluation), prior.majority(frame), dtype=float)
            else:
                mode, variant = arm.split('_')
                algorithm = 'logit1' if variant == 'fixed' else (personal_config if mode == 'personal' else generic_config)['algorithm']
                frame = {'generic': generic, 'personal': personal, 'hybrid': hybrid}[mode]
                artifact = fit(frame, profile, algorithm, person if mode == 'hybrid' else None)
                scores = predict(artifact, evaluation)
                path = root/'models/short-window-v1'/profile/target/person/(arm+'.joblib')
                path.parent.mkdir(parents=True, exist_ok=True);joblib.dump(artifact, path)
                artifacts.append({'arm': arm, 'file': str(path.relative_to(root)), 'sha256': sha(path),
                                  'config': artifact['config'], 'single_class_fallback': 'constant' in artifact})
            metadata[arm] = scores
    path = root/OUT/'predictions'/f'{profile}__{target}__{person}.csv.gz'
    path.parent.mkdir(parents=True, exist_ok=True)
    metadata.to_csv(path, index=False, compression={'method': 'gzip', 'mtime': 0})
    return {'profile': profile, 'target': target, 'person': person, 'fold': fold,
            'prediction_file': str(path.relative_to(root)), 'predictions_sha256': sha(path), 'artifacts': artifacts}


def evaluate(root):
    out = root/OUT;selection_path = out/'frozen-selection.json'
    frozen = json.loads(selection_path.read_text());run = frozen['run']
    assert sha(Path(__file__)) == run['training_code_sha256']
    assert sha(root/PROTOCOL) == run['protocol_sha256'] and sha(root/AUDIT) == run['data_audit_sha256']
    assert sha(Path(__file__).with_name('short_window_features.py')) == run['feature_code_sha256']
    for name, digest in run['feature_files'].items():
        assert sha(root/'data/prepared/short-window-v1'/name) == digest
    for path, digest in run['preserved_files'].items():
        assert sha(root/path) == digest, path
    assert not (out/'evaluation.json').exists(), 'Evaluation already saved; verify instead.'
    choices = {(r['profile'], r['target'], r['mode'], str(r['key'])): r['config'] for r in frozen['selections']}
    audit = json.loads((root/'data/prepared/personalization-v1/audit.json').read_text())
    jobs = []
    for profile in PROFILES:
        for target in TARGETS:
            for person in audit['targets'][target]['paired_people']:
                fold = next(i for i, ids in enumerate(run['folds']) if person in ids)
                jobs.append((str(root), profile, target, person, fold, run['folds'][fold],
                             choices[(profile, target, 'generic', str(fold))], choices[(profile, target, 'personal', person)]))
    write_json(out/'evaluation-start.json', {'started_utc': datetime.now(timezone.utc).isoformat(),
                                           'selection_sha256': sha(selection_path)})
    results = []
    with ProcessPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(evaluation_job, *job) for job in jobs]
        for future in as_completed(futures):
            result = future.result();results.append(result)
            print(json.dumps({'evaluated': len(results), 'of': len(jobs), 'profile': result['profile'],
                              'target': result['target'], 'person': result['person']}), flush=True)
    write_json(out/'evaluation.json', {'selection_sha256': sha(selection_path), 'jobs': results})
