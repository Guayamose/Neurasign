"""Person-disjoint development search and a single reserved-person evaluation."""
from __future__ import annotations
import hashlib
import json
import math
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
from catboost import CatBoostClassifier, CatBoostRegressor
from sklearn.dummy import DummyClassifier, DummyRegressor
from sklearn.ensemble import ExtraTreesClassifier, ExtraTreesRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import confusion_matrix, r2_score, roc_auc_score
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC, SVR
from threadpoolctl import threadpool_limits

SEED = 20260926


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    path = Path(path);path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False)+'\n')


def weights(frame):
    """Equal participant mass, then equal observed reference responses per person."""
    counts = frame.groupby('participant').participant.transform('size')
    result = 1/counts.to_numpy(float)
    return result/result.mean()


def split_people(people):
    people = sorted(str(p) for p in people)
    order = np.random.default_rng(SEED).permutation(people).tolist()
    n = max(3, math.ceil(len(people)*.2))
    return {'development': sorted(order[n:]), 'test': sorted(order[:n])}


def candidates(kind):
    return (['linear1', 'linear10', 'linear100', 'svm1', 'svm10', 'svm100', 'extra2', 'extra5', 'cat3', 'cat5']
            if kind == 'regression' else
            ['linear0.1', 'linear1', 'linear10', 'svm0.1', 'svm1', 'svm10', 'extra2', 'extra5', 'cat3', 'cat5'])


def estimator(kind, name):
    regression = kind == 'regression'
    if name == 'baseline':
        model = DummyRegressor(strategy='mean') if regression else DummyClassifier(strategy='prior')
    elif name.startswith('linear'):
        value = float(name[6:])
        model = Ridge(alpha=value) if regression else LogisticRegression(C=value, max_iter=3000, random_state=SEED)
    elif name.startswith('svm'):
        value = float(name[3:])
        model = SVR(C=value, epsilon=2.) if regression else SVC(C=value, probability=False, random_state=SEED)
    elif name.startswith('extra'):
        cls = ExtraTreesRegressor if regression else ExtraTreesClassifier
        model = cls(n_estimators=250, min_samples_leaf=int(name[5:]), max_features=.8, random_state=SEED, n_jobs=1)
    elif name.startswith('cat'):
        cls = CatBoostRegressor if regression else CatBoostClassifier
        model = cls(iterations=450, depth=int(name[3:]), learning_rate=.04, l2_leaf_reg=5., random_seed=SEED,
                    thread_count=1, verbose=False, allow_writing_files=False)
    else:
        raise ValueError(name)
    return make_pipeline(SimpleImputer(strategy='median', add_indicator=True, keep_empty_features=True), StandardScaler(), model)


def fit(frame, columns, kind, name):
    w = weights(frame)
    if kind == 'classification' and name != 'baseline':
        for label in (0, 1):
            mask = frame.target.to_numpy() == label
            if mask.any():
                w[mask] /= w[mask].sum()
        w /= w.mean()
    if kind == 'classification' and frame.target.nunique() == 1:
        name = 'baseline'
    model = estimator(kind, name)
    with threadpool_limits(limits=1):
        model.fit(frame[columns], frame.target, **{model.steps[-1][0]+'__sample_weight': w})
    return model


def predict(model, frame, columns, kind):
    if kind == 'regression':
        return np.clip(model.predict(frame[columns]), 0, 100)
    if hasattr(model, 'predict_proba'):
        if len(model.classes_) == 1:
            return np.full(len(frame), float(model.classes_[0]))
        return model.predict_proba(frame[columns])[:, list(model.classes_).index(1)]
    # SVM margins mapped monotonically for a fixed zero-margin decision boundary.
    return 1/(1+np.exp(-np.clip(model.decision_function(frame[columns]), -30, 30)))


def metrics(frame, predictions, kind):
    y = frame.target.to_numpy(float);p = np.asarray(predictions, float);w = weights(frame)
    if kind == 'regression':
        residual = np.abs(y-p)
        return {'mae': float(np.average(residual, weights=w)), 'rmse': float(np.sqrt(np.average((y-p)**2, weights=w))),
                'r2': float(r2_score(y, p, sample_weight=w)),
                'agreement_within_5': float(np.average(residual <= 5, weights=w)),
                'agreement_within_10': float(np.average(residual <= 10, weights=w))}
    labels = (p >= .5).astype(int)
    cm = confusion_matrix(y, labels, labels=[0, 1], sample_weight=w)
    recall = np.divide(np.diag(cm), cm.sum(axis=1), out=np.full(2, np.nan), where=cm.sum(axis=1)>0)
    f1 = np.divide(2*np.diag(cm), cm.sum(axis=0)+cm.sum(axis=1), out=np.zeros(2), where=cm.sum(axis=0)+cm.sum(axis=1)>0)
    individual=[]
    for person in frame.participant.unique():
        mask=frame.participant.to_numpy()==person
        if len(np.unique(y[mask]))==2:
            individual.append(float(np.mean([np.mean(labels[mask & (y==c)]==c) for c in (0,1)])))
    return {'accuracy': float(np.average(labels == y, weights=w)),
            'balanced_accuracy': float(recall.mean()) if np.isfinite(recall).all() else None,
            'low_recall': float(recall[0]) if np.isfinite(recall[0]) else None,
            'high_recall': float(recall[1]) if np.isfinite(recall[1]) else None,
            'macro_f1': float(f1.mean()), 'roc_auc': float(roc_auc_score(y, p, sample_weight=w)) if len(np.unique(y))==2 else None,
            'confusion_counts': confusion_matrix(y, labels, labels=[0, 1]).tolist(),
            'within_person_balanced_accuracy':float(np.mean(individual)) if individual else None,
            'people_with_both_classes':len(individual)}


def interval(frame, predictions, kind):
    rng = np.random.default_rng(SEED);people = frame.participant.unique();values = []
    copy = frame.copy();copy['_prediction'] = predictions
    key = 'mae' if kind == 'regression' else 'balanced_accuracy'
    for _ in range(1000):
        parts = []
        for i, person in enumerate(rng.choice(people, len(people), replace=True)):
            part = copy[copy.participant == person].copy();part.participant = str(i);parts.append(part)
        boot = pd.concat(parts, ignore_index=True)
        value = metrics(boot, boot._prediction, kind)[key]
        if value is not None:
            values.append(value)
    return {'metric': key, 'person_bootstrap_95': [float(v) for v in np.quantile(values, [.025, .975])] if values else None,
            'valid_resamples': len(values), 'warning': 'Few reserved people; this interval does not establish population validation.'}


def run(root, name, data_path, protocol_path):
    out = root/'results'/name
    if (out/'report.json').exists():
        raise ValueError('Completed benchmark exists; verify instead of reopening test selection')
    protocol = json.loads((root/protocol_path).read_text())
    data = pd.read_csv(root/data_path, dtype={'participant':str})
    assert not data.row_id.duplicated().any() and data.target.notna().all()
    split = protocol['split'];kind = protocol['kind'];profiles = protocol['profiles']
    assert set(split['development']).isdisjoint(split['test'])
    assert set(data.participant) == set(split['development'])|set(split['test'])
    dev = data[data.participant.isin(split['development'])].reset_index(drop=True)
    test = data[data.participant.isin(split['test'])].reset_index(drop=True)
    assert len(dev) and len(test)
    forbidden = {'target', 'participant', 'row_id', 'unit_id', 'session', 'date', 'outcome', 'score'}
    assert all(not forbidden.intersection(cols) for cols in profiles.values())
    freeze = {'protocol': str(protocol_path), 'protocol_sha256':sha(root/protocol_path),
              'code_sha256': sha(__file__), 'data': str(data_path), 'data_sha256':sha(root/data_path),
              'dependencies': {p: sha(root/p) for p in protocol.get('code_dependencies', [])}}
    save(out/'run-start.json', freeze)
    cv = list(GroupKFold(n_splits=min(4, dev.participant.nunique())).split(dev, groups=dev.participant))
    comparisons = [];cv_predictions = {};folds = []
    for tr, va in cv:
        assert set(dev.iloc[tr].participant).isdisjoint(dev.iloc[va].participant)
        folds.append({'training_people':sorted(dev.iloc[tr].participant.unique()), 'validation_people':sorted(dev.iloc[va].participant.unique())})
    for profile, columns in profiles.items():
        for algorithm in candidates(kind):
            p = np.full(len(dev), np.nan)
            for tr, va in cv:
                model = fit(dev.iloc[tr], columns, kind, algorithm)
                p[va] = predict(model, dev.iloc[va], columns, kind)
            key = profile+':'+algorithm;cv_predictions[key] = p
            result = {'key':key, 'profile':profile, 'algorithm':algorithm, **metrics(dev,p,kind)}
            comparisons.append(result)
        print(json.dumps({'benchmark':name,'profile_complete':profile,'comparisons':len(comparisons)}),flush=True)
    key = 'mae' if kind == 'regression' else 'balanced_accuracy'
    ranked = sorted(comparisons, key=lambda r:r[key] if kind == 'regression' else -(r[key] if r[key] is not None else -1))
    top = ranked[:3]
    ensemble_predictions = np.mean([cv_predictions[c['key']] for c in top],axis=0)
    ensemble = {'key':'top3_ensemble', 'members':[c['key'] for c in top], **metrics(dev,ensemble_predictions,kind)}
    cv_predictions['top3_ensemble'] = ensemble_predictions;comparisons.append(ensemble)
    improve = ensemble[key] < ranked[0][key] if kind == 'regression' else ensemble[key] > ranked[0][key]
    chosen = top if improve else [ranked[0]]
    selection = {'criterion':key, 'selected':[c['key'] for c in chosen], 'folds':folds, 'comparisons':comparisons,
                 'note':'Selection scores are development scores, not independent performance estimates.'}
    save(out/'frozen-selection.json', selection)
    prediction_table = dev[['row_id','participant','target']].copy()
    for column, values in cv_predictions.items():prediction_table[column]=values
    prediction_table.to_csv(out/'development-predictions.csv.gz',index=False,compression={'method':'gzip','mtime':0})
    artifacts=[];held_predictions=[]
    for candidate in chosen:
        columns=profiles[candidate['profile']]
        model=fit(dev,columns,kind,candidate['algorithm']);held_predictions.append(predict(model,test,columns,kind))
        artifacts.append({'model':model,'columns':columns,'key':candidate['key']})
    selected=np.mean(held_predictions,axis=0)
    baseline_model=fit(dev,profiles[next(iter(profiles))],kind,'baseline')
    baseline=predict(baseline_model,test,profiles[next(iter(profiles))],kind)
    artifact={'models':artifacts,'kind':kind,'production_enabled':False,'target_definition':protocol['target_definition'],
              'training_people':split['development'],'test_people_excluded':split['test'],'selection':selection['selected']}
    model_path=root/'models'/name/'selected.joblib';model_path.parent.mkdir(parents=True,exist_ok=True);joblib.dump(artifact,model_path)
    predictions=test[['row_id','participant','target']].copy();predictions['selected']=selected;predictions['baseline']=baseline
    predictions.to_csv(out/'test-predictions.csv.gz',index=False,compression={'method':'gzip','mtime':0})
    selected_metrics=metrics(test,selected,kind);baseline_metrics=metrics(test,baseline,kind)
    if kind=='classification':
        gate=selected_metrics['balanced_accuracy'] is not None and selected_metrics['balanced_accuracy']>=.8 and min(selected_metrics['low_recall'],selected_metrics['high_recall'])>=.7
    else:
        gate=selected_metrics['mae']<=8 and selected_metrics['mae']<=.8*baseline_metrics['mae'] and selected_metrics['r2']>=.25
    report={'name':name,'kind':kind,'selected':selected_metrics,'baseline':baseline_metrics,'uncertainty':interval(test,selected,kind),
            'test_people':len(split['test']),'test_rows':len(test),'development_people':len(split['development']),'development_rows':len(dev),
            'selection':selection['selected'],'research_gate_met':bool(gate), 'production_enabled':False,
            'test_once_after_development_selection':True,'target_definition':protocol['target_definition']}
    save(out/'report.json',report)
    save(out/'evaluation.json',{'model':str(model_path.relative_to(root)),'model_sha256':sha(model_path),
                              'predictions_sha256':sha(out/'test-predictions.csv.gz'),'selection_sha256':sha(out/'frozen-selection.json')})
    print(json.dumps(report),flush=True)
    return report


def verify(root,name):
    out=root/'results'/name;freeze=json.loads((out/'run-start.json').read_text());evaluation=json.loads((out/'evaluation.json').read_text())
    assert sha(__file__)==freeze['code_sha256'] and sha(root/freeze['protocol'])==freeze['protocol_sha256']
    assert sha(root/freeze['data'])==freeze['data_sha256']
    for path,digest in freeze['dependencies'].items():assert sha(root/path)==digest
    assert sha(root/evaluation['model'])==evaluation['model_sha256']
    assert sha(out/'test-predictions.csv.gz')==evaluation['predictions_sha256']
    assert sha(out/'frozen-selection.json')==evaluation['selection_sha256']
    artifact=joblib.load(root/evaluation['model']);data=pd.read_csv(root/freeze['data'],dtype={'participant':str})
    predictions=pd.read_csv(out/'test-predictions.csv.gz',dtype={'participant':str})
    test=data.set_index('row_id').loc[predictions.row_id].reset_index()
    assert set(test.participant).isdisjoint(artifact['training_people']) and artifact['production_enabled'] is False
    np.testing.assert_allclose(np.mean([predict(m['model'],test,m['columns'],artifact['kind']) for m in artifact['models']],axis=0),predictions.selected,atol=1e-10)
    report=json.loads((out/'report.json').read_text())
    for arm in ('selected','baseline'):
        actual=metrics(predictions,predictions[arm],artifact['kind'])
        for key,value in actual.items():
            if value is None:assert report[arm][key] is None
            else:np.testing.assert_allclose(value,report[arm][key],atol=1e-10)
    result={'status':'passed','artifact_replayed':True,'person_disjoint':True,'metric_recalculation':True}
    save(out/'verification.json',result);return result
