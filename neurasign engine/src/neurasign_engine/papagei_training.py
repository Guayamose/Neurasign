"""Bounded development comparisons. Never load held-out sensor or label rows."""
from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
import json
from pathlib import Path
import warnings

import joblib
import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

from .schema import SEED, TARGETS
from .transfer_features import FEATURES
from .transfer_training import (fit_predict, fit_weights, grouped_folds, make_model,
                                metrics, sha, thin, write_json)

ENGINEERED = FEATURES + [f+'__delta' for f in FEATURES]
PROFILES = ['ppg60', 'fused60', 'fused180', 'engineered']
ALGORITHMS = ['ridge100', 'ridge1000', 'cat4']
PREVIOUS = {
    'mental_effort': {'profile': 'ppg_eda', 'algorithm': 'boost_absolute'},
    'mental_demand': {'profile': 'summary_history', 'algorithm': 'cat4'},
    'physical_demand': {'profile': 'native', 'algorithm': 'boost_absolute'},
    'temporal_demand': {'profile': 'all_history', 'algorithm': 'ridge100'},
    'perceived_performance': {'profile': 'all_history', 'algorithm': 'ridge1000'},
    'effort': {'profile': 'all_history', 'algorithm': 'boost_absolute'},
}


def design(frame, embeddings, fitting, profile, algorithm, transformers=None):
    """Fit coordinate projections on training indices, transform all rows without refitting."""
    blocks = []
    learned = {} if transformers is None else transformers
    if profile != 'engineered':
        for b in range(3 if profile == 'fused180' else 1):
            values = embeddings[:, b, :]
            if algorithm.startswith('cat'):
                if transformers is None:
                    learned[b] = make_pipeline(StandardScaler(), PCA(32, svd_solver='randomized', random_state=SEED))
                    learned[b].fit(values[fitting])
                values = learned[b].transform(values)
            blocks.append(values)
    if profile != 'ppg60':
        assert not set(ENGINEERED) & (set(TARGETS) | {'participant', 'unit_id', 'source_end', 'session'})
        blocks.append(frame[ENGINEERED].to_numpy(np.float32))
    return np.concatenate(blocks, axis=1), learned


def load_inputs(root):
    data = root/'data/prepared/papagei-v1'
    audit = json.loads((data/'audit.json').read_text())
    assert sha(data/'windows.csv.gz') == audit['windows_sha256']
    assert sha(data/'embeddings.npy') == audit['embeddings_sha256']
    frame = pd.read_csv(data/'windows.csv.gz')
    embeddings = np.load(data/'embeddings.npy', mmap_mode='r', allow_pickle=False)
    assert embeddings.shape == (len(frame), 3, 512) and np.isfinite(embeddings).all()
    split = json.loads((root/'experiments/split-v1.json').read_text())
    assert set(frame.participant) <= set(split['development'])
    assert not set(frame.participant) & set(split['test'])
    native = pd.read_csv(root/'data/prepared/transfer-v1/universe-native.csv.gz')
    for column in native.columns:
        frame[column] = native.iloc[frame.original_row.to_numpy()][column].to_numpy()
    return frame, embeddings


def fit_one(frame, embeddings, training, valid, target, profile, algorithm):
    fitting = thin(training)
    x, projections = design(frame, embeddings, fitting.index.to_numpy(), profile, algorithm)
    model = make_model(algorithm)
    low, high = TARGETS[target]['range']
    key = model.steps[-1][0]+'__sample_weight' if hasattr(model, 'steps') else 'sample_weight'
    model.fit(x[fitting.index], (fitting[target]-low)/(high-low), **{key: fit_weights(fitting)})
    pred = np.clip(model.predict(x[valid.index]), 0, 1)*(high-low)+low
    return pred, {'model': model, 'projections': projections, 'profile': profile,
                  'algorithm': algorithm, 'target': target, 'range': [low, high],
                  'production_enabled': False, 'training_people': sorted(training.participant.unique())}


def evaluate_job(root_string, target, profile, algorithm, folds):
    root = Path(root_string)
    frame, embeddings = load_inputs(root)
    selected = frame[frame[target].notna()]
    rows = []
    with threadpool_limits(limits=1), warnings.catch_warnings():
        warnings.simplefilter('ignore', category=RuntimeWarning)
        for fold, ids in enumerate(folds):
            training = selected[~selected.participant.isin(ids)]
            valid = selected[selected.participant.isin(ids)]
            if profile == 'previous':
                pred = fit_predict(training, valid, target, PREVIOUS[target])
            else:
                pred, _ = fit_one(frame, embeddings, training, valid, target, profile, algorithm)
            result = valid[['participant', 'session', 'unit_id', 'source_end', 'original_row', target]].copy()
            result['prediction'] = pred
            result['fold'] = fold
            rows.append(result)
    predictions = pd.concat(rows).sort_values('original_row').reset_index(drop=True)
    name = profile+'__'+algorithm
    path = root/'results/papagei-v1'/(target+'__'+name+'.csv.gz')
    predictions.to_csv(path, index=False, compression={'method': 'gzip', 'mtime': 0})
    result = {'target': target, 'profile': profile, 'algorithm': algorithm, 'name': name,
              'metrics': metrics(predictions, target, predictions.prediction), 'predictions_sha256': sha(path)}
    write_json(path.with_name(target+'__'+name+'.metrics.json'), result)
    return result


def train(root):
    frame, _ = load_inputs(root)
    out = root/'results/papagei-v1'
    out.mkdir(parents=True, exist_ok=True)
    folds = grouped_folds(frame)
    original_folds = json.loads((root/'results/transfer-v1/universe/protocol.json').read_text())['folds']
    assert folds == original_folds
    configs = [(p, a) for p in PROFILES for a in ALGORITHMS]
    configs += [('engineered', 'constant_mean'), ('engineered', 'constant_median'), ('previous', 'frozen008')]
    document = {'started_utc': datetime.now(timezone.utc).isoformat(), 'folds': folds,
                'configurations_per_target': len(configs), 'targets': list(TARGETS),
                'protocol_sha256': sha(root/'experiments/009-papagei-protocol.json'),
                'training_code_sha256': sha(Path(__file__)),
                'input_audit_sha256': sha(root/'data/prepared/papagei-v1/audit.json'),
                'previous_configurations': PREVIOUS,
                'previous_final_selection_sha256': sha(root/'experiments/008-final-selection.json'),
                'previous_test_report_sha256': sha(root/'results/transfer-v1/final/test-report.json')}
    protocol_path = out/'run.json'
    if protocol_path.exists():
        previous = json.loads(protocol_path.read_text())
        assert {k: v for k, v in previous.items() if k != 'started_utc'} == {k: v for k, v in document.items() if k != 'started_utc'}
    else:
        write_json(protocol_path, document)
    jobs = [(t, p, a) for t in TARGETS for p, a in configs]
    completed = []
    with ProcessPoolExecutor(max_workers=6) as pool:
        pending = {}
        for t, p, a in jobs:
            path = out/(t+'__'+p+'__'+a+'.metrics.json')
            if path.exists():
                completed.append(json.loads(path.read_text()))
            else:
                pending[pool.submit(evaluate_job, str(root), t, p, a, folds)] = (t, p, a)
        for future in as_completed(pending):
            result = future.result()
            completed.append(result)
            print(json.dumps({'completed': len(completed), 'of': len(jobs), 'target': result['target'],
                              'model': result['name'], 'mae': result['metrics']['mae']}), flush=True)
    write_json(out/'report.json', {'run': json.loads(protocol_path.read_text()), 'results': completed})
    pd.DataFrame([{'target': r['target'], 'name': r['name'], 'profile': r['profile'],
                  'algorithm': r['algorithm'], **{k: v for k, v in r['metrics'].items() if not isinstance(v, (dict, list))}}
                  for r in completed]).to_csv(out/'comparison.csv', index=False)


def paired_interval(candidate, baseline):
    people = sorted(candidate['per_person_mae'])
    assert people == sorted(baseline['per_person_mae'])
    delta = np.array([baseline['per_person_mae'][p]-candidate['per_person_mae'][p] for p in people])
    samples = np.random.default_rng(SEED).choice(delta, (10000, len(delta)), replace=True).mean(axis=1)
    return {'mae_reduction_points': float(delta.mean()), 'percentile_95_ci': np.quantile(samples, [.025, .975]).tolist(),
            'people_improved': int((delta > 0).sum()), 'people': len(people),
            'meaning': 'Descriptive development interval; no correction for model selection or multiple comparisons.'}


def report(root):
    out = root/'results/papagei-v1'
    results = json.loads((out/'report.json').read_text())['results']
    audit = json.loads((root/'data/prepared/papagei-v1/audit.json').read_text())
    selected = {}
    for target in TARGETS:
        rows = [r for r in results if r['target'] == target]
        choose = lambda rs: min(rs, key=lambda r: r['metrics']['mae'])
        papagei = choose([r for r in rows if r['profile'] in ('ppg60', 'fused60', 'fused180')])
        engineered = choose([r for r in rows if r['profile'] in ('engineered', 'previous') and not r['algorithm'].startswith('constant')])
        constant = choose([r for r in rows if r['algorithm'].startswith('constant')])
        selected[target] = {'papagei': papagei, 'engineered': engineered, 'constant': constant,
                            'vs_constant': paired_interval(papagei['metrics'], constant['metrics']),
                            'vs_engineered': paired_interval(papagei['metrics'], engineered['metrics'])}
    write_json(out/'selection.json', selected)
    lines = ['# Experiment 009: raw pulse transfer with PaPaGei-S', '',
        '**Development experiment only. No new independent test and no product integration.**', '',
        f"The frozen encoder processed {audit['chunks']:,} distinct completed 10-second chunks; {audit['valid_chunks']:,} passed availability checks. "
        f"The matched comparison includes {audit['accepted_windows']:,}/{audit['original_windows']:,} original endpoints "
        f"({audit['coverage']:.1%}), {audit['tasks']} tasks and {audit['people']} development participants. "
        'Every profile requires the same three-minute warm-up and signal coverage, including the one-minute profiles and baselines.', '',
        '## Results', '',
        'Lower mean absolute error (MAE) is better. Each person and task has equal weight. '
        'The selected PaPaGei configuration is chosen by development MAE, not by the agreement column. '
        'Agreement is exact 1–5 category agreement for mental effort and within ±10 points for the five 0–100 ratings.', '',
        '| Questionnaire target | Constant MAE | Engineered MAE | PaPaGei MAE | PaPaGei agreement | Constant agreement | Best PaPaGei |',
        '|---|---:|---:|---:|---:|---:|---|']
    for target, values in selected.items():
        p, e, c = [values[k] for k in ('papagei', 'engineered', 'constant')]
        key = 'exact_or_three_level_accuracy' if target == 'mental_effort' else 'within_tolerance'
        lines.append(f"| {target} | {c['metrics']['mae']:.3f} | {e['metrics']['mae']:.3f} | {p['metrics']['mae']:.3f} | {p['metrics'][key]:.1%} | {c['metrics'][key]:.1%} | {p['name']} |")
    lines += ['', 'The engineered comparator is the better of the newly matched engineered candidates and the prior experiment 008 winner retrained on exactly the same eligible population. '
              'Constants are fitted independently inside each fold. Their mean/median variant is selected on development MAE. '
              'These are development selection results, so neither the selected scores nor their intervals establish generalization.', '',
              '| Target | MAE improvement over constant (95% descriptive interval) | MAE improvement over engineered (95% descriptive interval) |',
              '|---|---:|---:|']
    for target, values in selected.items():
        cells = []
        for k in ('vs_constant', 'vs_engineered'):
            s = values[k];lo, hi = s['percentile_95_ci']
            cells.append(f"{s['mae_reduction_points']:.3f} [{lo:.3f}, {hi:.3f}]")
        lines.append('| '+target+' | '+' | '.join(cells)+' |')
    lines += ['', 'Positive improvement means lower PaPaGei error. Intervals resample the 19 people, not overlapping windows. '
              'They are descriptive, do not correct for selecting the best candidate and are not an independent validation claim.', '',
              '## Method and boundaries', '',
              '- PaPaGei-S is frozen: a 512-coordinate embedding per completed 10-second raw BVP chunk, output index 0. No UNIVERSE target is used to update the encoder.',
              '- Inputs follow the authors\' training normalization order: filter at 64 Hz, z-score each chunk, resample to 125 Hz. The band-pass uses only the chunk and up to 10 seconds of past padding; the full task is never filtered in advance. A zero-phase filter over a completed past chunk is endpoint-causal.',
              '- Profiles compare the last minute, fusion with EDA/temperature/movement/HR and past-reference deltas, and three-minute embedding means plus recent-versus-earlier differences. This is temporal aggregation, not a recurrent network or end-to-end fine-tuning.',
              '- Ridge (alpha 100 and 1000) and CatBoost (depth 4) are trained in five participant-disjoint folds. CatBoost receives 32 PCA coordinates per embedding block; PCA, scaling and imputation are fitted on training participants only. Maximum 20 training windows per task; all eligible validation windows are scored.',
              '- 90 target/configuration comparisons, 450 supervised fold fits: 54 with PaPaGei, 18 matched engineered controls, 12 constants and six retrained prior winners. All six questionnaire targets remain separate.',
              '- No EEG, task name, person identity, questionnaire field, future physiology or held-out participant enters predictors. Original UNIVERSE and Mobile tests remain closed. Mobile has no raw PPG for this route.',
              '- Questionnaire ratings apply to an entire task. Repeating them across windows does not create instantaneous ground truth. History resets at labeled recording boundaries; this comparison does not establish continuous, boundary-free deployment performance.',
              '- Availability checks reject gaps, nonfinite values and flat chunks; they do not establish freedom from motion artifacts. The three-minute warm-up and coverage restriction reduce the scored population.',
              '- Raw PPG access is required. Supporting a wearable\'s HR API alone does not make it compatible with this encoder. Physical demand is not fatigue, and perceived performance is a self-rating, not measured productivity.', '',
              '## Reproduce', '', 'From `neurasign engine/`:', '', '```bash',
              '.venv/bin/python scripts/download_papagei.py',
              'OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python scripts/run_papagei.py extract',
              'OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python scripts/run_papagei.py train',
              '.venv/bin/python scripts/run_papagei.py report',
              '.venv/bin/python scripts/run_papagei.py verify', '```', '',
              'The complete candidate table, per-window out-of-fold predictions, selected research models, source checksums and audit are stored in ignored `results/papagei-v1/`, `models/papagei-v1/` and `data/prepared/papagei-v1/`. '
              'The [protocol](009-papagei-protocol.json) was written before supervised PaPaGei outcomes. '
              'The experiment does not exhaust end-to-end fine-tuning, larger temporal models or other foundation models.', '',
              '## Sources', '',
              '- [Official PaPaGei repository](https://github.com/Nokia-Bell-Labs/papagei-foundation-model/tree/0c537dad4d2850e15b724260de820dd68d77f0b0), pinned architecture and normalization code.',
              '- [Official pretrained weights](https://zenodo.org/records/13983110), published MD5 verified, safe tensor-only loading. Authors list VitalDB, MIMIC-III and MESA as training sources; no UNIVERSE overlap is reported. This is not a workload-specific pretraining claim.',
              '- [PaPaGei paper](https://arxiv.org/abs/2410.20542). Published model results are not NEURASIGN accuracy.', '',
              'The source file labels its license BSD-3-Clause-Clear while the repository LICENSE is BSD 3-Clause. Both original notices are retained in the vendored architecture and license file. No research artifact is integrated into the product.', '']
    (root/'experiments/009-papagei-results.md').write_text('\n'.join(lines))
    # Export selected research-only heads, without evaluating any closed test.
    frame, embeddings = load_inputs(root)
    model_dir = root/'models/papagei-v1';model_dir.mkdir(parents=True, exist_ok=True)
    with threadpool_limits(limits=1):
        for target, values in selected.items():
            c = values['papagei'];training = frame[frame[target].notna()]
            _, artifact = fit_one(frame, embeddings, training, training.iloc[:1], target, c['profile'], c['algorithm'])
            artifact['encoder_sha256'] = audit['fingerprint']['weights']
            artifact['input_audit_sha256'] = sha(root/'data/prepared/papagei-v1/audit.json')
            artifact['validation_status'] = 'development_selection_only'
            joblib.dump(artifact, model_dir/(target+'.joblib'))
    print(pd.DataFrame([{'target': t, 'constant': v['constant']['metrics']['mae'],
                        'engineered': v['engineered']['metrics']['mae'], 'papagei': v['papagei']['metrics']['mae']}
                       for t, v in selected.items()]).to_string(index=False), flush=True)


def verify(root):
    out = root/'results/papagei-v1'
    document = json.loads((out/'report.json').read_text())
    run = document['run']
    assert sha(Path(__file__)) == run['training_code_sha256']
    assert sha(root/'experiments/008-final-selection.json') == run['previous_final_selection_sha256']
    assert sha(root/'results/transfer-v1/final/test-report.json') == run['previous_test_report_sha256']
    frame, embeddings = load_inputs(root)
    count = 0
    for result in document['results']:
        t = result['target'];path = out/(t+'__'+result['name']+'.csv.gz')
        assert sha(path) == result['predictions_sha256']
        pred = pd.read_csv(path)
        assert not pred.original_row.duplicated().any()
        expected = frame.loc[frame[t].notna()].sort_values('original_row')
        assert pred.original_row.tolist() == expected.original_row.tolist()
        np.testing.assert_allclose(pred[t], expected[t], rtol=0, atol=0)
        for fold, ids in enumerate(run['folds']):
            assert set(pred.loc[pred.fold == fold, 'participant']) == set(ids)
        # Independent calculations, not calls back to the training metric helper.
        pred['error'] = abs(pred[t]-pred.prediction)
        person_mae = pred.groupby(['participant', 'unit_id']).error.mean().groupby('participant').mean()
        np.testing.assert_allclose(person_mae.mean(), result['metrics']['mae'], rtol=1e-10)
        tol = 1 if t == 'mental_effort' else 10
        pred['agreement'] = pred.error <= tol
        agreement = pred.groupby(['participant', 'unit_id']).agreement.mean().groupby('participant').mean().mean()
        np.testing.assert_allclose(agreement, result['metrics']['within_tolerance'], rtol=1e-10)
        if t == 'mental_effort':
            pred['exact'] = np.floor(pred.prediction+.5) == pred[t]
        else:
            pred['exact'] = np.minimum((pred.prediction/(100/3)).astype(int), 2) == np.minimum((pred[t]/(100/3)).astype(int), 2)
        exact = pred.groupby(['participant', 'unit_id']).exact.mean().groupby('participant').mean().mean()
        np.testing.assert_allclose(exact, result['metrics']['exact_or_three_level_accuracy'], rtol=1e-10)
        count += 3
    assert len(document['results']) == 90
    artifacts = []
    with threadpool_limits(limits=1):
        for target in TARGETS:
            path = root/'models/papagei-v1'/(target+'.joblib')
            artifact = joblib.load(path)  # Locally generated, never downloaded pickle.
            assert artifact['production_enabled'] is False
            x, _ = design(frame.iloc[:5], embeddings[:5], [], artifact['profile'], artifact['algorithm'], artifact['projections'])
            assert np.isfinite(artifact['model'].predict(x)).all()
            artifacts.append({'target': target, 'sha256': sha(path)})
    write_json(out/'verification.json', {'status': 'passed', 'comparisons': 90, 'independent_metrics': count,
                                       'old_test_report_unchanged': True, 'artifact_checks': artifacts})
    print('Verified 90 comparisons, 270 independent metrics and six research artifacts.', flush=True)
