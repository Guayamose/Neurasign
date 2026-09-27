"""Observed FatigueSet physical/mental ratings from strictly preceding wrist data."""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
from .causal import Trace, FEATURES, extract_window
from .reference_benchmark import save, sha, split_people

BASE_FEATURES = FEATURES+['native_ibi_mean_ms','native_ibi_sdnn_ms','native_ibi_rmssd_ms']


def absolute_answer_start(label, submission_marker_ms):
    # Some session clocks pause/reset by180s. Anchor each response to its own UTC
    # submission marker; never extrapolate the experiment's initial clock offset.
    lag=float(label['fatigueSurveySubmissionTime'])-float(label['physicalFatigueAnswerTime'])
    if not 0<=lag<=120:raise ValueError('Unexpected questionnaire timing')
    return float(submission_marker_ms)/1000-lag


def load_signals(folder):
    traces={}
    for file,name,col,rate,unit in [('wrist_bvp.csv','bvp','bvp',64,'au'),('wrist_eda.csv','eda','eda',4,'uS'),
                                   ('wrist_skin_temperature.csv','temperature','temp',4,'degC'),('wrist_hr.csv','heart_rate','hr',1,'bpm')]:
        data=pd.read_csv(folder/file).sort_values('timestamp').drop_duplicates('timestamp')
        traces[name]=Trace(data.timestamp.to_numpy(float)/1000,data[col].to_numpy(float),float(rate),unit)
    data=pd.read_csv(folder/'wrist_acc.csv').sort_values('timestamp').drop_duplicates('timestamp')
    for c in ('x','y','z'):
        traces['acc_'+c]=Trace(data.timestamp.to_numpy(float)/1000,data['a'+c].to_numpy(float),32.,'g')
    ibi=pd.read_csv(folder/'wrist_ibi.csv').sort_values('timestamp').drop_duplicates('timestamp')
    return traces,ibi


def window_features(traces,ibi,end):
    result=extract_window(traces,end);f=result['features'].copy()
    beats=ibi[(ibi.timestamp>=1000*(end-60))&(ibi.timestamp<1000*end)]
    f.update({name:np.nan for name in BASE_FEATURES if name.startswith('native_')})
    valid=beats.duration.between(300,2000)
    if valid.sum()>=20 and f.get('motion_std',1)<.2:
        rr=beats.loc[valid,'duration'].to_numpy(float);f['native_ibi_mean_ms']=float(rr.mean());f['native_ibi_sdnn_ms']=float(rr.std(ddof=1))
        diff=beats.duration.diff().to_numpy(float)
        adjacent=valid.to_numpy() & np.r_[False,valid.to_numpy()[:-1]]
        adjacent &= beats.timestamp.diff().fillna(1e9).to_numpy() <= 2200
        if adjacent.sum()>=10:f['native_ibi_rmssd_ms']=float(np.sqrt(np.mean(diff[adjacent]**2)))
    return f,result['status']


def prepare(root):
    source=root/'data/external/fatigueset';manifest=json.loads((source/'manifest.json').read_text())
    for record in manifest['files']:assert sha(source/'extracted'/record['member'])==record['sha256']
    folder=source/'extracted/fatigueset';rows=[];audit=[]
    for label_file in sorted(folder.glob('*/*/exp_fatigue.csv')):
        session=label_file.parent;person=session.parent.name
        labels=pd.read_csv(label_file);markers=pd.read_csv(session/'exp_markers.csv')
        traces,ibi=load_signals(session)
        baseline_start=float(markers.loc[markers.eventMarker=='start_baseline','utcTime'].iloc[0])/1000
        baseline,_=window_features(traces,ibi,baseline_start+60)
        for number,event in enumerate(['end_baseline','end_activity','end_fatigue']):
            label=labels[labels.measurementNumber==number]
            marker=markers[markers.eventMarker==event]
            if len(label)!=1 or len(marker)!=1:
                audit.append({'participant':person,'session':session.name,'measurement':number,'status':'missing_reference_or_marker'});continue
            end=float(marker.utcTime.iloc[0])/1000
            submissions=markers.loc[markers.eventMarker=='submit_survey','utcTime'].to_numpy(float)
            if len(submissions)!=3:raise ValueError('Ambiguous questionnaire marker sequence')
            answer_start=absolute_answer_start(label.iloc[0],submissions[number])
            assert end<=answer_start+1.,'Feature endpoint follows fatigue answer'
            end=min(end,answer_start)
            f,status=window_features(traces,ibi,end)
            if sum(np.isfinite(list(f.values())))<15:
                audit.append({'participant':person,'session':session.name,'measurement':number,'status':'insufficient_wrist_features'});continue
            row={'participant':person,'unit_id':f'{person}-{session.name}-{number}','window_end':end,
                 'physical':float(label.physicalFatigueScore.iloc[0]),'mental':float(label.mentalFatigueScore.iloc[0])}
            assert 0<=row['physical']<=100 and 0<=row['mental']<=100
            row.update({'w60_'+k:v for k,v in f.items()})
            row.update({'delta_'+k:v-baseline[k] for k,v in f.items()})
            previous=[]
            for offset in (120,60,0):
                sample,_=window_features(traces,ibi,end-offset);previous.append(sample)
            for k in BASE_FEATURES:
                values=np.asarray([p[k] for p in previous],float)
                row['w180_'+k]=float(np.nanmean(values)) if np.isfinite(values).any() else np.nan
            rows.append(row);audit.append({'participant':person,'session':session.name,'measurement':number,'status':status})
    data=pd.DataFrame(rows);data['row_id']=np.arange(len(data))
    assert not data.unit_id.duplicated().any()
    split=split_people(data.participant.unique())
    cardiac=[c for c in BASE_FEATURES if c.startswith(('heart_rate','pulse_','native_','bvp_'))]
    autonomic=[c for c in BASE_FEATURES if not c.startswith(('motion','acc_'))]
    profiles={'cardiac_60':['w60_'+k for k in cardiac],
              'autonomic_60':['w60_'+k for k in autonomic],
              'all_60':['w60_'+k for k in BASE_FEATURES],
              'all_180':['w180_'+k for k in BASE_FEATURES],
              'all_60_baseline_delta':['w60_'+k for k in BASE_FEATURES]+['delta_'+k for k in BASE_FEATURES]}
    for target in ('physical','mental'):
        frame=data.drop(columns=['physical','mental']).copy();frame['rating']=data[target];frame['target']=(data[target]>=50).astype(int)
        path=root/f'data/prepared/fatigueset-{target}-v1/references.csv.gz';path.parent.mkdir(parents=True,exist_ok=True)
        frame.to_csv(path,index=False,compression={'method':'gzip','mtime':0})
        protocol={'experiment':15,'kind':'classification','target_definition':f'Self-reported {target} fatigue VAS>=50 versus<50; fixed research midpoint, not clinical cutoff.',
                  'split':split,'profiles':profiles,'reference':'One row per observed answer, not per repeated second; no neutral ratings excluded.',
                  'windows':'Trailing60s ending before answer at end_baseline/end_activity/end_fatigue;180s profile averages three preceding60s windows; baseline delta uses first60s resting recording, no baseline questionnaire input. Each answer is aligned to its own UTC submit_survey marker because relative experiment clock offsets change in some sessions.',
                  'evaluation':'Four grouped-development folds, ten classifiers per profile and top-three ensemble; fixed0.5 threshold. One heldout-person test after selection.',
                  'gate':'Balanced accuracy>=80%, both recalls>=70%. This is a research gate, not workplace validation.',
                  'source':'https://www.esense.io/datasets/fatigueset/','license':'Public author research release; explicit redistribution/commercial license not identified.',
                  'excluded':'EEG, chest/ear devices, task phase/time, identity, other questionnaire answers, demographics.',
                  'code_dependencies':['src/neurasign_engine/fatigueset.py','src/neurasign_engine/causal.py'],
                  'production_enabled':False}
        protocol_path=root/f'experiments/015-fatigueset-{target}-protocol.json'
        if protocol_path.exists():raise ValueError('Protocol exists; do not overwrite a frozen experiment')
        save(protocol_path,protocol)
    save(root/'results/fatigueset-acquisition-audit.json',{'references':len(data),'people':data.participant.nunique(),
          'source_rows':audit,'retained_by_target':{target:{'low':int((data[target]<50).sum()),'high':int((data[target]>=50).sum())} for target in ('physical','mental')},
          'manifest_sha256':sha(source/'manifest.json'),'feature_availability':data[[c for c in data if c.startswith('w60_')]].notna().mean().to_dict()})
    return {'references':len(data),'people':data.participant.nunique(),'split':split}
