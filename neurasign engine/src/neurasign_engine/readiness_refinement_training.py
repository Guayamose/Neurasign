"""Frozen nested model selection for experiment019, excluding prior test people."""
from __future__ import annotations
import json
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
from catboost import CatBoostRegressor
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import SplineTransformer, StandardScaler
from sklearn.svm import SVR
from threadpoolctl import threadpool_limits
from .reference_benchmark import weights, metrics, fit as old_fit, predict as old_predict, save, sha
from .readiness_refinement import NAME, SEED

ALGORITHMS = ['ridge100', 'spline100', 'svr10', 'svr100', 'cat_rmse3', 'cat_rmse5', 'cat_mae4', 'hgb7', 'hgb15']
CONFIGS = [{'profile': p, 'algorithm': a} for p in ['original','recovery_context'] for a in ALGORITHMS]


def key(config):
    return config['profile']+':'+config['algorithm']


def nested_folds(frame):
    folds = []
    for index, (train, valid) in enumerate(GroupKFold(n_splits=4).split(frame, groups=frame.participant)):
        outer = frame.iloc[train]
        inner = []
        for tr, va in GroupKFold(n_splits=3).split(outer,groups=outer.participant):
            inner.append({'training_people':sorted(outer.iloc[tr].participant.unique()),
                          'validation_people':sorted(outer.iloc[va].participant.unique())})
        folds.append({'fold':index,'training_people':sorted(outer.participant.unique()),
                      'validation_people':sorted(frame.iloc[valid].participant.unique()),'inner':inner})
    return folds


def estimator(algorithm):
    pre = [SimpleImputer(strategy='median', add_indicator=True, keep_empty_features=True), StandardScaler()]
    if algorithm.startswith('ridge'):
        model = Ridge(alpha=float(algorithm[5:]))
    elif algorithm.startswith('spline'):
        pre.append(SplineTransformer(n_knots=4,degree=2,extrapolation='constant',include_bias=False))
        model = Ridge(alpha=float(algorithm[6:]))
    elif algorithm.startswith('svr'):
        model = SVR(C=float(algorithm[3:]),epsilon=1.)
    elif algorithm.startswith('cat'):
        model = CatBoostRegressor(iterations=650,depth=int(algorithm[-1]),learning_rate=.035,l2_leaf_reg=10,
            loss_function='MAE' if 'mae' in algorithm else 'RMSE',random_seed=SEED,thread_count=1,
            allow_writing_files=False,verbose=False)
    elif algorithm.startswith('hgb'):
        model = HistGradientBoostingRegressor(loss='absolute_error',max_iter=300,max_leaf_nodes=int(algorithm[3:]),
            min_samples_leaf=25,l2_regularization=5,learning_rate=.05,early_stopping=False,random_state=SEED)
    else:
        raise ValueError(algorithm)
    return make_pipeline(*pre,model)


def train(frame, columns, algorithm):
    pipeline = estimator(algorithm)
    weight = weights(frame)
    with threadpool_limits(limits=1):
        pipeline.fit(frame[columns],frame.target,standardscaler__sample_weight=weight,
                     **{pipeline.steps[-1][0]+'__sample_weight':weight})
    return pipeline


def output(model, frame, columns):
    with threadpool_limits(limits=1):
        return np.clip(model.predict(frame[columns]),0,100)


def predict_bundle(bundle, frame):
    return np.mean([output(item['model'],frame,item['columns']) for item in bundle['models']],axis=0)


def search(frame, folds, profiles, folder):
    folder.mkdir(parents=True,exist_ok=True)
    predictions = {};comparison=[]
    for config in CONFIGS:
        name=key(config);path=folder/(name.replace(':','-')+'.csv.gz')
        if path.exists():
            cached=pd.read_csv(path)
            np.testing.assert_array_equal(cached.row_id,frame.row_id)
            p=cached.prediction.to_numpy()
        else:
            p=np.full(len(frame),np.nan)
            for fold in folds:
                tr=frame.participant.isin(fold['training_people']).to_numpy()
                va=frame.participant.isin(fold['validation_people']).to_numpy()
                assert not (tr&va).any() and (tr|va).all()
                m=train(frame[tr],profiles[config['profile']],config['algorithm'])
                p[va]=output(m,frame[va],profiles[config['profile']])
            assert np.isfinite(p).all()
            pd.DataFrame({'row_id':frame.row_id,'prediction':p}).to_csv(path,index=False,compression={'method':'gzip','mtime':0})
        predictions[name]=p
        comparison.append({'configuration':config,**metrics(frame,p,'regression')})
        print(json.dumps({'stage':str(folder.name),'candidate':name,'mae':comparison[-1]['mae']}),flush=True)
    order=sorted(comparison,key=lambda c:c['mae'])
    top=[item['configuration'] for item in order[:3]]
    ensemble=np.mean([predictions[key(c)] for c in top],axis=0)
    ensemble_metrics=metrics(frame,ensemble,'regression')
    selected=top if ensemble_metrics['mae']<order[0]['mae'] else [order[0]['configuration']]
    frozen={'selected':selected,'comparison':comparison,'ensemble_top3':{'members':top,**ensemble_metrics},
            'criterion':'Minimum person-weighted inner MAE; outer labels not inspected'}
    save(folder/'selection.json',frozen)
    return frozen


def fit_bundle(frame, configs, profiles, excluded):
    models=[]
    for config in configs:
        columns=profiles[config['profile']]
        models.append({'model':train(frame,columns,config['algorithm']),'columns':columns,'configuration':config})
    return {'models':models,'training_people':sorted(frame.participant.unique()),'excluded_people':sorted(excluded),
            'production_enabled':False,'target':'Observed Oura daily score, not live employee readiness'}


def fixed_bundle(frame, profiles, excluded):
    columns=profiles['original']
    return {'models':[{'model':old_fit(frame,columns,'regression',name),'columns':columns,
                      'configuration':{'profile':'original','algorithm':name}} for name in ['svm10','cat3','cat5']],
            'training_people':sorted(frame.participant.unique()),'excluded_people':sorted(excluded),
            'production_enabled':False,'target':'Observed Oura daily score, not live employee readiness'}


def bootstrap(frame):
    rng=np.random.default_rng(SEED);people=frame.participant.unique();values=[]
    for _ in range(1000):
        parts=[]
        for i, person in enumerate(rng.choice(people,len(people),replace=True)):
            part=frame[frame.participant==person].copy();part.participant=str(i);parts.append(part)
        data=pd.concat(parts,ignore_index=True)
        selected=metrics(data,data.selected,'regression')['mae'];reference=metrics(data,data.fixed,'regression')['mae']
        values.append([selected,selected-reference])
    return {'selected_mae_95':np.quantile(np.array(values)[:,0],[.025,.975]).tolist(),
            'paired_mae_difference_95':np.quantile(np.array(values)[:,1],[.025,.975]).tolist(),
            'resamples':1000,'warning':'Exploratory reused development cohort; not a fresh external confidence guarantee.'}


def load(root):
    path=root/'experiments/019-readiness-refinement-protocol.json'
    p=json.loads(path.read_text());data_path=root/'data/prepared'/NAME/'days.csv.gz'
    assert sha(data_path)==p['data_sha256']
    for file,digest in p['code_sha256'].items():
        assert sha(root/file)==digest, f'Frozen code changed: {file}'
    data=pd.read_csv(data_path)
    assert sorted(data.participant.unique())==p['people']
    assert set(data.participant).isdisjoint(p['old_test_people_excluded'])
    return p,data,path


def run(root):
    p,data,path=load(root);out=root/'results'/NAME;modeldir=root/'models'/NAME
    if (out/'report.json').exists():
        raise ValueError('Completed experiment exists; use verify')
    out.mkdir(parents=True,exist_ok=True);modeldir.mkdir(parents=True,exist_ok=True)
    freeze={'protocol_sha256':sha(path),'data_sha256':p['data_sha256'],'code_sha256':p['code_sha256']}
    if (out/'run-start.json').exists():
        assert json.loads((out/'run-start.json').read_text())==freeze
    else:
        save(out/'run-start.json',freeze)
    predictions=[];artifacts=[]
    for fold in p['folds']:
        train_frame=data[data.participant.isin(fold['training_people'])].reset_index(drop=True)
        valid=data[data.participant.isin(fold['validation_people'])].reset_index(drop=True)
        folder=out/f'outer-{fold["fold"]}'
        selection=search(train_frame,fold['inner'],p['profiles'],folder)
        for arm,bundle in [('selected',fit_bundle(train_frame,selection['selected'],p['profiles'],fold['validation_people'])),
                           ('fixed',fixed_bundle(train_frame,p['profiles'],fold['validation_people']))]:
            artifact=modeldir/f'outer-{fold["fold"]}-{arm}.joblib';joblib.dump(bundle,artifact)
            valid[arm]=predict_bundle(bundle,valid)
            artifacts.append({'path':str(artifact.relative_to(root)),'sha256':sha(artifact),'fold':fold['fold'],'arm':arm})
        valid['constant']=np.average(train_frame.target,weights=weights(train_frame))
        valid['fold']=fold['fold']
        predictions.append(valid[['row_id','participant','target','selected','fixed','constant','fold']])
    pred=pd.concat(predictions,ignore_index=True).sort_values('row_id').reset_index(drop=True)
    assert pred.row_id.is_unique and set(pred.row_id)==set(data.row_id)
    pred.to_csv(out/'outer-predictions.csv.gz',index=False,compression={'method':'gzip','mtime':0})
    outer_report={arm:metrics(pred,pred[arm],'regression') for arm in ['selected','fixed','constant']}
    interval=bootstrap(pred)
    # Final fitting searches only the development cohort; no old test set is reopened.
    final_folds=[]
    for tr,va in GroupKFold(n_splits=3).split(data,groups=data.participant):
        final_folds.append({'training_people':sorted(data.iloc[tr].participant.unique()),'validation_people':sorted(data.iloc[va].participant.unique())})
    final_selection=search(data,final_folds,p['profiles'],out/'final-selection')
    bundle=fit_bundle(data,final_selection['selected'],p['profiles'],p['old_test_people_excluded'])
    final_path=modeldir/'selected-development.joblib';joblib.dump(bundle,final_path)
    artifacts.append({'path':str(final_path.relative_to(root)),'sha256':sha(final_path),'arm':'development_fit'})
    selected,fixed=outer_report['selected'],outer_report['fixed']
    report={'name':NAME,'people':len(p['people']),'rows':len(data),'outer':outer_report,'uncertainty':interval,
            'relative_mae_improvement_over_fixed':1-selected['mae']/fixed['mae'],
            'research_gate_met':bool(selected['mae']<=.9*fixed['mae'] and selected['mae']<=4 and selected['r2']>=.5),
            'final_selection':final_selection['selected'],'outer_selections':[json.loads((out/f'outer-{f["fold"]}'/'selection.json').read_text())['selected'] for f in p['folds']],
            'production_enabled':False,'evidence':'Exploratory nested development only; prior4 test people remain excluded.'}
    save(out/'report.json',report)
    save(out/'evaluation.json',{'artifacts':artifacts,'predictions_sha256':sha(out/'outer-predictions.csv.gz'),
                              'selection_sha256':{str(x.relative_to(root)):sha(x) for x in out.glob('*/selection.json')}})
    print(json.dumps(report),flush=True)
    return report


def verify(root):
    protocol,data,path=load(root);out=root/'results'/NAME
    freeze=json.loads((out/'run-start.json').read_text());e=json.loads((out/'evaluation.json').read_text())
    assert sha(path)==freeze['protocol_sha256']
    for file,digest in protocol['source_sha256'].items():assert sha(root/file)==digest
    for file,digest in e['selection_sha256'].items():assert sha(root/file)==digest
    assert sha(out/'outer-predictions.csv.gz')==e['predictions_sha256']
    pred=pd.read_csv(out/'outer-predictions.csv.gz')
    original=data.set_index('row_id').loc[pred.row_id]
    np.testing.assert_array_equal(original.target,pred.target)
    np.testing.assert_array_equal(original.participant,pred.participant)
    replays=0
    for item in e['artifacts']:
        assert sha(root/item['path'])==item['sha256']
        bundle=joblib.load(root/item['path']);assert bundle['production_enabled'] is False
        assert set(bundle['training_people']).isdisjoint(bundle['excluded_people'])
        assert set(bundle['training_people']).isdisjoint(protocol['old_test_people_excluded'])
        if 'fold' in item:
            rows=pred[pred.fold==item['fold']]
            features=data.set_index('row_id').loc[rows.row_id]
            assert set(features.participant)==set(bundle['excluded_people'])
            np.testing.assert_allclose(predict_bundle(bundle,features),rows[item['arm']],atol=1e-10)
            replays+=1
    report=json.loads((out/'report.json').read_text());count=0
    # Direct NumPy implementation independent of the benchmark scoring helper.
    people,inverse,n=np.unique(pred.participant,return_inverse=True,return_counts=True)
    w=1/(len(people)*n[inverse]);y=pred.target.to_numpy();variance=np.dot(w,(y-np.dot(w,y))**2)
    for arm in ['selected','fixed','constant']:
        error=y-pred[arm].to_numpy();a=np.abs(error)
        actual={'mae':np.dot(w,a),'rmse':np.sqrt(np.dot(w,error**2)),
                'r2':1-np.dot(w,error**2)/variance,'agreement_within_5':np.dot(w,a<=5),'agreement_within_10':np.dot(w,a<=10)}
        for metric,value in actual.items():
            np.testing.assert_allclose(value,report['outer'][arm][metric],atol=1e-10);count+=1
    for fold in protocol['folds']:
        tr=data[data.participant.isin(fold['training_people'])]
        pp,ii,nn=np.unique(tr.participant,return_inverse=True,return_counts=True)
        mean=np.dot(1/(len(pp)*nn[ii]),tr.target)
        np.testing.assert_allclose(pred.loc[pred.fold==fold['fold'],'constant'],mean,atol=1e-10)
        selection=json.loads((out/f'outer-{fold["fold"]}'/'selection.json').read_text())
        recomputed=[]
        for row in selection['comparison']:
            saved=pd.read_csv(out/f'outer-{fold["fold"]}'/(key(row['configuration']).replace(':','-')+'.csv.gz'))
            truth=tr.set_index('row_id').loc[saved.row_id]
            pp,ii,nn=np.unique(truth.participant,return_inverse=True,return_counts=True)
            mae=np.dot(1/(len(pp)*nn[ii]),np.abs(truth.target.to_numpy()-saved.prediction.to_numpy()))
            np.testing.assert_allclose(mae,row['mae'],atol=1e-10);count+=1
        assert all(set(inner['training_people']).isdisjoint(inner['validation_people']) and
                   set(inner['training_people']+inner['validation_people'])==set(fold['training_people']) for inner in fold['inner'])
    result={'passed':True,'independent_metric_checks':count,'outer_artifact_replays':replays,
            'source_hashes':len(protocol['source_sha256']),'prior_test_people_excluded':True}
    save(out/'verification.json',result)
    return result
