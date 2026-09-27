#!/usr/bin/env python3
"""Secondary fixed-bin classification; does not replace the registered MVP gate."""
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import sys,json
import numpy as np
import pandas as pd
from sklearn.pipeline import make_pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import RobustScaler,FunctionTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.dummy import DummyClassifier
from sklearn.metrics import accuracy_score,balanced_accuracy_score,confusion_matrix,f1_score
from catboost import CatBoostClassifier
from threadpoolctl import threadpool_limits
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from neurasign_engine.transfer_training import columns,fit_weights,thin,grouped_folds,write_json,sha
from neurasign_engine.training import weights
from neurasign_engine.schema import TARGETS,SEED


def make(algorithm):
    if algorithm=='constant':m=DummyClassifier(strategy='most_frequent')
    elif algorithm=='cat':m=CatBoostClassifier(iterations=220,depth=4,learning_rate=.04,l2_leaf_reg=10,random_seed=SEED,thread_count=1,verbose=False,allow_writing_files=False)
    else:m=LogisticRegression(C=float(algorithm[3:]),max_iter=1000)
    return make_pipeline(SimpleImputer(strategy='median',add_indicator=True,keep_empty_features=True),RobustScaler(quantile_range=(10,90)),FunctionTransformer(np.tanh),m)


def fit_predict(train,valid,target,profile,algorithm,return_model=False):
    train=thin(train[train[target].notna()]);cols=columns(profile,train);model=make(algorithm)
    y=np.minimum((train[target].to_numpy(float)/(100/3)).astype(int),2);w=fit_weights(train)
    if algorithm!='constant':
        for label in np.unique(y):w[y==label]/=w[y==label].sum()
        w/=w.mean()
    with threadpool_limits(limits=1):
        model.fit(train[cols],y,**{model.steps[-1][0]+'__sample_weight':w})
        p=model.predict(valid[cols]).reshape(-1).astype(int)
    return (p,model,cols) if return_model else p


def metric(d):
    w=weights(d)
    return {'accuracy':float(accuracy_score(d.truth,d.prediction,sample_weight=w)),
      'balanced_accuracy':float(balanced_accuracy_score(d.truth,d.prediction,sample_weight=w)),
      'macro_f1':float(f1_score(d.truth,d.prediction,average='macro',labels=[0,1,2],sample_weight=w,zero_division=0)),
      'confusion_matrix':confusion_matrix(d.truth,d.prediction,labels=[0,1,2],sample_weight=w).tolist(),
      'people':int(d.participant.nunique()),'windows':len(d)}


def job(item):
    target,profile,algorithm,mode=item;data=pd.read_csv(ROOT/'results/transfer-v1/pooled/development-input.csv.gz')
    data=data[data[target].notna()];rows=[]
    for fold,ids in enumerate(grouped_folds(data)):
        train=data[~data.participant.isin(ids)];valid=data[data.participant.isin(ids)]
        for source,g in valid.groupby('dataset'):
            fit=train if mode=='pooled' else train[train.dataset==source]
            p=fit_predict(fit,g,target,profile,algorithm)
            d=g[['participant','session','unit_id','source_end','dataset',target]].copy()
            d['truth']=np.minimum((d[target]/(100/3)).astype(int),2);d['prediction']=p;d['fold']=fold;rows.append(d)
    d=pd.concat(rows,ignore_index=True);name=mode+'__'+profile+'__'+algorithm
    out=ROOT/'results/transfer-v1/coarse';path=out/(target+'__'+name+'.csv.gz');d.to_csv(path,index=False,compression={'method':'gzip','mtime':0})
    r={'target':target,'name':name,'config':{'profile':profile,'algorithm':algorithm},'source_mode':mode,
       'by_dataset':{s:metric(g) for s,g in d.groupby('dataset')},'predictions_sha256':sha(path)}
    write_json(out/(target+'__'+name+'.metrics.json'),r);return r


def main():
    out=ROOT/'results/transfer-v1/coarse';out.mkdir(parents=True,exist_ok=True)
    jobs=[(t,p,a,s) for t in TARGETS if t!='mental_effort' for p in ['summary','summary_history']
          for a in ['constant','log1','log10','cat'] for s in (['local'] if t=='perceived_performance' else ['local','pooled'])]
    write_json(out/'protocol.json',{'thresholds':[100/3,200/3],'target':'low/middle/high original questionnaire rating',
      'jobs':len(jobs),'code_sha256':sha(__file__),'interpretation':'Secondary development experiment. No replacement of registered continuous-rating gate; not instantaneous truth.'})
    results=[]
    with ProcessPoolExecutor(max_workers=4) as pool:
        futures=[pool.submit(job,j) for j in jobs]
        for future in as_completed(futures):
            results.append(future.result())
            if len(results)%10==0:print('coarse completed',len(results),'/',len(jobs),flush=True)
    write_json(out/'report.json',{'results':results})


if __name__=='__main__':main()
