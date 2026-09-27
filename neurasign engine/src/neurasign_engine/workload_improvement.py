"""Experiment 021: nested development-only prediction of recorded overall NASA-TLX.

Anonymous academic research. No workplace inference or emotion output is enabled.
"""
from __future__ import annotations

from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
import csv
import hashlib
import io
import json
from pathlib import Path
import warnings

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import ExtraTreesRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import FunctionTransformer, RobustScaler
from sklearn.svm import SVR
from threadpoolctl import threadpool_limits

from .causal_data import source_manifest
from .data import verified_bytes
from .transfer_features import FEATURES
from .transfer_training import sha, write_json

SEED = 20260926
OUT = 'results/workload-improvement-v1'
DATA = 'data/prepared/workload-improvement-v1'
PROTOCOL = 'experiments/021-workload-improvement-protocol.json'
NATIVE = ['native_rmssd_ms', 'native_sdnn_ms', 'native_pnn50', 'native_coverage']
DERIVED = ['log_eda_mean', 'log_pulse_rmssd', 'log_pulse_sdnn', 'log_native_rmssd',
           'log_native_sdnn', 'log_best_rmssd', 'log_best_sdnn', 'native_minus_pulse_rmssd',
           'native_minus_pulse_sdnn', 'hr_to_log_rmssd', 'eda_to_motion_ratio']
SIGNALS = list(FEATURES) + NATIVE + DERIVED
PROFILES = ['legacy', 'temporal', 'reference']
ALGORITHMS = ['ridge1', 'ridge10', 'ridge100', 'ridge1000', 'svr10', 'svr30', 'extra', 'cat3']
CONFIGS = [{'profile': p, 'algorithm': a} for p in PROFILES for a in ALGORITHMS]
ARMS = ['constant', 'fixed_prior', 'selected']
DIMENSIONS = ['Mental Demand', 'Physical Demand', 'Temporal Demand', 'Performance', 'Effort', 'Frustration']


def feature_columns(profile):
    if profile == 'legacy':
        return [f+'__median' for f in FEATURES]
    if profile not in PROFILES:
        raise ValueError('Unknown feature profile')
    result = [f+'__'+stat for f in SIGNALS for stat in ('median', 'iqr', 'late_minus_early')]
    result += [f+'__observed_fraction' for f in NATIVE[:3]]
    if profile == 'reference':
        result += [f+'__past_reference_delta' for f in SIGNALS]
    assert not set(result) & {'target', 'participant', 'unit_id', 'active', 'source_end', 'mental_demand'}
    return result


def scalar_summary(values):
    finite = np.asarray(values, float);finite = finite[np.isfinite(finite)]
    return (float(np.median(finite)), float(np.quantile(finite, .75)-np.quantile(finite, .25))) if len(finite) else (np.nan, np.nan)


def enrich_windows(frame):
    """Pointwise transformations; never use labels, later windows or other people."""
    result = frame.copy()
    for target, source in [('log_eda_mean', 'eda_mean'), ('log_pulse_rmssd', 'pulse_interval_rmssd_ms'),
                           ('log_pulse_sdnn', 'pulse_interval_sdnn_ms'), ('log_native_rmssd', 'native_rmssd_ms'),
                           ('log_native_sdnn', 'native_sdnn_ms')]:
        result[target] = np.log1p(result[source].where(result[source] >= 0))
    for suffix in ('rmssd', 'sdnn'):
        native = result['native_'+suffix+'_ms'];pulse = result['pulse_interval_'+suffix+'_ms']
        best = native.where(native.notna(), pulse)
        result['log_best_'+suffix] = np.log1p(best.where(best >= 0))
        result['native_minus_pulse_'+suffix] = native-pulse
    result['hr_to_log_rmssd'] = result.heart_rate_mean/(1+result.log_best_rmssd)
    result['eda_to_motion_ratio'] = result.log_eda_mean/(1+np.maximum(result.motion_std, 0))
    return result


def aggregate_task(task, session):
    """One completed task is one observation; early/late thirds use elapsed time."""
    ordered = task.sort_values('source_end');end = ordered.source_end.to_numpy(float)
    first, last = float(end[0]), float(end[-1]);span = last-first
    early = ordered[end <= first+span/3]
    late = ordered[end >= last-span/3]
    # Unlabeled initial reference from this person's session; it ends before any
    # sample contributing to this task's first sixty-second window.
    reference = session[session.source_end <= first-60].sort_values('source_end').iloc[:15]
    values = {}
    for feature in SIGNALS:
        middle, spread = scalar_summary(ordered[feature])
        a, _ = scalar_summary(early[feature]);b, _ = scalar_summary(late[feature])
        values[feature+'__median'] = middle
        values[feature+'__iqr'] = spread
        values[feature+'__late_minus_early'] = b-a
        baseline, _ = scalar_summary(reference[feature]) if reference[feature].notna().sum() >= 3 else (np.nan, np.nan)
        values[feature+'__past_reference_delta'] = middle-baseline
    for feature in NATIVE[:3]:
        values[feature+'__observed_fraction'] = float(ordered[feature].notna().mean())
    return values


def recorded_tlx(path, source, manifest):
    """Verify the recorded weighted score against all 15 recorded pair comparisons."""
    rows = list(csv.reader(io.StringIO(verified_bytes(path, source, manifest).decode('utf-8-sig'))))
    header = rows[0];pair_columns = [c for c in header if '__vs__' in c]
    if len(pair_columns) != 15 or 'Weighted Nasa Score' not in header:
        raise ValueError('The source lacks the recorded NASA-TLX weights or total')
    result = {};audit = Counter();conflicts = set()
    for values in rows[1:]:
        audit['source_rows'] += 1
        if len(values) != len(header):
            audit['invalid_row_width'] += 1;continue
        row = dict(zip(header, values));segment = row.get('Task', '').strip()
        if segment == 'video_baseline':
            segment = 'relaxation_video'
        try:
            score = float(row['Weighted Nasa Score'])
            ratings = {name.lower().replace(' ', '_'): float(row[name]) for name in DIMENSIONS}
            if not segment or not np.isfinite([score, *ratings.values()]).all() or not all(0 <= v <= 100 for v in [score, *ratings.values()]):
                raise ValueError('Invalid NASA-TLX rating range')
            if any(row[c] not in c.split('__vs__') for c in pair_columns):
                raise ValueError('Invalid pair-comparison choice')
            weights = Counter(row[c] for c in pair_columns)
            reconstructed = sum(ratings[name]*weight for name, weight in weights.items())/15
            if abs(reconstructed-score) > .011:
                raise ValueError('Recorded NASA-TLX does not match its recorded weights')
        except (ValueError, KeyError):
            audit['invalid_or_inconsistent_score'] += 1;continue
        if segment in result and result[segment] != score:
            conflicts.add(segment)
        result[segment] = score;audit['verified_scores'] += 1
    for segment in conflicts:
        result.pop(segment, None)
    audit['conflicting_segments'] = len(conflicts)
    return result, dict(audit)


def person_folds(people, count, seed=SEED):
    people = sorted(str(v) for v in people)
    return [sorted(part.tolist()) for part in np.array_split(np.random.default_rng(seed).permutation(people), count)]


def protected_hashes(root):
    files = [root/'src/neurasign_engine'/name for name in ['data.py', 'schema.py', 'causal.py', 'causal_data.py',
        'external_labeled.py', 'transfer_features.py', 'transfer_training.py', 'personalization.py', 'short_window.py']]
    files += [p for p in (root/'experiments').iterdir() if p.is_file() and p.name[:3].isdigit() and int(p.name[:3]) <= 18]
    return {str(p.relative_to(root)): sha(p) for p in files}


def prepare(root):
    root = Path(root);destination = root/DATA;out = root/OUT
    if (root/PROTOCOL).exists() or (destination/'tasks.csv.gz').exists():
        raise ValueError('Experiment 021 already prepared; do not replace the registered comparison')
    split = json.loads((root/'experiments/split-v1.json').read_text())
    source, manifest = source_manifest(root)
    basepath = root/'data/prepared/transfer-v1/universe.csv.gz'
    nativepath = root/'data/prepared/transfer-v1/universe-native.csv.gz'
    nativeaudit = json.loads(nativepath.with_name('universe-native-audit.json').read_text())
    assert sha(basepath) == nativeaudit['base_table_sha256'] and sha(nativepath) == nativeaudit['output_sha256']
    # Read only predictor/identity columns from the old table, never old target
    # columns, and discard all non-Lab1 observations before feature computation.
    base = pd.read_csv(basepath, usecols=[*FEATURES, 'participant', 'session', 'unit_id', 'source_end', 'window_end'])
    assert set(base.participant) <= set(split['development'])
    base['old_row_id'] = np.arange(len(base));native = pd.read_csv(nativepath)
    assert len(base) == len(native)
    base = base[(base.session == 'Lab1') & base.participant.isin(split['development'])].copy()
    for feature in NATIVE:
        base[feature] = native.loc[base.old_row_id, feature].to_numpy()
    base = enrich_windows(base)
    records = json.loads((root/'data/prepared/causal-v3/provenance.json').read_text())
    provenance = {r['unit_id']: r for r in records if r['session'] == 'Lab1' and r['participant'] in split['development']}
    rows = [];label_audit = [];sources = {};coverage = Counter()
    for person, session in base.groupby('participant', sort=True):
        path = source/'UNIVERSE'/person/'Lab1'/'Task_Labels.csv'
        targets, info = recorded_tlx(path, source, manifest)
        sources[str(path.relative_to(source))] = sha(path)
        label_audit.append({'participant': person, **info})
        for unit, task in session.groupby('unit_id', sort=True):
            coverage['candidate_tasks'] += 1
            segment = provenance[unit]['segment'].split('/')[-1]
            if segment not in targets:
                coverage['missing_or_invalid_workload_reference'] += 1;continue
            if len(task) < 3:
                coverage['fewer_than_three_causal_windows'] += 1;continue
            rows.append({'row_id': unit, 'participant': person, 'session': 'Lab1', 'unit_id': unit,
                         'target': targets[segment], 'active': segment != 'relaxation_video',
                         'source_start': float(task.source_end.min()-60), 'source_end': float(task.source_end.max()),
                         'source_windows': len(task), **aggregate_task(task, session)})
    data = pd.DataFrame(rows).sort_values(['participant', 'source_end']).reset_index(drop=True)
    assert not data.unit_id.duplicated().any() and set(data.session) == {'Lab1'}
    assert set(data.participant) <= set(split['development']) and not set(data.participant) & set(split['test'])
    outer = person_folds(data.participant.unique(), 4)
    folds = [{'fold': i, 'evaluation_people': held,
              'training_people': sorted(set(data.participant)-set(held)),
              'inner_folds': person_folds(sorted(set(data.participant)-set(held)), 3, SEED+i+1)} for i, held in enumerate(outer)]
    protocol = {'experiment': 21, 'name': 'overall workload development improvement',
        'registered_utc': datetime.now(timezone.utc).isoformat(), 'registered_before_any_model_scoring': True,
        'population': 'Original 19 UNIVERSE development people, Lab1 only. Previously studied people: exploratory development research. Lab2, original five test people and all Mobile test records stay outside the experiment.',
        'target': 'Recorded Weighted Nasa Score, 0–100, verified against all 15 source pair choices and the six source ratings divided by 15, within source rounding tolerance .011. It is overall subjective NASA-TLX workload, including mental/physical/temporal demand, performance, effort and frustration; no separate emotion target or output.',
        'unit': 'One completed labeled Lab1 task, aggregated over its eligible 60-second causal windows. At least three windows required. This is post-task prediction, not instantaneous or one-second inference.',
        'inputs': {p: feature_columns(p) for p in PROFILES},
        'features': 'Legacy: medians of original28 causal features. Temporal: medians/IQR/late-minus-early thirds of original signals, verified manufacturer IBI summaries and declared log/quality transforms. Reference adds deviations from first up-to15 unlabeled same-session windows ending before task evidence starts, requiring3 finite values. No future task enters a reference.',
        'native_ibi': 'Existing checksum-verified three-waveform-block alignment and gap-safe manufacturer pulse intervals. Missing/gapped intervals remain absent; they are not ECG ground truth.',
        'excluded_predictors': ['all questionnaire answers and labels', 'task names/difficulty', 'person/session IDs', 'timestamps/task duration', 'EEG', 'future task measurements', 'target history'],
        'folds': folds, 'seed': SEED,
        'selection': '4 person-disjoint outer folds, each with 3 person-disjoint inner folds. All preprocessing and candidate/ensemble selection within outer-training people. Equal person weight then equal tasks. Select smallest inner person-balanced MAE; deterministic ties retain registered order.',
        'candidates': CONFIGS,
        'ensemble_candidates': 'Mean of top3 inner-OOF-ranked base candidates globally and within each of3 profiles:4 additional candidates, total28. Their inner scores are selection scores, not an independent validation estimate. Ensemble choice remains inside each outer training fold.',
        'models': 'Ridge alpha1/10/100/1000; RBF SVR C10/30 epsilon5 gamma=scale; ExtraTrees250 trees max_depth6 min_leaf3 max_features.8; CatBoost300 iterations depth3 learning_rate.035 l2_leaf_reg20 MAE. Median imputation+missingness flags, RobustScaler10–90 then tanh fitted separately on training folds. All scores clipped0–100.',
        'comparators': 'Training person/task-weighted median constant and fixed original28-feature Ridge100, both refitted on identical outer-training tasks. Prior algorithm/features, not reuse of a model trained on evaluation people. Different target/protocol from010/011, so their reported percentages are not directly comparable.',
        'metrics': 'Primary person-balanced MAE on all observed0–100 outcomes; also RMSE, weightedR2, agreement within10 points. Prespecified descriptive extremes<=100/3 versus>=200/3, middle excluded with exactcoverage, prediction threshold50, accuracy/low-high recalls/balancedaccuracy/AUC. No threshold tuning. Report all tasks and active-only without refitting.',
        'bootstrap': '10000 paired whole-person resamples for MAE improvement selected versus each comparator. Exploratory percentile95 intervals; model training sets overlap and prior development reuse remains.',
        'deployment': 'Anonymous academic research only; production_enabled false; no named employee, app or dashboard integration and no changes to earlier workplace-output exclusions.',
        'stop': 'Complete one frozen nested comparison and independent saved-artifact verification. Do not alter candidates, folds, target, threshold or features based on outer outcomes.',
        'references': ['https://www.nasa.gov/human-systems-integration-division/nasa-task-load-index-tlx/',
                       'https://www.nature.com/articles/s41597-024-03738-7']}
    write_json(root/PROTOCOL, protocol)
    destination.mkdir(parents=True, exist_ok=True);out.mkdir(parents=True, exist_ok=True)
    path = destination/'tasks.csv.gz';data.to_csv(path, index=False, compression={'method': 'gzip', 'mtime': 0})
    audit = {'people': int(data.participant.nunique()), 'tasks': len(data), 'windows': int(data.source_windows.sum()),
        'active_tasks': int(data.active.sum()), 'labels': label_audit, 'coverage': dict(coverage),
        'minimum_target': float(data.target.min()), 'maximum_target': float(data.target.max()),
        'extreme_low_tasks': int((data.target <= 100/3).sum()), 'extreme_high_tasks': int((data.target >= 200/3).sum()),
        'middle_tasks': int(((data.target > 100/3)&(data.target < 200/3)).sum()),
        'features_available': data[feature_columns('reference')].notna().mean().to_dict(),
        'source_labels_sha256': sources, 'table_sha256': sha(path), 'protocol_sha256': sha(root/PROTOCOL),
        'base_features_sha256': sha(basepath), 'native_features_sha256': sha(nativepath),
        'native_alignment_audit_sha256': sha(nativepath.with_name('universe-native-audit.json')),
        'preserved_files': protected_hashes(root), 'original_test_excluded': split['test'],
        'Lab2_and_Mobile_evaluation_used': False}
    write_json(destination/'audit.json', audit)
    print(json.dumps({k: audit[k] for k in ['people', 'tasks', 'windows', 'active_tasks', 'extreme_low_tasks', 'extreme_high_tasks', 'middle_tasks']}), flush=True)


def observation_weights(frame):
    values = 1/frame.groupby('participant').participant.transform('size').to_numpy(float)
    return values/values.mean()


def weighted_median(values, weights):
    order = np.argsort(values, kind='stable');x = np.asarray(values)[order];w = np.asarray(weights)[order]
    return float(x[np.searchsorted(np.cumsum(w), w.sum()/2, side='left')])


def model_for(name):
    if name.startswith('ridge'):
        model = Ridge(alpha=float(name[5:]))
    elif name.startswith('svr'):
        model = SVR(C=float(name[3:]), epsilon=5., gamma='scale')
    elif name == 'extra':
        model = ExtraTreesRegressor(n_estimators=250, max_depth=6, min_samples_leaf=3, max_features=.8, random_state=SEED, n_jobs=1)
    elif name == 'cat3':
        from catboost import CatBoostRegressor
        model = CatBoostRegressor(iterations=300, depth=3, learning_rate=.035, l2_leaf_reg=20,
                loss_function='MAE', random_seed=SEED, thread_count=1, verbose=False, allow_writing_files=False)
    else:
        raise ValueError(name)
    return make_pipeline(SimpleImputer(strategy='median', add_indicator=True, keep_empty_features=True),
                         RobustScaler(quantile_range=(10, 90)), FunctionTransformer(np.tanh, feature_names_out='one-to-one'), model)


def fit(frame, config):
    if set(frame.session) != {'Lab1'} or frame.target.isna().any() or not frame.target.between(0, 100).all():
        raise ValueError('Only observed valid Lab1 workload scores may fit models')
    if frame.unit_id.duplicated().any():
        raise ValueError('A task cannot be duplicated in fitting')
    artifact = {'config': config, 'training_people': sorted(frame.participant.unique()),
                'training_units': sorted(frame.unit_id.unique()), 'training_session': 'Lab1',
                'production_enabled': False, 'target': 'recorded_weighted_nasa_tlx', 'score_is_calibrated_confidence': False}
    if config['algorithm'] == 'constant':
        artifact.update(columns=[], constant=weighted_median(frame.target, observation_weights(frame)))
        return artifact
    cols = feature_columns(config['profile']);artifact['columns'] = cols
    model = model_for(config['algorithm'])
    with threadpool_limits(limits=1), warnings.catch_warnings():
        warnings.simplefilter('ignore', category=RuntimeWarning)
        model.fit(frame[cols], frame.target, **{model.steps[-1][0]+'__sample_weight': observation_weights(frame)})
    artifact['model'] = model
    return artifact


def predict(artifact, frame):
    if 'members' in artifact:
        return np.mean([predict(member, frame) for member in artifact['members']], axis=0)
    if 'constant' in artifact:
        return np.full(len(frame), artifact['constant'], float)
    return np.clip(artifact['model'].predict(frame[artifact['columns']]), 0, 100)


def person_mae(frame, scores):
    return float(frame.assign(error=np.abs(frame.target.to_numpy()-np.asarray(scores))).groupby('participant').error.mean().mean())


def nested_job(root_string, specification):
    root = Path(root_string);fold = specification['fold'];out = root/OUT
    data = pd.read_csv(root/DATA/'tasks.csv.gz')
    training = data[data.participant.isin(specification['training_people'])].reset_index(drop=True)
    evaluation = data[data.participant.isin(specification['evaluation_people'])].reset_index(drop=True)
    assert not set(training.participant)&set(evaluation.participant)
    assert not set(training.unit_id)&set(evaluation.unit_id)
    oof = np.full((len(training), len(CONFIGS)), np.nan)
    split_records = []
    for inner, held in enumerate(specification['inner_folds']):
        fit_rows = training[~training.participant.isin(held)];valid = training[training.participant.isin(held)]
        assert not set(fit_rows.participant)&set(valid.participant)
        split_records.append({'inner': inner, 'training_people': sorted(fit_rows.participant.unique()),
                              'validation_people': sorted(valid.participant.unique()),
                              'training_units': sorted(fit_rows.unit_id), 'validation_units': sorted(valid.unit_id)})
        for i, config in enumerate(CONFIGS):
            oof[valid.index, i] = predict(fit(fit_rows, config), valid)
    assert np.isfinite(oof).all()
    candidates = [{'id': f'base{i}', 'members': [i], 'config': config, 'inner_mae': person_mae(training, oof[:, i])}
                  for i, config in enumerate(CONFIGS)]
    rank = sorted(range(len(CONFIGS)), key=lambda i: candidates[i]['inner_mae'])
    for profile in ['all', *PROFILES]:
        indices = [i for i in rank if profile == 'all' or CONFIGS[i]['profile'] == profile][:3]
        score = oof[:, indices].mean(axis=1)
        candidates.append({'id': 'ensemble_'+profile, 'members': indices,
                           'config': {'profile': profile, 'algorithm': 'top3_mean'}, 'inner_mae': person_mae(training, score)})
    chosen = min(candidates, key=lambda row: row['inner_mae'])
    selection = {'fold': fold, 'selected': chosen, 'candidates': candidates, 'inner_folds': split_records,
                 'training_people': specification['training_people'], 'evaluation_people': specification['evaluation_people']}
    selection_path = out/'folds'/f'{fold}-selection.json';write_json(selection_path, selection)
    # Candidate predictions are saved before this outer fold's held people are scored.
    oof_frame = training[['row_id', 'participant', 'unit_id', 'target']].copy()
    for i in range(len(CONFIGS)):
        oof_frame[f'base{i}'] = oof[:, i]
    oofpath = out/'folds'/f'{fold}-inner-predictions.csv.gz'
    oof_frame.to_csv(oofpath, index=False, compression={'method': 'gzip', 'mtime': 0})
    selected = {'members': [fit(training, CONFIGS[i]) for i in chosen['members']],
                'config': chosen['config'], 'training_people': sorted(training.participant.unique()),
                'training_units': sorted(training.unit_id), 'training_session': 'Lab1',
                'production_enabled': False, 'target': 'recorded_weighted_nasa_tlx'}
    models = {'constant': fit(training, {'profile': 'legacy', 'algorithm': 'constant'}),
              'fixed_prior': fit(training, {'profile': 'legacy', 'algorithm': 'ridge100'}), 'selected': selected}
    predictions = evaluation[['row_id', 'participant', 'session', 'unit_id', 'target', 'active', 'source_windows']].copy()
    predictions['fold'] = fold;artifacts = []
    for arm, artifact in models.items():
        path = root/'models/workload-improvement-v1'/f'fold{fold}-{arm}.joblib'
        path.parent.mkdir(parents=True, exist_ok=True);joblib.dump(artifact, path)
        artifacts.append({'arm': arm, 'file': str(path.relative_to(root)), 'sha256': sha(path)})
        predictions[arm] = predict(artifact, evaluation)
    path = out/'folds'/f'{fold}-predictions.csv.gz'
    predictions.to_csv(path, index=False, compression={'method': 'gzip', 'mtime': 0})
    return {'fold': fold, 'selection': str(selection_path.relative_to(root)), 'selection_sha256': sha(selection_path),
            'inner_predictions': str(oofpath.relative_to(root)), 'inner_predictions_sha256': sha(oofpath),
            'predictions': str(path.relative_to(root)), 'predictions_sha256': sha(path), 'artifacts': artifacts}


def run(root):
    root = Path(root);out = root/OUT;out.mkdir(parents=True, exist_ok=True)
    if (out/'evaluation.json').exists() or (out/'run-freeze.json').exists():
        raise ValueError('Experiment already started; preserve its frozen evidence')
    audit = json.loads((root/DATA/'audit.json').read_text());protocol = json.loads((root/PROTOCOL).read_text())
    assert sha(root/DATA/'tasks.csv.gz') == audit['table_sha256']
    assert sha(root/PROTOCOL) == audit['protocol_sha256']
    for path, digest in audit['preserved_files'].items():
        assert sha(root/path) == digest
    freeze = {'started_utc': datetime.now(timezone.utc).isoformat(), 'protocol_sha256': sha(root/PROTOCOL),
              'audit_sha256': sha(root/DATA/'audit.json'), 'data_sha256': sha(root/DATA/'tasks.csv.gz'),
              'code_sha256': sha(Path(__file__)), 'folds': protocol['folds'], 'candidates': CONFIGS,
              'preserved_files': audit['preserved_files']}
    write_json(out/'run-freeze.json', freeze)
    jobs = []
    with ProcessPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(nested_job, str(root), spec) for spec in protocol['folds']]
        for future in as_completed(futures):
            record = future.result();jobs.append(record)
            print(json.dumps({'outer_folds_complete': len(jobs), 'of': 4, 'fold': record['fold']}), flush=True)
    write_json(out/'evaluation.json', {'run_sha256': sha(out/'run-freeze.json'), 'jobs': sorted(jobs, key=lambda x: x['fold'])})


def load_predictions(root):
    root = Path(root);evaluation = json.loads((root/OUT/'evaluation.json').read_text())
    parts = []
    for job in evaluation['jobs']:
        assert sha(root/job['predictions']) == job['predictions_sha256']
        parts.append(pd.read_csv(root/job['predictions']))
    result = pd.concat(parts, ignore_index=True).sort_values('row_id').reset_index(drop=True)
    assert not result.row_id.duplicated().any()
    return result
