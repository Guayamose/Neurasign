"""Source-aware development experiments; held-out data require a separate command.

All CV scores in this module are selection scores, not an unbiased estimate of
the winner. IDs, conditions, questionnaire fields and session time are metadata.
"""
from __future__ import annotations
from concurrent.futures import ProcessPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import warnings

import numpy as np
import pandas as pd
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import ExtraTreesRegressor, HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.metrics import confusion_matrix
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import RobustScaler, FunctionTransformer
from sklearn.svm import SVR
from threadpoolctl import threadpool_limits

from .schema import TARGETS, SEED
from .training import weights
from .transfer_features import FEATURES, PROFILES

ALGORITHMS = ['ridge100', 'ridge1000', 'svr10', 'boost_squared', 'boost_absolute', 'cat4', 'cat6', 'extra']


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, allow_nan=False)+'\n')


def columns(profile, frame):
    history=profile.endswith('_history');base=profile.removesuffix('_history')
    if base == 'latent':
        cols=FEATURES+[f'latent_{i}' for i in range(16)]
    elif base == 'native':
        cols=FEATURES+['native_rmssd_ms','native_sdnn_ms','native_pnn50','native_coverage']
    else:
        cols=PROFILES[base]
    if history: cols=cols+[f+'__delta' for f in cols if f+'__delta' in frame]
    assert not set(cols)&(set(TARGETS)|{'participant','session','unit_id','source_end','dataset'})
    return cols


def fit_weights(frame):
    """Equal datasets, then equal people, tasks, observations."""
    w=weights(frame)
    if 'dataset' in frame:
        for dataset in frame.dataset.unique():
            mask=frame.dataset.to_numpy()==dataset
            w[mask]/=w[mask].sum()
    return w/w.mean()


def thin(frame):
    indices=[]
    for _,g in frame.sort_values('source_end').groupby('unit_id',sort=True):
        indices.extend(g.iloc[np.unique(np.linspace(0,len(g)-1,min(20,len(g))).astype(int))].index)
    return frame.loc[indices]


def make_model(algorithm):
    if algorithm.startswith('constant_'):return DummyRegressor(strategy=algorithm.split('_')[1])
    if algorithm.startswith('cat'):
        from catboost import CatBoostRegressor
        model=CatBoostRegressor(iterations=300,depth=int(algorithm[-1]),learning_rate=.035,
              loss_function='MAE',l2_leaf_reg=10,random_seed=SEED,thread_count=1,
              verbose=False,allow_writing_files=False)
    elif algorithm=='extra':
        model=ExtraTreesRegressor(n_estimators=150,min_samples_leaf=15,max_features=.8,random_state=SEED,n_jobs=1)
    elif algorithm.startswith('boost'):
        return HistGradientBoostingRegressor(loss='absolute_error' if algorithm.endswith('absolute') else 'squared_error',
          max_iter=180,max_leaf_nodes=7,min_samples_leaf=30,l2_regularization=20,learning_rate=.04,
          early_stopping=False,max_bins=64,random_state=SEED)
    elif algorithm.startswith('ridge'):model=Ridge(alpha=float(algorithm[5:]))
    elif algorithm.startswith('svr'):model=SVR(C=float(algorithm[3:]),epsilon=.05)
    else:raise ValueError(algorithm)
    return make_pipeline(SimpleImputer(strategy='median',add_indicator=True,keep_empty_features=True),
           RobustScaler(quantile_range=(10,90)),FunctionTransformer(np.tanh,feature_names_out='one-to-one'),model)


def fit_predict(train, valid, target, config, return_model=False):
    train=train[train[target].notna()];fitting=thin(train)
    cols=columns(config['profile'],train);model=make_model(config['algorithm'])
    low,high=TARGETS[target]['range']
    param=(model.steps[-1][0]+'__sample_weight') if hasattr(model,'steps') else 'sample_weight'
    with threadpool_limits(limits=1),warnings.catch_warnings():
        warnings.simplefilter('ignore',category=RuntimeWarning)
        model.fit(fitting[cols],(fitting[target]-low)/(high-low),**{param:fit_weights(fitting)})
        pred=np.clip(model.predict(valid[cols]),0,1)*(high-low)+low
    if return_model:return pred,{'model':model,'columns':cols,'target':target,'range':[low,high],
                                 'config':config,'training_ids':sorted(train.participant.unique())}
    return pred


def metrics(frame,target,prediction):
    y=frame[target].to_numpy(float);p=np.asarray(prediction,float)
    assert len(y)==len(p) and np.isfinite(p).all()
    error=abs(y-p);w=weights(frame)
    perperson=frame.assign(error=error).groupby(['participant','unit_id']).error.mean().groupby('participant').mean()
    ordinal=target=='mental_effort';tol=1 if ordinal else 10
    labels=np.arange(1,6) if ordinal else np.arange(3)
    actual=y.astype(int) if ordinal else np.minimum((y/(100/3)).astype(int),2)
    predicted=np.floor(p+.5).astype(int) if ordinal else np.minimum((p/(100/3)).astype(int),2)
    cm=confusion_matrix(actual,predicted,labels=labels,sample_weight=w)
    present=cm.sum(axis=1)>0
    recall=np.divide(cm.diagonal(),cm.sum(axis=1),out=np.zeros(len(labels)),where=present)
    return {'mae':float(perperson.mean()),'within_tolerance':float(np.average(error<=tol,weights=w)),
            'tolerance_points':tol,'exact_or_three_level_accuracy':float(np.average(actual==predicted,weights=w)),
            'balanced_accuracy':float(recall[present].mean()),'represented_classes':int(present.sum()),
            'confusion_matrix_weighted':cm.tolist(),'people':len(perperson),'blocks':int(frame.unit_id.nunique()),
            'windows':len(frame),'per_person_mae':perperson.to_dict()}


def grouped_folds(frame):
    folds=[[] for _ in range(5)]
    for _,g in frame.groupby('dataset',sort=True):
        ids=np.random.default_rng(SEED).permutation(sorted(g.participant.unique()))
        for i,part in enumerate(np.array_split(ids,5)):folds[i].extend(part.tolist())
    return folds


def evaluate_job(args):
    path,out,target,config,folds,source_mode=args
    frame=pd.read_csv(path);frame=frame[frame[target].notna()];rows=[]
    for i,ids in enumerate(folds):
        valid=frame[frame.participant.isin(ids)];train=frame[~frame.participant.isin(ids)]
        if not len(valid):continue
        for dataset,g in valid.groupby('dataset'):
            fit=train if source_mode=='pooled' else train[train.dataset==dataset]
            if not len(fit):continue
            p=fit_predict(fit,g,target,config)
            d=g[['participant','session','unit_id','source_end','dataset',target]].copy()
            d['prediction']=p;d['fold']=i;rows.append(d)
    pred=pd.concat(rows,ignore_index=True)
    name=source_mode+'__'+config['profile']+'__'+config['algorithm']
    dest=Path(out)/(target+'__'+name+'.csv.gz')
    pred.to_csv(dest,index=False,compression={'method':'gzip','mtime':0})
    return {'target':target,'name':name,'config':config,'source_mode':source_mode,
            'by_dataset':{str(s):metrics(g,target,g.prediction) for s,g in pred.groupby('dataset')},
            'predictions_sha256':sha(dest)}


def development(root, mode, profiles=None):
    prepared=root/'data/prepared/transfer-v1';out=root/'results/transfer-v1'/mode;out.mkdir(parents=True,exist_ok=True)
    data=pd.read_csv(prepared/'universe.csv.gz');data['dataset']='universe'
    split=json.loads((root/'experiments/split-v1.json').read_text())
    assert set(data.participant)<=set(split['development'])
    if mode=='pooled':
        mobile=pd.read_csv(prepared/'mobile_development.csv.gz')
        # Scale/direction review must explicitly permit each pooled target.
        mapping=json.loads((prepared/'mobile-audit.json').read_text())
        if not mapping['pooling_permitted']:raise ValueError('Unverified questionnaire scale; pooling refused')
        data=pd.concat([data,mobile],ignore_index=True)
    if mode=='latent':
        latent=pd.read_csv(prepared/'universe-latent.csv.gz')
        assert len(data)==len(latent)
        data=pd.concat([data,latent],axis=1)
    if mode=='native':
        native=pd.read_csv(prepared/'universe-native.csv.gz')
        assert len(data)==len(native)
        data=pd.concat([data,native],axis=1)
    frozen=out/'development-input.csv.gz';data.to_csv(frozen,index=False,compression={'method':'gzip','mtime':0})
    folds=grouped_folds(data)
    profiles=profiles or (['summary','summary_history'] if mode=='pooled' else ['latent'] if mode=='latent' else ['native'] if mode=='native' else ['all','all_history','summary','summary_history','ppg_eda'])
    configurations=[{'profile':p,'algorithm':a} for p in profiles for a in ALGORITHMS]
    configurations += [{'profile':profiles[0],'algorithm':a} for a in ['constant_mean','constant_median']]
    jobs=[]
    for target in TARGETS:
        source_modes=['local','pooled'] if mode=='pooled' and target in mapping['pooled_targets'] else ['local']
        for config in configurations:
            for source_mode in source_modes:jobs.append((str(frozen),str(out),target,config,folds,source_mode))
    protocol={'mode':mode,'folds':folds,'jobs':len(jobs),'configuration_count':len(configurations),
              'input_sha256':sha(frozen),'code_sha256':sha(Path(__file__)),
              'interpretation':'Development selection scores. No winner accuracy claim until held-out evaluation.',
              'profiles':profiles,'fit_windows_per_block_max':20}
    write_json(out/'protocol.json',protocol)
    completed=[];pending=[]
    for job in jobs:
        _,_,t,c,_,s=job
        cached=out/(t+'__'+s+'__'+c['profile']+'__'+c['algorithm']+'.metrics.json')
        if cached.exists():completed.append(json.loads(cached.read_text()))
        else:pending.append(job)
    with ProcessPoolExecutor(max_workers=6) as pool:
        futures={pool.submit(evaluate_job,job):job for job in pending}
        for future in as_completed(futures):
            result=future.result();completed.append(result)
            write_json(out/(result['target']+'__'+result['name']+'.metrics.json'),result)
            if len(completed)%10==0:print(json.dumps({'mode':mode,'completed':len(completed),'total':len(jobs)}),flush=True)
    write_json(out/'report.json',{'protocol':protocol,'results':completed})
    flat=[{'target':r['target'],'name':r['name'],'dataset':s,**{k:v for k,v in m.items() if not isinstance(v,(dict,list))}}
          for r in completed for s,m in r['by_dataset'].items()]
    table=pd.DataFrame(flat);table.to_csv(out/'comparison.csv',index=False)
    print(table.sort_values('mae').groupby(['dataset','target']).head(3)[['dataset','target','name','mae','within_tolerance','balanced_accuracy']].to_string(index=False),flush=True)
