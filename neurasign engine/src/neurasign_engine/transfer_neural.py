"""Small masked multi-output networks; all supervised fitting stays inside folds."""
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import numpy as np
import pandas as pd
import torch
from torch import nn
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import RobustScaler
from .schema import TARGETS,SEED
from .transfer_training import thin,fit_weights,columns,grouped_folds,metrics,write_json,sha


def fit_predict(train,valid,profile,loss_name,return_model=False):
    torch.set_num_threads(1);torch.manual_seed(SEED)
    train=thin(train);cols=columns(profile,train);targets=list(TARGETS)
    imputer=SimpleImputer(strategy='median',keep_empty_features=True);scaler=RobustScaler(quantile_range=(10,90))
    scaler.fit(imputer.fit_transform(train[cols]))
    def x(frame):
        mask=np.isfinite(frame[cols].to_numpy(float)).astype('float32')
        values=np.tanh(scaler.transform(imputer.transform(frame[cols]))).astype('float32')
        return torch.tensor(np.c_[values,mask])
    inputs=x(train);test=x(valid);ys=[];ws=[]
    for t in targets:
        low,high=TARGETS[t]['range'];y=(train[t].to_numpy(float)-low)/(high-low);known=np.isfinite(y)
        w=np.zeros(len(train));w[known]=fit_weights(train[known]) if known.any() else []
        if w.sum():w*=len(train)/w.sum()
        ys.append(np.nan_to_num(y));ws.append(w)
    y=torch.tensor(np.array(ys).T,dtype=torch.float32);w=torch.tensor(np.array(ws).T,dtype=torch.float32)
    model=nn.Sequential(nn.Linear(inputs.shape[1],64),nn.GELU(),nn.Dropout(.15),nn.Linear(64,32),nn.GELU(),nn.Linear(32,len(targets)),nn.Sigmoid())
    optimizer=torch.optim.AdamW(model.parameters(),lr=.001,weight_decay=.01)
    rng=np.random.default_rng(SEED)
    for epoch in range(80):
        model.train();order=rng.permutation(len(train))
        for ids in np.array_split(order,max(1,len(train)//256)):
            pred=model(inputs[ids]);error=pred-y[ids]
            loss=((error.abs() if loss_name=='absolute' else error.square())*w[ids]).mean()
            optimizer.zero_grad();loss.backward();nn.utils.clip_grad_norm_(model.parameters(),5);optimizer.step()
    model.eval()
    with torch.no_grad():pred=model(test).numpy()
    for i,t in enumerate(targets):
        low,high=TARGETS[t]['range'];pred[:,i]=pred[:,i]*(high-low)+low
    if return_model:return pred,{'state_dict':model.state_dict(),'columns':cols,'imputer':imputer,'scaler':scaler,'targets':targets,'training_ids':sorted(train.participant.unique()),'profile':profile,'loss':loss_name}
    return pred


def job(item):
    path,out,profile,loss=item;data=pd.read_csv(path);rows=[];folds=grouped_folds(data)
    name='multitask__'+profile+'__'+loss
    for fold,ids in enumerate(folds):
        train=data[~data.participant.isin(ids)];valid=data[data.participant.isin(ids)]
        p=fit_predict(train,valid,profile,loss)
        d=valid[['participant','session','unit_id','source_end','dataset',*TARGETS]].copy()
        for j,t in enumerate(TARGETS):d[t+'__prediction']=p[:,j]
        d['fold']=fold;rows.append(d)
    all_predictions=pd.concat(rows,ignore_index=True);results=[]
    for t in TARGETS:
        d=all_predictions[all_predictions[t].notna()]
        if not len(d):continue
        d=d[['participant','session','unit_id','source_end','dataset',t,t+'__prediction','fold']].rename(columns={t+'__prediction':'prediction'})
        dest=Path(out)/(t+'__'+name+'.csv.gz');d.to_csv(dest,index=False,compression={'method':'gzip','mtime':0})
        result={'target':t,'name':name,'config':{'profile':profile,'algorithm':'multitask','loss':loss},'source_mode':'local',
          'by_dataset':{s:metrics(g,t,g.prediction) for s,g in d.groupby('dataset')},'predictions_sha256':sha(dest)}
        write_json(dest.with_name(t+'__'+name+'.metrics.json'),result);results.append(result)
    return results


def run(root):
    prepared=root/'data/prepared/transfer-v1';out=root/'results/transfer-v1/multitask';out.mkdir(parents=True,exist_ok=True)
    uni=pd.read_csv(prepared/'universe.csv.gz');uni['dataset']='universe'
    latent=pd.read_csv(prepared/'universe-latent.csv.gz');uni=pd.concat([uni,latent],axis=1)
    mobile=pd.read_csv(prepared/'mobile_development.csv.gz')
    jobs=[]
    for name,data,profiles in [('universe',uni,['all','all_history','latent']),('mobile',mobile,['all','summary_history'])]:
        path=out/(name+'-development-input.csv.gz');data.to_csv(path,index=False,compression={'method':'gzip','mtime':0})
        destination=out/name;destination.mkdir(exist_ok=True)
        for p in profiles:
            for loss in ['squared','absolute']:jobs.append((str(path),str(destination),p,loss))
    results=[]
    with ProcessPoolExecutor(max_workers=3) as pool:
        futures=[pool.submit(job,item) for item in jobs]
        for f in as_completed(futures):
            results.extend(f.result());print('multitask completed',len(results),'target comparisons',flush=True)
    write_json(out/'report.json',{'results':results,'epochs':80,'seed':SEED,'code_sha256':sha(__file__),
       'interpretation':'Development selection scores; six jointly learned outputs with masks on unavailable targets. Mobile and UNIVERSE trained separately.'})
