#!/usr/bin/env python3
"""Nested person-CV on author-released wrist features: protocol probe only."""
from concurrent.futures import ProcessPoolExecutor
import io,json
from pathlib import Path
import sys
import numpy as np
import pandas as pd
from sklearn.pipeline import make_pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import RobustScaler,FunctionTransformer
from sklearn.svm import SVC
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import ExtraTreesClassifier
from sklearn.dummy import DummyClassifier
from sklearn.metrics import balanced_accuracy_score,accuracy_score,f1_score,confusion_matrix
from threadpoolctl import threadpool_limits
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from neurasign_engine.data import FeatureUnpickler
from neurasign_engine.schema import SEED
from neurasign_engine.transfer_training import sha,write_json
CONFIGS=['constant','logistic.1','logistic1','svc.1','svc1','svc10','extra']


def model(config):
    if config=='constant':m=DummyClassifier(strategy='most_frequent')
    elif config=='extra':m=ExtraTreesClassifier(n_estimators=100,min_samples_leaf=8,class_weight='balanced',random_state=SEED,n_jobs=1)
    elif config.startswith('svc'):m=SVC(C=float(config[3:]),class_weight='balanced')
    else:m=LogisticRegression(C=float(config[8:]),class_weight='balanced',max_iter=1000)
    return make_pipeline(SimpleImputer(strategy='median',keep_empty_features=True),RobustScaler(quantile_range=(10,90)),FunctionTransformer(np.tanh),m)


def outer(item):
    x,y,people,held=item;train=people!=held;test=people==held
    ids=np.random.default_rng(SEED+int(held)).permutation(np.unique(people[train]));folds=np.array_split(ids,3)
    scores=[]
    with threadpool_limits(limits=1):
        for c in CONFIGS:
            values=[]
            for ids in folds:
                fit=train&~np.isin(people,ids);val=train&np.isin(people,ids)
                m=model(c);m.fit(x[fit],y[fit]);values.append(balanced_accuracy_score(y[val],m.predict(x[val])))
            scores.append(float(np.mean(values)))
        chosen=CONFIGS[int(np.argmax(scores))];m=model(chosen);m.fit(x[train],y[train]);pred=m.predict(x[test])
        baseline=model('constant');baseline.fit(x[train],y[train]);base=baseline.predict(x[test])
    return {'person':int(held),'selected':chosen,'inner_scores':dict(zip(CONFIGS,scores)),
            'truth':y[test].tolist(),'prediction':pred.tolist(),'constant':base.tolist()}


def main():
    source=ROOT/'data/external/maus_public_features';out=ROOT/'results/transfer-v1/maus';out.mkdir(parents=True,exist_ok=True)
    manifest=json.loads((source/'manifest.json').read_text())
    for f in manifest['files']:
        # Manifest uses relative source paths, not remotely supplied executable objects.
        path=source/f.get('path',f.get('member',''))
        if path.is_file() and sha(path)!=f['sha256']:raise ValueError('Source checksum mismatch')
    def load(name):return np.asarray(FeatureUnpickler(io.BytesIO((source/'feature_data'/name).read_bytes())).load())
    x=load('feat_pix_ppg.pkl').astype(float);labels=load('label.pkl').astype(int);bounds=load('obj_position.pkl').astype(int)
    assert x.shape==(342,13) and len(labels)==len(x) and bounds[0]==0 and bounds[-1]==len(x)
    people=np.repeat(np.arange(len(bounds)-1),np.diff(bounds));y=(labels!=0).astype(int)
    write_json(out/'protocol.json',{'target':'source protocol class 0 vs {2,3}; not self-rated cognitive state',
      'outer':'leave one source subject out','inner':'three person folds','configs':CONFIGS,'people':len(bounds)-1,
      'features':13,'normalization':'training-fold robust scaling, no whole-subject future normalization',
      'source_manifest_sha256':sha(source/'manifest.json'),'code_sha256':sha(__file__)})
    with ProcessPoolExecutor(max_workers=4) as pool:folds=list(pool.map(outer,[(x,y,people,p) for p in np.unique(people)]))
    rows=[]
    for fold in folds:
        for i,(truth,pred,constant) in enumerate(zip(fold['truth'],fold['prediction'],fold['constant'])):
            rows.append({'participant':fold['person'],'window':i,'truth':truth,'prediction':pred,'constant':constant})
    d=pd.DataFrame(rows);d.to_csv(out/'predictions.csv',index=False)
    report={'folds':folds,'selected':{'accuracy':accuracy_score(d.truth,d.prediction),'balanced_accuracy':balanced_accuracy_score(d.truth,d.prediction),'macro_f1':f1_score(d.truth,d.prediction,average='macro'),'confusion_matrix':confusion_matrix(d.truth,d.prediction).tolist()},
      'constant':{'accuracy':accuracy_score(d.truth,d.constant),'balanced_accuracy':balanced_accuracy_score(d.truth,d.constant)},
      'people':len(bounds)-1,'windows':len(d),'mvp_gate_applicable':False,
      'limitations':['Protocol classes are not NASA-TLX ratings or live employee states.','Author feature preprocessing is offline; raw files are access-restricted.','No future subject-wide z-score normalization from the author classifier was reused.']}
    write_json(out/'report.json',report);print(json.dumps({k:v for k,v in report.items() if k!='folds'}),flush=True)


if __name__=='__main__':main()
