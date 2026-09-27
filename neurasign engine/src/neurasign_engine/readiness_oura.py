"""Offline reconstruction of observed Oura daily scores; no employee-readiness claim."""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
from .reference_benchmark import save, sha, split_people

SLEEP = ['duration','awake','light','rem','deep','total','onset_latency','midpoint_time','efficiency','restless',
         'hr_average','hr_lowest','rmssd','breath_average','temperature_delta']
CARDIAC = ['hr_average','hr_lowest','rmssd','breath_average','temperature_delta']
ACTIVITY = ['cal_active','steps','non_wear','rest','inactive','low','medium','high','average_met']
HISTORY = ['hr_average','hr_lowest','rmssd','total','temperature_delta']


def enrich_sleep(sleep, activity, heart):
    """Features available by this completed sleep; all history precedes it."""
    sleep = sleep.sort_values('bedtime_end_timestamp').copy()
    sleep['_end'] = pd.to_datetime(sleep.bedtime_end_timestamp, unit='ms', utc=True)
    numeric = sleep[SLEEP].apply(pd.to_numeric, errors='coerce')
    for col in ['hr_average','hr_lowest','rmssd','breath_average']:
        numeric[col] = numeric[col].where(numeric[col] > 0)
    rows=[]
    for position, (_, row) in enumerate(sleep.iterrows()):
        local_date = row['_end'].tz_convert('America/Los_Angeles').strftime('%Y-%m-%d')
        if local_date != row.date:
            continue
        f = numeric.iloc[position].to_dict()
        f['date']=row.date;f['feature_cutoff_ms']=float(row.bedtime_end_timestamp)
        for days in (7, 14):
            earlier = (sleep['_end'] < row['_end']) & (sleep['_end'] >= row['_end']-pd.Timedelta(days=days))
            for col in HISTORY:
                history = numeric.loc[earlier,col].dropna()
                mean = history.mean() if len(history)>=2 else np.nan
                f[f'{col}_past{days}_mean'] = mean
                f[f'{col}_past{days}_delta'] = f[col]-mean
        previous = activity[(activity.day_end_timestamp <= row.bedtime_end_timestamp) &
                            (activity.day_end_timestamp > row.bedtime_end_timestamp-48*3600*1000)]
        for col in ACTIVITY:
            f['previous_activity_'+col] = float(previous.sort_values('day_end_timestamp').iloc[-1][col]) if len(previous) else np.nan
        night = heart[(heart.timestamp >= row.bedtime_start_timestamp) & (heart.timestamp <= row.bedtime_end_timestamp)]
        for field in ('heart_rate','heart_rmssd'):
            values = pd.to_numeric(night[field], errors='coerce').where(lambda s:s>0).dropna()
            f[field+'_night_std'] = float(values.std()) if len(values)>=3 else np.nan
            f[field+'_night_range'] = float(values.quantile(.9)-values.quantile(.1)) if len(values)>=3 else np.nan
            midpoint=(row.bedtime_start_timestamp+row.bedtime_end_timestamp)/2
            a=night.loc[night.timestamp<midpoint,field];b=night.loc[night.timestamp>=midpoint,field]
            f[field+'_late_minus_early'] = float(b[b>0].mean()-a[a>0].mean()) if len(a) and len(b) else np.nan
        rows.append(f)
    return pd.DataFrame(rows)


def prepare(root):
    destination=root/'data/external/ifh_readiness'
    manifest=json.loads((destination/'manifest.json').read_text())
    for record in manifest['files']:
        assert sha(destination/'extracted'/record['member'])==record['sha256']
    frames=[];audit=[]
    # Follow the paper and author loader's 21-person cohort. Extra undocumented folders stay excluded.
    for identifier in range(1,22):
        person=f'par_{identifier}';p=destination/'extracted'/person/'oura'
        if not (p/'sleep.csv').exists():
            audit.append({'person':person,'status':'missing_sleep'});continue
        readiness=pd.read_csv(p/'readiness.csv',usecols=['date','score'])
        sleep=pd.read_csv(p/'sleep.csv');activity=pd.read_csv(p/'activity.csv');heart=pd.read_csv(p/'heart_rate.csv')
        assert not readiness.date.duplicated().any() and not sleep.date.duplicated().any()
        features=enrich_sleep(sleep,activity,heart)
        if features.empty:
            audit.append({'person':person,'status':'no_aligned_sleep'});continue
        frame=readiness.merge(features,on='date',validate='one_to_one')
        frame=frame[(frame.score>=1)&(frame.score<=100)].copy()
        frame=frame[frame[CARDIAC].notna().sum(axis=1)>=3].copy()
        audit.append({'person':person,'aligned_rows':len(frame),'status':'eligible' if len(frame)>=10 else 'fewer_than_10_days'})
        if len(frame)<10:continue
        frame['participant']=person;frame['target']=frame.pop('score');frames.append(frame)
    data=pd.concat(frames,ignore_index=True);data['row_id']=np.arange(len(data))
    assert not data[['participant','date']].duplicated().any()
    columns=[c for c in data if c not in {'participant','target','date','row_id','feature_cutoff_ms'}]
    assert not any('score' in col for col in columns)
    path=Path('data/prepared/readiness-oura-v1/days.csv.gz');(root/path).parent.mkdir(parents=True,exist_ok=True)
    data.to_csv(root/path,index=False,compression={'method':'gzip','mtime':0})
    profiles={'cardiac':CARDIAC,'sleep_physiology':SLEEP,
              'sleep_physiology_history_activity':columns}
    protocol={'experiment':16,'kind':'regression','target_definition':'Observed Oura proprietary daily readiness score 1–100; not independently measured employee readiness.',
              'split':split_people(data.participant.unique()),'profiles':profiles,
              'candidate_algorithms':'Ridge, RBF SVR, ExtraTrees, CatBoost, and top-three development ensemble; 10 models per profile.',
              'alignment':'Same exported calendar date only when sleep end timestamp is on that date in America/Los_Angeles. README prior-day wording contradicts 3985/3997 source rows; no alignment chosen by predictive score.',
              'cutoff':'End of completed sleep. Previous activity must end before cutoff, within48h. History uses strictly earlier sleep endings from7/14days. No prediction-time availability claim for vendor score.',
              'cohort':'Only par_1..par_21 as published and in author loader; undocumented par_22..24 excluded. At least10 aligned days,3/5 cardiac channels.',
              'excluded':'All vendor score columns and readiness contributors, target history, questionnaire data, demographics, identity and calendar date as inputs.',
              'evaluation':'Four development person folds select MAE; one final reserved-person evaluation. All metrics equal-weight people. Bootstrap people1000times.',
              'gate':'MAE<=8/100, >=20% lower than training-mean baseline MAE, R2>=0.25. Agreement±10 is not classification accuracy.',
              'source':'https://zenodo.org/records/10458511','license':'CC0-1.0','production_enabled':False,
              'code_dependencies':['src/neurasign_engine/readiness_oura.py']}
    protocol_path=Path('experiments/016-readiness-oura-protocol.json')
    if (root/protocol_path).exists():raise ValueError('Protocol exists; do not replace a frozen experiment')
    save(root/protocol_path,protocol)
    save(root/'results/readiness-oura-v1/audit.json',{'cohort':audit,'rows':len(data),'people':data.participant.nunique(),
                                                   'feature_availability':data[columns].notna().mean().to_dict(),
                                                   'manifest_sha256':sha(destination/'manifest.json')})
    return str(path),str(protocol_path)
