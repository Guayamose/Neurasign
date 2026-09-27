"""Frozen, nested development-only DailySense fatigue improvement experiment.

No historical reserved person is evaluated here. Raw signals and original daily
labels retain the timing, integrity and coverage rules of experiment 018.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from catboost import CatBoostClassifier, CatBoostRegressor
from sklearn.ensemble import ExtraTreesClassifier, ExtraTreesRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import RobustScaler, StandardScaler
from sklearn.svm import SVC, SVR
from threadpoolctl import threadpool_limits

SEED = 20260927
NAME = 'fatigue-nested-v1'
PROTOCOL = 'experiments/020-fatigue-nested-protocol.json'
DATA = 'data/prepared/fatigue-nested-v1/development.csv.gz'
KINDS = ('classification', 'regression')
ALGORITHMS = ('linear_strong', 'linear_moderate', 'rbf_regularized',
              'rbf_flexible', 'extra_regularized', 'cat_regularized')
SIGNALS = ('hr_mean', 'hr_std', 'eda_mean', 'eda_std', 'temperature_mean',
           'temperature_std', 'ibi_mean_ms', 'ibi_sdnn_ms', 'ibi_rmssd_ms')
LOG_SIGNALS = {'eda_mean', 'eda_std', 'ibi_sdnn_ms', 'ibi_rmssd_ms'}
THRESHOLDS = np.round(np.arange(.25, .7501, .025), 3)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False)+'\n')


def features(frame, cardiac):
    """Deterministic per-row features: no labels, fitted statistics or cross rows."""
    values = {c: frame[c].to_numpy(float) for c in cardiac}
    core, change = [], []
    for signal in SIGNALS:
        for stat in ('mean', 'std', 'p50', 'iq80'):
            prefix = 'day__'+signal+'__'
            raw = (frame[prefix+'p90']-frame[prefix+'p10'] if stat == 'iq80'
                   else frame[prefix+stat]).to_numpy(float)
            value = np.log1p(np.maximum(raw, 0)) if signal in LOG_SIGNALS else raw
            key = 'robust__'+signal+'__'+stat
            values[key] = value
            core.append(key)
        for stat in ('mean', 'p50', 'std'):
            day = frame[f'day__{signal}__{stat}'].to_numpy(float)
            recent = frame[f'last60__{signal}__{stat}'].to_numpy(float)
            past_delta = frame[f'day__{signal}__{stat}__past7_delta'].to_numpy(float)
            past = day-past_delta
            for context, other in [('recent', recent), ('history', past)]:
                # EDA and variability differ greatly between people. Log1p
                # differences give bounded influence without population fitting.
                if signal in LOG_SIGNALS:
                    delta = np.log1p(np.maximum(day, 0))-np.log1p(np.maximum(other, 0))
                elif signal in ('hr_mean', 'ibi_mean_ms') and stat != 'std':
                    delta = (day-other)/np.maximum(np.abs(other), 1.)
                else:
                    delta = day-other
                key = f'change__{signal}__{stat}__{context}'
                values[key] = delta
                change.append(key)
    for numerator in ('ibi_sdnn_ms', 'ibi_rmssd_ms'):
        key = 'robust__'+numerator+'__relative_ibi'
        values[key] = frame[f'day__{numerator}__p50'].to_numpy(float)/np.maximum(
            frame['day__ibi_mean_ms__p50'].to_numpy(float), 1.)
        core.append(key)
    result = pd.DataFrame(values, index=frame.index).replace([np.inf, -np.inf], np.nan)
    profiles = {'cardiac_day': list(cardiac), 'robust_core': core,
                'physiological_change': core+change}
    return result, profiles


def grouped_folds(frame, n):
    result = []
    for train, valid in GroupKFold(n_splits=n).split(frame, groups=frame.participant):
        training = sorted(frame.iloc[train].participant.unique().tolist())
        validation = sorted(frame.iloc[valid].participant.unique().tolist())
        assert set(training).isdisjoint(validation)
        result.append({'training_people': training, 'validation_people': validation})
    return result


def prepare(root):
    root = Path(root)
    path = root/PROTOCOL
    if path.exists():
        raise ValueError('Protocol already frozen; do not replace it')
    old_path = root/'experiments/018-dailysense-classification-protocol.json'
    old = json.loads(old_path.read_text())
    original = pd.read_csv(root/'data/prepared/dailysense-v1/answers.csv.gz')
    # Filter before any feature statistics, folds, fitting or scoring.
    frame = original[original.participant.isin(old['split']['development'])].copy()
    frame = frame.sort_values(['participant', 'row_id']).reset_index(drop=True)
    assert len(frame) == 357 and frame.participant.nunique() == 28
    assert not set(frame.participant).intersection(old['split']['test'])
    transformed, profiles = features(frame, old['profiles']['cardiac_day'])
    meta = frame[['row_id', 'participant', 'unit_id', 'date', 'rating']].copy()
    data = pd.concat([meta, transformed], axis=1)
    (root/DATA).parent.mkdir(parents=True, exist_ok=True)
    data.to_csv(root/DATA, index=False, compression={'method': 'gzip', 'mtime': 0})
    folds = grouped_folds(data, 4)
    for fold in folds:
        training = data[data.participant.isin(fold['training_people'])]
        fold['inner_folds'] = grouped_folds(training, 3)
    candidates = [{'key': profile+':'+algorithm, 'profile': profile, 'algorithm': algorithm}
                  for profile in profiles for algorithm in ALGORITHMS]
    source_files = ['src/neurasign_engine/fatigue_nested.py',
                    'src/neurasign_engine/fatigue_nested_verify.py',
                    'scripts/run_fatigue_nested.py', 'tests/test_fatigue_nested.py']
    frozen = ['experiments/018-dailysense-classification-protocol.json',
              'experiments/018-dailysense-regression-protocol.json',
              'src/neurasign_engine/dailysense_data.py',
              'src/neurasign_engine/reference_benchmark.py']
    protocol = {
        'experiment': 20, 'name': NAME, 'seed': SEED,
        'evidence': 'Exploratory nested development evidence; not fresh held-out validation. Historical test people never enter this experiment.',
        'source': 'https://zenodo.org/records/10816004',
        'target_classification': 'Observed daily fatigue VAS >=50 versus <50; research midpoint, no excluded middle ratings.',
        'target_regression': 'Observed daily fatigue VAS in original 0–100 units.',
        'people': old['split']['development'], 'historical_test_people_excluded': old['split']['test'],
        'rows': len(data), 'outer_folds': folds, 'final_inner_folds': grouped_folds(data, 3),
        'profiles': profiles, 'candidates': candidates,
        'candidate_budget': '18 candidates per target, 36 total; a fixed reference per target and one deterministic top-three ensemble per selection.',
        'arms': ['training_constant', 'fixed_cardiac_extra5', 'inner_selected'],
        'reference': 'Exact experiment018 cardiac ExtraTrees settings: 250 trees, leaf=5, max_features=.8, seed20260926; threshold .5.',
        'selection': 'Three grouped inner folds. Rank by person-weighted balanced accuracy after inner-only threshold search, or MAE. Compare best single with top three distinct algorithm families averaged. Tie prefers single. Freeze before outer fitting/prediction.',
        'thresholds': THRESHOLDS.tolist(),
        'threshold_tie': 'Maximum balanced accuracy, then maximum worse-class recall, then nearest .5, then lower threshold.',
        'preprocessing': 'Fold-trained median imputation and missingness indicators. RobustScaler for improved candidates; StandardScaler for unchanged fixed reference. Class-balanced person weights for classifiers; equal total person weight for regressors.',
        'algorithm_settings': {
            'linear_strong': 'Logistic C=.03 or Ridge alpha=100',
            'linear_moderate': 'Logistic C=.3 or Ridge alpha=10',
            'rbf_regularized': 'RBF SVC C=.3 or SVR C=10 epsilon=5',
            'rbf_flexible': 'RBF SVC C=3 or SVR C=50 epsilon=5',
            'extra_regularized': '500 ExtraTrees, max_depth=5, min_leaf=8, max_features=.5',
            'cat_regularized': '350 CatBoost iterations, depth=3, learning_rate=.035, l2=15, random_strength=2'},
        'feature_rationale': 'Remove severely damaged BVP from new compact profiles; log positive EDA/HRV distributions, native HRV/IBI ratios, recent-hour versus day differences and strictly preceding seven-day physiological baseline differences. Original cardiac profile retained as a comparison. No psychological answers, identity or calendar values enter predictors.',
        'timing': old['cutoff'], 'source_integrity': old['cohort'],
        'coverage': 'All 357 development daily labels retained; no outcome-based abstention.',
        'uncertainty': '1000 seeded paired participant bootstrap draws; this describes limited development cohort variation, not external validation.',
        'classification_gate': 'Exploratory only: BA >=.8 and both recalls >=.7.',
        'regression_gate': 'Exploratory only: MAE <=8, >=20% improvement over constant, R2 >=.25.',
        'no_old_test_comparison': 'Nested outer folds use different people than the old test; their scores cannot be treated as a measured gain over experiment018 test results.',
        'production_enabled': False, 'data': DATA, 'data_sha256': sha(root/DATA),
        'input_sha256': sha(root/'data/prepared/dailysense-v1/answers.csv.gz'),
        'code_sha256': {p: sha(root/p) for p in source_files},
        'preserved_sha256': {p: sha(root/p) for p in frozen},
    }
    save(path, protocol)
    return {'rows': len(data), 'people': len(protocol['people']),
            'profiles': {k: len(v) for k, v in profiles.items()}, 'candidates_per_target': len(candidates)}


def person_weights(frame):
    w = 1/frame.groupby('participant').participant.transform('size').to_numpy(float)
    return w/w.mean()


def estimator(kind, algorithm):
    regression = kind == 'regression'
    seed = SEED
    if algorithm == 'fixed':
        cls = ExtraTreesRegressor if regression else ExtraTreesClassifier
        model = cls(n_estimators=250, min_samples_leaf=5, max_features=.8, random_state=20260926, n_jobs=1)
    elif algorithm.startswith('linear'):
        strong = algorithm == 'linear_strong'
        model = Ridge(alpha=100 if strong else 10) if regression else LogisticRegression(
            C=.03 if strong else .3, max_iter=4000, random_state=seed)
    elif algorithm.startswith('rbf'):
        regularized = algorithm == 'rbf_regularized'
        model = SVR(C=10 if regularized else 50, epsilon=5) if regression else SVC(
            C=.3 if regularized else 3, random_state=seed)
    elif algorithm == 'extra_regularized':
        cls = ExtraTreesRegressor if regression else ExtraTreesClassifier
        model = cls(n_estimators=500, max_depth=5, min_samples_leaf=8, max_features=.5, random_state=seed, n_jobs=1)
    elif algorithm == 'cat_regularized':
        cls = CatBoostRegressor if regression else CatBoostClassifier
        model = cls(iterations=350, depth=3, learning_rate=.035, l2_leaf_reg=15,
                    random_strength=2, random_seed=seed, verbose=False, thread_count=1,
                    allow_writing_files=False)
    else:
        raise ValueError(algorithm)
    return make_pipeline(SimpleImputer(strategy='median', add_indicator=True, keep_empty_features=True),
                         StandardScaler() if algorithm == 'fixed' else RobustScaler(), model)


def fit(frame, columns, kind, algorithm):
    w = person_weights(frame)
    if kind == 'classification':
        assert frame.target.nunique() == 2, 'Both classes required within every training fold'
        for c in (0, 1):
            mask = frame.target.to_numpy() == c
            w[mask] /= w[mask].sum()
        w /= w.mean()
    model = estimator(kind, algorithm)
    with threadpool_limits(limits=1):
        model.fit(frame[columns], frame.target, **{model.steps[-1][0]+'__sample_weight': w})
    return model


def predict(model, frame, columns, kind):
    with threadpool_limits(limits=1):
        if kind == 'regression':
            return np.clip(model.predict(frame[columns]), 0, 100)
        if hasattr(model, 'predict_proba'):
            return model.predict_proba(frame[columns])[:, list(model.classes_).index(1)]
        return 1/(1+np.exp(-np.clip(model.decision_function(frame[columns]), -30, 30)))


def classification_metrics(frame, scores, threshold=.5, decisions=None):
    y = frame.target.to_numpy(int)
    pred = (np.asarray(scores) >= threshold).astype(int) if decisions is None else np.asarray(decisions, int)
    w = person_weights(frame)
    cm = np.array([[w[(y == a) & (pred == b)].sum() for b in (0, 1)] for a in (0, 1)])
    counts = np.array([[np.sum((y == a) & (pred == b)) for b in (0, 1)] for a in (0, 1)])
    recall = np.diag(cm)/cm.sum(axis=1)
    precision = np.divide(np.diag(cm), cm.sum(axis=0), out=np.zeros(2), where=cm.sum(axis=0)>0)
    f1 = np.divide(2*np.diag(cm), cm.sum(axis=0)+cm.sum(axis=1), out=np.zeros(2), where=(cm.sum(axis=0)+cm.sum(axis=1))>0)
    individual = []
    for person in frame.participant.unique():
        mask = frame.participant.to_numpy() == person
        if len(np.unique(y[mask])) == 2:
            individual.append(np.mean([np.mean(pred[mask & (y == c)] == c) for c in (0, 1)]))
    return {'person_weighted_accuracy': float(np.average(y == pred, weights=w)),
            'unweighted_accuracy': float(np.mean(y == pred)), 'balanced_accuracy': float(recall.mean()),
            'low_recall': float(recall[0]), 'high_recall': float(recall[1]),
            'low_precision': float(precision[0]), 'high_precision': float(precision[1]),
            'macro_f1': float(f1.mean()), 'confusion_counts': counts.tolist(),
            'within_person_balanced_accuracy': float(np.mean(individual)) if individual else None,
            'people_with_both_classes': len(individual), 'coverage': 1.}


def regression_metrics(frame, scores):
    y = frame.target.to_numpy(float); p = np.asarray(scores); w = person_weights(frame)
    e = y-p
    return {'mae': float(np.average(abs(e), weights=w)),
            'rmse': float(np.sqrt(np.average(e**2, weights=w))),
            'r2': float(1-np.sum(w*e**2)/np.sum(w*(y-np.average(y, weights=w))**2)),
            'agreement_within_5': float(np.average(abs(e) <= 5, weights=w)),
            'agreement_within_10': float(np.average(abs(e) <= 10, weights=w)), 'coverage': 1.}


def choose_threshold(frame, scores):
    options = [(classification_metrics(frame, scores, t), float(t)) for t in THRESHOLDS]
    metric, threshold = max(options, key=lambda item: (item[0]['balanced_accuracy'],
        min(item[0]['low_recall'], item[0]['high_recall']), -abs(item[1]-.5), -item[1]))
    return threshold, metric


def select(frame, profiles, candidates, folds, kind):
    comparisons, predictions = [], {}
    for candidate in candidates:
        columns = profiles[candidate['profile']]
        p = np.full(len(frame), np.nan)
        for fold in folds:
            tr = frame.participant.isin(fold['training_people']).to_numpy()
            va = frame.participant.isin(fold['validation_people']).to_numpy()
            assert not np.any(tr & va) and np.all(tr | va)
            model = fit(frame.loc[tr], columns, kind, candidate['algorithm'])
            p[va] = predict(model, frame.loc[va], columns, kind)
        assert np.isfinite(p).all()
        if kind == 'classification':
            threshold, scores = choose_threshold(frame, p)
        else:
            threshold, scores = None, regression_metrics(frame, p)
        comparisons.append({**candidate, 'threshold': threshold, 'metrics': scores})
        predictions[candidate['key']] = p
    key = 'balanced_accuracy' if kind == 'classification' else 'mae'
    ranked = sorted(comparisons, key=lambda c: (-c['metrics'][key] if kind == 'classification' else c['metrics'][key], c['key']))
    # Diversity is fixed by estimator family, not handpicked after outer scores.
    top, families = [], set()
    for candidate in ranked:
        family = candidate['algorithm'].split('_')[0]
        if family not in families:
            top.append(candidate); families.add(family)
        if len(top) == 3:
            break
    ensemble_pred = np.mean([predictions[c['key']] for c in top], axis=0)
    if kind == 'classification':
        threshold, scores = choose_threshold(frame, ensemble_pred)
    else:
        threshold, scores = None, regression_metrics(frame, ensemble_pred)
    ensemble = {'key': 'diverse_top3', 'members': [c['key'] for c in top], 'threshold': threshold, 'metrics': scores}
    best = ranked[0]
    improve = scores[key] > best['metrics'][key] if kind == 'classification' else scores[key] < best['metrics'][key]
    chosen = top if improve else [best]
    chosen_threshold = threshold if improve else best['threshold']
    comparisons.append(ensemble)
    table = frame[['row_id', 'participant', 'target']].copy()
    for name, values in predictions.items():
        table[name] = values
    table['diverse_top3'] = ensemble_pred
    selection = {'kind': kind, 'selected': [c['key'] for c in chosen], 'threshold': chosen_threshold,
                 'criterion': key, 'comparisons': comparisons, 'folds': folds,
                 'interpretation': 'Inner fitting/selection scores; not validation estimates.'}
    return selection, table


def artifact(frame, profiles, chosen, kind):
    models = []
    for key in chosen['selected']:
        profile, algorithm = key.split(':')
        columns = profiles[profile]
        models.append({'key': key, 'columns': columns, 'model': fit(frame, columns, kind, algorithm)})
    return {'models': models, 'kind': kind, 'threshold': chosen['threshold'],
            'training_people': sorted(frame.participant.unique().tolist()),
            'production_enabled': False,
            'meaning': 'Daily fatigue research; no clinical or live-state validation.'}


def artifact_prediction(saved, frame):
    return np.mean([predict(x['model'], frame, x['columns'], saved['kind']) for x in saved['models']], axis=0)


def uncertainty(frame, arms, kind):
    """Paired participant bootstrap, retaining all observations within each person."""
    people = sorted(frame.participant.unique())
    grouped = {}
    y = frame.target.to_numpy()
    for name, values in arms.items():
        per_person = []
        for person in people:
            mask = frame.participant.to_numpy() == person
            if kind == 'classification':
                gy, gp = y[mask], np.asarray(values)[mask].astype(int)
                per_person.append(np.array([[np.mean((gy == a) & (gp == b)) for b in (0, 1)] for a in (0, 1)]))
            else:
                per_person.append(np.mean(abs(y[mask]-np.asarray(values)[mask])))
        grouped[name] = np.asarray(per_person)
    rng = np.random.default_rng(SEED)
    draws = {name: [] for name in arms}
    for _ in range(1000):
        indices = rng.integers(0, len(people), len(people))
        for name, values in grouped.items():
            mean = values[indices].mean(axis=0)
            value = (np.diag(mean)/mean.sum(axis=1)).mean() if kind == 'classification' else mean
            draws[name].append(float(value))
    result = {name: np.quantile(values, [.025, .975]).tolist() for name, values in draws.items()}
    diff = np.asarray(draws['inner_selected'])-np.asarray(draws['fixed_cardiac_extra5'])
    result['selected_minus_fixed'] = np.quantile(diff, [.025, .975]).tolist()
    return {'metric': 'balanced_accuracy' if kind == 'classification' else 'mae',
            'person_bootstrap_95': result, 'draws': 1000,
            'warning': 'Exploratory 28-person development cohort; not independent population validation.'}


def run(root, kind):
    root = Path(root)
    protocol = json.loads((root/PROTOCOL).read_text())
    out = root/'results'/NAME/kind
    if (out/'run-start.json').exists():
        raise ValueError('Run already started; completed outer outcomes must not trigger changes or replacement')
    assert sha(root/DATA) == protocol['data_sha256']
    for path, digest in {**protocol['code_sha256'], **protocol['preserved_sha256']}.items():
        assert sha(root/path) == digest, path
    frame = pd.read_csv(root/DATA)
    frame['target'] = (frame.rating >= 50).astype(int) if kind == 'classification' else frame.rating
    assert set(frame.participant) == set(protocol['people'])
    assert set(frame.participant).isdisjoint(protocol['historical_test_people_excluded'])
    save(out/'run-start.json', {'protocol_sha256': sha(root/PROTOCOL), 'data_sha256': sha(root/DATA),
                              'code_sha256': protocol['code_sha256'], 'kind': kind})
    all_predictions, model_manifest, fold_reports = [], [], []
    for fold_id, fold in enumerate(protocol['outer_folds']):
        train = frame[frame.participant.isin(fold['training_people'])].reset_index(drop=True)
        valid = frame[frame.participant.isin(fold['validation_people'])].reset_index(drop=True)
        selected, inner = select(train, protocol['profiles'], protocol['candidates'], fold['inner_folds'], kind)
        selected_path = out/f'fold-{fold_id}-selection.json'
        save(selected_path, selected)  # selection frozen before touching outer outcomes
        inner.to_csv(out/f'fold-{fold_id}-inner.csv.gz', index=False, compression={'method': 'gzip', 'mtime': 0})
        fitted = artifact(train, protocol['profiles'], selected, kind)
        fitted['outer_people_excluded'] = fold['validation_people']
        fitted['historical_test_people_excluded'] = protocol['historical_test_people_excluded']
        refcols = protocol['profiles']['cardiac_day']
        fixed = fit(train, refcols, kind, 'fixed')
        fitted['fixed_model'] = fixed
        fitted['fixed_columns'] = refcols
        constant = float(train.groupby('participant').target.mean().mean())
        fitted['training_constant'] = constant
        artifact_path = root/'models'/NAME/kind/f'fold-{fold_id}.joblib'
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(fitted, artifact_path)
        pred = valid[['row_id', 'participant', 'target']].copy()
        pred['fold'] = fold_id
        pred['training_constant'] = constant
        pred['fixed_cardiac_extra5'] = predict(fixed, valid, refcols, kind)
        pred['inner_selected'] = artifact_prediction(fitted, valid)
        pred['threshold'] = selected['threshold'] if kind == 'classification' else np.nan
        if kind == 'classification':
            for arm in protocol['arms']:
                pred[arm+'_decision'] = (pred[arm] >= (selected['threshold'] if arm == 'inner_selected' else .5)).astype(int)
        metrics = {arm: classification_metrics(valid, pred[arm], decisions=pred[arm+'_decision'])
                   if kind == 'classification' else regression_metrics(valid, pred[arm]) for arm in protocol['arms']}
        fold_reports.append({'fold': fold_id, 'selection': selected['selected'], 'threshold': selected['threshold'],
                             'validation_people': fold['validation_people'], 'rows': len(valid), 'metrics': metrics})
        all_predictions.append(pred)
        model_manifest.append({'fold': fold_id, 'path': str(artifact_path.relative_to(root)),
                               'sha256': sha(artifact_path), 'selection_sha256': sha(selected_path)})
        print(json.dumps({'kind': kind, 'outer_fold_completed': fold_id+1, 'selected': selected['selected']}), flush=True)
    predictions = pd.concat(all_predictions, ignore_index=True)
    assert predictions.row_id.is_unique and set(predictions.row_id) == set(frame.row_id)
    predpath = out/'outer-predictions.csv.gz'
    predictions.to_csv(predpath, index=False, compression={'method': 'gzip', 'mtime': 0})
    metrics = {arm: classification_metrics(predictions, predictions[arm], decisions=predictions[arm+'_decision'])
               if kind == 'classification' else regression_metrics(predictions, predictions[arm]) for arm in protocol['arms']}
    arms = {arm: predictions[arm+'_decision' if kind == 'classification' else arm].to_numpy() for arm in protocol['arms']}
    # Final artifact uses the same frozen selection procedure on all development
    # people. It is saved, but never evaluated against historical reserved people.
    final_selection, final_inner = select(frame, protocol['profiles'], protocol['candidates'], protocol['final_inner_folds'], kind)
    save(out/'final-selection.json', final_selection)
    final_inner.to_csv(out/'final-inner.csv.gz', index=False, compression={'method': 'gzip', 'mtime': 0})
    final = artifact(frame, protocol['profiles'], final_selection, kind)
    final['historical_test_people_excluded'] = protocol['historical_test_people_excluded']
    final_path = root/'models'/NAME/kind/'final-development.joblib'
    joblib.dump(final, final_path)
    score = metrics['inner_selected']
    gate = (score['balanced_accuracy'] >= .8 and min(score['low_recall'], score['high_recall']) >= .7
            if kind == 'classification' else score['mae'] <= 8 and score['mae'] <= .8*metrics['training_constant']['mae'] and score['r2'] >= .25)
    report = {'experiment': 20, 'kind': kind, 'evidence': protocol['evidence'], 'people': len(protocol['people']),
              'rows': len(frame), 'outer_metrics': metrics, 'folds': fold_reports,
              'uncertainty': uncertainty(predictions, arms, kind), 'exploratory_gate_met': bool(gate),
              'production_enabled': False, 'final_development_selection': final_selection['selected'],
              'historical_test_people_excluded': protocol['historical_test_people_excluded'],
              'warning': protocol['no_old_test_comparison']}
    save(out/'report.json', report)
    save(out/'manifest.json', {'models': model_manifest, 'predictions_sha256': sha(predpath),
                             'final_model': str(final_path.relative_to(root)), 'final_model_sha256': sha(final_path),
                             'final_selection_sha256': sha(out/'final-selection.json')})
    print(json.dumps({'kind': kind, 'outer_metrics': metrics, 'gate': bool(gate)}), flush=True)
    return report


def report_markdown(root):
    root = Path(root)
    reports = {k: json.loads((root/'results'/NAME/k/'report.json').read_text()) for k in KINDS}
    c, r = reports['classification'], reports['regression']
    lines = ['# Experiment 020: nested DailySense fatigue improvements', '',
             'Exploratory development evidence from **28 people and 357 daily answers**. Four outer participant folds evaluate the complete selection procedure; three inner participant folds choose models, ensembles and classification thresholds. The historical eight test people are excluded throughout.', '',
             'Labels remain observed daily fatigue VAS ≥50 versus <50 and the original 0–100 rating. No middle ratings were removed. This evaluates daily fatigue, not instantaneous states or clinical fitness for duty.', '',
             '## Classification', '',
             '| Planned arm | Balanced accuracy | Person-weighted accuracy | Raw accuracy | Low recall | High recall | Within-person BA |',
             '| --- | ---: | ---: | ---: | ---: | ---: | ---: |']
    for arm, m in c['outer_metrics'].items():
        lines.append('| '+arm+' | '+' | '.join(f'{100*m[k]:.1f}%' for k in ('balanced_accuracy', 'person_weighted_accuracy', 'unweighted_accuracy', 'low_recall', 'high_recall', 'within_person_balanced_accuracy'))+' |')
    lines += ['', '## Regression', '', '| Planned arm | MAE / 100 | RMSE | R² | Within ±10 |', '| --- | ---: | ---: | ---: | ---: |']
    for arm, m in r['outer_metrics'].items():
        lines.append(f"| {arm} | {m['mae']:.3f} | {m['rmse']:.3f} | {m['r2']:.3f} | {100*m['agreement_within_10']:.1f}% |")
    lines += ['', '## Interpretation and checks', '']
    for kind, data in reports.items():
        ci = data['uncertainty']['person_bootstrap_95']
        multiplier = 100 if kind == 'classification' else 1
        lines.append(f"- {kind}: selected {data['uncertainty']['metric']} 95% participant-bootstrap interval {ci['inner_selected'][0]*multiplier:.2f}–{ci['inner_selected'][1]*multiplier:.2f}; paired selected-minus-fixed interval {ci['selected_minus_fixed'][0]*multiplier:.2f}–{ci['selected_minus_fixed'][1]*multiplier:.2f}. Exploratory gate passed: {data['exploratory_gate_met']}.")
    lines += ['', 'Every arm covers all 357 eligible answers. The fixed cardiac ExtraTrees uses experiment 018 settings; improved candidates compare robust transforms, compact intact-channel physiology and preceding physiological baseline deviations. Thirty-six candidates across both targets, plus the fixed references and a deterministic diverse ensemble, were specified before fitting. Every transform requiring population statistics is fitted inside its training fold. No target history, identities, dates or other questionnaire answers enter the predictor matrix.', '',
              'The DailySense publisher archives match their published MD5, but many nested signal files are damaged. Only individually CRC-valid channels were used; missing channels remain missing. In particular, most BVP files are unavailable. Sensor windows stop at 21:30 Asia/Tokyo on SignalDate; no later samples enter. Baselines use only earlier sensor days. The nested comparison does not establish transfer across devices or to live employee monitoring.', '',
              'Historical test outcomes remain unchanged. These outer-fold scores are from a different cohort and must not be represented as a measured gain over experiment 018’s test score. Final development artifacts are saved with `production_enabled=False` and were not scored on the old test people.', '',
              '## Reproduction', '', 'From `neurasign engine/`, after verified DailySense preparation:', '', '```sh',
              '.venv/bin/python scripts/run_fatigue_nested.py prepare',
              '.venv/bin/python scripts/run_fatigue_nested.py run',
              '.venv/bin/python scripts/run_fatigue_nested.py verify',
              '.venv/bin/python scripts/run_fatigue_nested.py report',
              '.venv/bin/python -m unittest discover -s tests -p test_fatigue_nested.py -v', '```', '',
              'The protocol is immutable, and completed or started runs refuse replacement. Verification independently recomputes outer metrics, training-only constants, label mappings, grouped exclusions and artifact predictions. Data, individual predictions and fitted artifacts remain ignored.', '',
              'Source: [DailySense dataset](https://zenodo.org/records/10816004), CC BY 4.0.']
    (root/'experiments/020-fatigue-nested-results.md').write_text('\n'.join(lines)+'\n')
