#!/usr/bin/env python3
"""Freeze on development evidence, then score the reserved source IDs once."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import sys,time
import joblib
import numpy as np
import pandas as pd
import torch
from torch import nn
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from neurasign_engine.schema import TARGETS,SEED
from neurasign_engine.transfer_training import fit_predict,metrics,sha,write_json
from neurasign_engine.transfer_neural import fit_predict as fit_neural
from neurasign_engine.training import weights
from train_coarse_transfer import fit_predict as fit_coarse,metric as coarse_metric


def collect():
    base=ROOT/'results/transfer-v1';rows=[]
    for mode in ['universe','pooled','latent','native','multitask','coarse','maus']:
        if not (base/mode/'report.json').exists():raise ValueError('Unfinished experiment: '+mode)
    for mode in ['universe','pooled','latent','native','multitask/universe','multitask/mobile','coarse']:
        for path in sorted((base/mode).glob('*.metrics.json')):
            r=json.loads(path.read_text());r['experiment']=mode;r['metrics_file']=str(path.relative_to(ROOT))
            rows.append(r)
    return rows


def compact(record,dataset):
    r={k:record[k] for k in ['target','name','config','source_mode','experiment','metrics_file']}
    r['development_metrics']={k:v for k,v in record['by_dataset'][dataset].items() if not isinstance(v,(dict,list))}
    return r


def freeze():
    path=ROOT/'experiments/008-final-selection.json'
    if path.exists():
        print('Selection already frozen; no changes made.');return
    records=collect();chosen={};dev_summary={}
    for dataset in ['universe','mobile']:
        dev_summary[dataset]={}
        for target in TARGETS:
            options=[r for r in records if r['target']==target and dataset in r['by_dataset'] and r['experiment']!='coarse']
            if not options:continue
            constants=[r for r in options if r['config']['algorithm'].startswith('constant')]
            learned=[r for r in options if not r['config']['algorithm'].startswith('constant')]
            best=min(learned,key=lambda r:(r['by_dataset'][dataset]['mae'],r['experiment'],r['name']))
            baseline=min(constants,key=lambda r:(r['by_dataset'][dataset]['mae'],r['experiment'],r['name']))
            dev_summary[dataset][target]={'learned':compact(best,dataset),'constant':compact(baseline,dataset),
                                        'candidates':len(options)}
            if dataset=='mobile':
                classifiers=[r for r in records if r['target']==target and r['experiment']=='coarse' and r['config']['algorithm']!='constant']
                classifier=max(classifiers,key=lambda r:(r['by_dataset'][dataset]['balanced_accuracy'],r['name']))
                chosen[target]={'learned':compact(best,dataset),'constant':compact(baseline,dataset),'coarse':compact(classifier,dataset)}
    prepared=ROOT/'data/prepared/transfer-v1'
    split=json.loads((ROOT/'experiments/008-mobile-split.json').read_text())
    document={'frozen_utc':datetime.now(timezone.utc).isoformat(),'seed':SEED,'selection':'Minimum person-macro development MAE; coarse maximum development balanced accuracy. No held-out scores used.',
      'targets':chosen,'development_summary':dev_summary,'reserved_mobile_codes':split['test'],
      'known_missing_label_file':'vbd5b: reserved but cannot be scored; no replacement after development inspection.',
      'selection_records':len(records),'data_hashes':{n:sha(prepared/(n+'.csv.gz')) for n in ['universe','mobile_development','mobile_test']},
      'code_hashes':{str(p.relative_to(ROOT)):sha(p) for p in sorted((ROOT/'src/neurasign_engine').glob('*.py'))}|
                    {str(p.relative_to(ROOT)):sha(p) for p in sorted((ROOT/'scripts').glob('*transfer*.py'))},
      'gate':json.loads((ROOT/'experiments/008-transfer-protocol.json').read_text())['mvp_research_gate'],
      'claim':'Research candidate selection. Development winner scores are optimistic after search. No product runtime enabled.'}
    write_json(path,document)
    out=ROOT/'results/transfer-v1/final';out.mkdir(parents=True,exist_ok=True)
    flat=[]
    for r in records:
        for d,m in r['by_dataset'].items():
            flat.append({'experiment':r['experiment'],'dataset':d,'target':r['target'],'name':r['name'],
                         **{k:v for k,v in m.items() if not isinstance(v,(dict,list))}})
    pd.DataFrame(flat).to_csv(out/'development-comparison.csv',index=False)
    print(json.dumps({'selection_frozen':True,'records':len(records),'targets':{t:{k:v['experiment']+'/'+v['name'] for k,v in r.items()} for t,r in chosen.items()}}),flush=True)


def prepare_models():
    frozen=json.loads((ROOT/'experiments/008-final-selection.json').read_text());base=ROOT/'data/prepared/transfer-v1'
    out=ROOT/'models/transfer-v1';out.mkdir(parents=True,exist_ok=True)
    if (out/'manifest.json').exists():
        print('Frozen model artifacts already exist.');return
    for n in ['universe','mobile_development']:
        assert sha(base/(n+'.csv.gz'))==frozen['data_hashes'][n]
    uni=pd.read_csv(base/'universe.csv.gz');uni['dataset']='universe'
    mobile=pd.read_csv(base/'mobile_development.csv.gz');data=pd.concat([uni,mobile],ignore_index=True)
    artifact_rows=[]
    for target,choices in frozen['targets'].items():
        for kind,choice in choices.items():
            train=data if choice['source_mode']=='pooled' else mobile
            valid=train.iloc[:1].copy();config=choice['config']
            if kind=='coarse':
                expected,model,cols=fit_coarse(train,valid,target,config['profile'],config['algorithm'],return_model=True)
                artifact={'kind':'coarse','model':model,'columns':cols,'target':target,'training_ids':sorted(train.participant.unique())}
            elif config['algorithm']=='multitask':
                expected,artifact=fit_neural(train,valid,config['profile'],config['loss'],return_model=True)
                artifact['kind']='neural';artifact['target']=target;expected=expected[:,list(TARGETS).index(target)]
            else:
                expected,artifact=fit_predict(train,valid,target,config,return_model=True);artifact['kind']='regression'
            artifact['production_enabled']=False;artifact['reason']='Research model; acceptance requires independent validation.'
            file=out/(target+'__'+kind+'.joblib');joblib.dump(artifact,file)
            actual=predict(joblib.load(file),valid)
            np.testing.assert_allclose(actual,expected,atol=1e-5)
            artifact_rows.append({'target':target,'kind':kind,'path':str(file.relative_to(ROOT)),'sha256':sha(file)})
        print('fitted frozen research artifacts:',target,flush=True)
    write_json(out/'manifest.json',{'selection_sha256':sha(ROOT/'experiments/008-final-selection.json'),'files':artifact_rows,
                                  'created_utc':datetime.now(timezone.utc).isoformat(),'test_labels_read':False})


def predict(artifact,frame):
    cols=artifact['columns']
    if artifact['kind']=='coarse':return artifact['model'].predict(frame[cols]).reshape(-1).astype(int)
    if artifact['kind']=='regression':
        low,high=artifact['range'];return np.clip(artifact['model'].predict(frame[cols]),0,1)*(high-low)+low
    torch.set_num_threads(1)
    mask=np.isfinite(frame[cols].to_numpy(float)).astype('float32')
    x=np.tanh(artifact['scaler'].transform(artifact['imputer'].transform(frame[cols]))).astype('float32')
    model=nn.Sequential(nn.Linear(2*len(cols),64),nn.GELU(),nn.Dropout(.15),nn.Linear(64,32),nn.GELU(),nn.Linear(32,len(TARGETS)),nn.Sigmoid())
    model.load_state_dict(artifact['state_dict']);model.eval()
    with torch.no_grad():values=model(torch.tensor(np.c_[x,mask])).numpy()[:,list(TARGETS).index(artifact['target'])]
    low,high=TARGETS[artifact['target']]['range'];return values*(high-low)+low


def paired_bootstrap(frame,target,learned,constant):
    d=frame[['participant','unit_id']].copy();truth=frame[target].to_numpy(float)
    d['change']=abs(truth-np.asarray(constant))-abs(truth-np.asarray(learned))
    person=d.groupby(['participant','unit_id']).change.mean().groupby('participant').mean().to_numpy()
    draws=np.random.default_rng(SEED).choice(person,(10000,len(person)),replace=True).mean(axis=1)
    return {'mean_mae_reduction':float(person.mean()),'paired_person_bootstrap_95_ci':np.quantile(draws,[.025,.975]).tolist(),
            'resamples':10000,'resampling_unit':'held-out user code; not individual overlapping windows'}


def evaluate():
    dest=ROOT/'results/transfer-v1/final';dest.mkdir(parents=True,exist_ok=True)
    if (dest/'test-report.json').exists():
        print('Held-out evaluation already recorded. Use verify_transfer.py to audit saved predictions.');return
    frozenpath=ROOT/'experiments/008-final-selection.json';frozen=json.loads(frozenpath.read_text())
    manifest=json.loads((ROOT/'models/transfer-v1/manifest.json').read_text())
    assert manifest['selection_sha256']==sha(frozenpath)
    testpath=ROOT/'data/prepared/transfer-v1/mobile_test.csv.gz';assert sha(testpath)==frozen['data_hashes']['mobile_test']
    test=pd.read_csv(testpath);assert set(test.participant)=={'mobile:'+p for p in frozen['reserved_mobile_codes'] if p!='vbd5b'}
    audit=json.loads((ROOT/'data/prepared/transfer-v1/mobile-audit.json').read_text())
    considered=sum(r.get('windows_considered',0) for r in audit['recordings'] if r['group']=='test')
    coverage=len(test)/considered;results={}
    for target in frozen['targets']:
        rows=test[test[target].notna()];predictions={};latency={}
        for kind in ['learned','constant','coarse']:
            file=next(f for f in manifest['files'] if f['target']==target and f['kind']==kind)
            assert sha(ROOT/file['path'])==file['sha256'];artifact=joblib.load(ROOT/file['path'])
            assert not set(artifact['training_ids'])&set(rows.participant)
            predictions[kind]=predict(artifact,rows)
            if kind=='learned':
                times=[]
                for i in np.linspace(0,len(rows)-1,30).astype(int):
                    start=time.perf_counter();predict(artifact,rows.iloc[[i]]);times.append((time.perf_counter()-start)*1000)
                latency={'median_ms':float(np.median(times)),'p95_ms':float(np.quantile(times,.95)),
                         'scope':'One already-extracted feature window, local CPU; excludes radio, server and feature extraction.'}
        output=rows[['participant','session','unit_id','source_end',target]].copy()
        for k,v in predictions.items():output[k]=v
        path=dest/(target+'-test-predictions.csv.gz');output.to_csv(path,index=False,compression={'method':'gzip','mtime':0})
        learned=metrics(rows,target,predictions['learned']);constant=metrics(rows,target,predictions['constant'])
        comparison=paired_bootstrap(rows,target,predictions['learned'],predictions['constant'])
        coarse=rows.copy();coarse['truth']=np.minimum((rows[target]/(100/3)).astype(int),2);coarse['prediction']=predictions['coarse']
        reduction=1-learned['mae']/constant['mae']
        gate={'relative_mae_reduction_at_least_15_percent':reduction>=.15,
              'paired_95_ci_improvement_lower_above_zero':comparison['paired_person_bootstrap_95_ci'][0]>0,
              'rating_model_three_level_balanced_accuracy_at_least_60_percent':learned['balanced_accuracy']>=.6,
              'within_10_points_at_least_60_percent':learned['within_tolerance']>=.6,
              'coverage_at_least_80_percent':coverage>=.8,'heldout_people_at_least_10':rows.participant.nunique()>=10}
        results[target]={'learned':learned,'constant':constant,'coarse_classifier':coarse_metric(coarse),
                        'relative_mae_reduction':reduction,'paired_comparison':comparison,'gate':gate,'passes_gate':all(gate.values()),
                        'latency':latency,'predictions_sha256':sha(path)}
    report={'evaluated_utc':datetime.now(timezone.utc).isoformat(),'selection_sha256':sha(frozenpath),
      'models_manifest_sha256':sha(ROOT/'models/transfer-v1/manifest.json'),'test_table_sha256':sha(testpath),
      'targets':results,'reserved_codes':10,'scored_codes':int(test.participant.nunique()),'blocks':int(test.unit_id.nunique()),
      'windows':len(test),'eligible_signal_coverage':coverage,'any_head_passes':any(r['passes_gate'] for r in results.values()),
      'production_enabled':False,'limitations':['One reserved code has no released questionnaire; nine can be scored.',
      'This is an internal study holdout on a second wrist device, not validation in workplaces or arbitrary wearables.',
      'Questionnaire answers refer to two-to-three-minute tasks, not each second.',
      'Mobile export/publication participant-count discrepancy and cross-study scale equivalence remain unresolved.',
      'Bootstrap intervals are descriptive per output and not adjusted for multiple comparisons.']}
    write_json(dest/'test-report.json',report)
    print(json.dumps({'heldout_codes':report['scored_codes'],'any_head_passes':report['any_head_passes'],
      'targets':{t:{'mae':r['learned']['mae'],'constant_mae':r['constant']['mae'],'within_10_percent':100*r['learned']['within_tolerance'],'coarse_balanced_percent':100*r['coarse_classifier']['balanced_accuracy']} for t,r in results.items()}},indent=2),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['freeze','fit','evaluate']);args=parser.parse_args()
    {'freeze':freeze,'fit':prepare_models,'evaluate':evaluate}[args.action]()
