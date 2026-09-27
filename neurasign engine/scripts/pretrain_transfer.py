#!/usr/bin/env python3
"""Masked feature autoencoder, trained on external unlabeled wrist signals only."""
from pathlib import Path
import sys
import json
import joblib
import numpy as np
import pandas as pd
import torch
from torch import nn
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import RobustScaler

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from neurasign_engine.transfer_features import FEATURES
from neurasign_engine.transfer_training import write_json,sha,fit_weights
from neurasign_engine.schema import SEED


def main():
    torch.set_num_threads(2);torch.manual_seed(SEED);rng=np.random.default_rng(SEED)
    source=ROOT/'data/prepared/transfer-v1';out=ROOT/'results/transfer-v1/pretraining';out.mkdir(parents=True,exist_ok=True)
    frames=[pd.read_csv(source/(d+'.csv.gz')) for d in ['clacir','cogwear']]
    d=pd.concat(frames,ignore_index=True)
    # Person/recording-group validation checks reconstruction, not mental states.
    ids=rng.permutation(sorted(d.participant.unique()));check=set(ids[:max(1,len(ids)//5)])
    train=d[~d.participant.isin(check)];valid=d[d.participant.isin(check)]
    imputer=SimpleImputer(strategy='median',keep_empty_features=True);scaler=RobustScaler(quantile_range=(10,90))
    scaler.fit(imputer.fit_transform(train[FEATURES]))
    def tensor(frame):
        mask=np.isfinite(frame[FEATURES].to_numpy()).astype('float32')
        x=np.tanh(scaler.transform(imputer.transform(frame[FEATURES]))).astype('float32')
        return torch.tensor(x*mask),torch.tensor(mask)
    x,m=tensor(train);vx,vm=tensor(valid);w=fit_weights(train);w=w/w.sum()
    encoder=nn.Sequential(nn.Linear(56,64),nn.GELU(),nn.Linear(64,32),nn.GELU(),nn.Linear(32,16))
    decoder=nn.Sequential(nn.Linear(16,32),nn.GELU(),nn.Linear(32,28),nn.Tanh())
    optimizer=torch.optim.AdamW(list(encoder.parameters())+list(decoder.parameters()),lr=.001,weight_decay=.001)
    history=[]
    for epoch in range(100):
        encoder.train();decoder.train();losses=[]
        order=rng.choice(len(train),size=len(train),replace=True,p=w)
        for indices in np.array_split(order,max(1,len(train)//256)):
            a,b=x[indices],m[indices];keep=(torch.rand_like(b)>.2).float()*b
            z=encoder(torch.cat([a*keep,keep],dim=1));pred=decoder(z)
            loss=(((pred-a)**2)*b).sum()/b.sum().clamp(min=1)
            optimizer.zero_grad();loss.backward();optimizer.step();losses.append(float(loss.detach()))
        if epoch%10==0 or epoch==99:
            encoder.eval();decoder.eval()
            with torch.no_grad():
                pred=decoder(encoder(torch.cat([vx,vm],dim=1)))
                val=float((((pred-vx)**2)*vm).sum()/vm.sum().clamp(min=1))
            history.append({'epoch':epoch+1,'training_masked_mse':float(np.mean(losses)),'validation_reconstruction_mse':val})
    encoder.eval();decoder.eval()
    modelpath=ROOT/'models/transfer-feature-encoder.pt';modelpath.parent.mkdir(exist_ok=True)
    torch.save({'encoder':encoder.state_dict(),'decoder':decoder.state_dict(),'features':FEATURES},modelpath)
    joblib.dump({'imputer':imputer,'scaler':scaler,'features':FEATURES},ROOT/'models/transfer-feature-scaler.joblib')
    for dataset in ['universe','mobile_development','mobile_test']:
        path=source/(dataset+'.csv.gz')
        if not path.exists():continue
        # Inference only; no statistic fitting or labels from either test set.
        frame=pd.read_csv(path,usecols=FEATURES);a,b=tensor(frame)
        with torch.no_grad():latent=encoder(torch.cat([a,b],dim=1)).numpy()
        pd.DataFrame(latent,columns=[f'latent_{i}' for i in range(16)]).to_csv(source/(dataset+'-latent.csv.gz'),index=False,compression={'method':'gzip','mtime':0})
    write_json(out/'report.json',{'features':FEATURES,'train_recording_ids':sorted(train.participant.unique()),
       'validation_recording_ids':sorted(check),'training_windows':len(train),'validation_windows':len(valid),
       'source_windows':d.groupby('dataset').size().to_dict(),'source_hours_nonoverlap':len(d)/60,
       'source_hashes':{n:sha(source/(n+'.csv.gz')) for n in ['clacir','cogwear']},
       'epochs_fixed':100,'history':history,'model_sha256':sha(modelpath),'code_sha256':sha(__file__),
       'limitations':['Feature-level representation learning; not a raw-waveform foundation model.',
                      'Reconstruction accuracy does not establish target-prediction accuracy.',
                      'CLACIR IDs are recording groups, not a verified count of independent people.']})
    print(json.dumps({'pretraining':'complete','windows':len(d),'hours':len(d)/60,'final':history[-1]}),flush=True)


if __name__=='__main__':main()
