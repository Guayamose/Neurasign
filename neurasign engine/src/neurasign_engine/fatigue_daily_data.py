"""Luo/De Luca 2020 daily fatigue: original PROs and wearable-only summaries."""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import subprocess
import numpy as np
import pandas as pd

DATASET = 'https://zenodo.org/records/4266157'
PAPER = 'https://pmc.ncbi.nlm.nih.gov/articles/PMC7768149/'
VITALS = ['BloodPerfusion','BloodPulseWave','GalvanicSkinResponse','HR','HRV','RESP','SkinTemperature']
ACTIVITY = ['ActivityCounts','EnergyExpenditure','Steps']
CHANNELS = VITALS+ACTIVITY
STATS = ['mean','std','p10','p50','p90','iqr']
BASE_FEATURES = [channel+'__'+stat for channel in CHANNELS for stat in STATS]
PROFILES = {'vitals':[f for f in BASE_FEATURES if f.split('__')[0] in VITALS],
            'all_wearable':list(BASE_FEATURES),
            'with_history':list(BASE_FEATURES)+[f+'__delta' for f in BASE_FEATURES]}
TARGETS = {'vas':{'range':[1,10],'tolerance':1.,'description':'Reported overall fatigue severity, 1–10 VAS'},
           'physical':{'range':[1,5],'tolerance':.5,'description':'Physical exhaustion frequency, Never=1 through Always=5'},
           'mental':{'range':[1,5],'tolerance':.5,'description':'Mental exhaustion frequency, Never=1 through Always=5'}}
FREQUENCIES = {'Never':1.,'Sometimes':2.,'Regularly':3.,'Often':4.,'Always':5.}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def acquire(root):
    folder = root/'data/external/fatigue_daily';folder.mkdir(parents=True,exist_ok=True)
    metadata = folder/'metadata.json'
    if not metadata.exists():
        subprocess.run(['curl','-fLs','--retry','2','https://zenodo.org/api/records/4266157','-o',str(metadata)],check=True)
    content = json.loads(metadata.read_text())
    def download(item):
        path = folder/item['key']
        if Path(item['key']).name != item['key']:
            raise ValueError('Unsafe source file path')
        if not path.exists():
            subprocess.run(['curl','-fLs','--retry','2',item['links']['self'],'-o',str(path)],check=True)
        algorithm,wanted = item['checksum'].split(':')
        if hashlib.new(algorithm,path.read_bytes()).hexdigest() != wanted:
            raise ValueError('Publisher checksum mismatch: '+item['key'])
        return item['key'],sha(path)
    with ThreadPoolExecutor(max_workers=3) as executor:
        hashes = dict(executor.map(download,content['files']))
    provenance = {'dataset':DATASET,'paper':PAPER,'license':content['metadata']['license'],
                  'sha256':hashes,'publisher_checksums_verified':len(hashes)}
    (folder/'provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')
    return folder,provenance


def labels(frame):
    """Latest daily response, excluding conflicting answers at identical times."""
    frame = frame.copy()
    frame['timestamp'] = pd.to_datetime(frame.DateTime,format='%d.%m.%y %H:%M',errors='raise')
    frame['participant'] = 'S'+frame.SubjectID.astype(str)
    frame['target'] = np.select([frame.PROquestion.str.startswith('Describe fatigue'),
        frame.PROquestion.str.startswith('Physically,'),frame.PROquestion.str.startswith('Mentally,')],
        ['vas','physical','mental'],default='excluded')
    frame = frame[frame.target!='excluded'].copy()
    frame['value'] = pd.to_numeric(frame.PROanswer_value,errors='coerce')
    ordinal = frame.target!='vas'
    frame.loc[ordinal,'value'] = frame.loc[ordinal,'PROanswer_choice'].map(FREQUENCIES)
    rows = [];conflicts = 0
    for (person,timestamp,target),group in frame.groupby(['participant','timestamp','target']):
        available = group.value.dropna().unique()
        if len(available) != 1:
            conflicts += int(len(available)>1)
            continue
        value = float(available[0]);low,high = TARGETS[target]['range']
        if not low <= value <= high:
            raise ValueError('Fatigue questionnaire value outside original scale')
        rows.append({'participant':person,'timestamp':timestamp,'day':timestamp.normalize(),'target':target,'value':value})
    answers = pd.DataFrame(rows).sort_values('timestamp').drop_duplicates(['participant','day','target'],keep='last')
    wide = answers.pivot(index=['participant','day'],columns='target',values='value').reset_index()
    return wide,{'conflicting_person_time_target_answers_excluded':conflicts,
                 'source_pro_rows':len(frame),'label_days':len(wide),'label_people':wide.participant.nunique()}


def aggregate_day(frame):
    """Use finite sensor observations only, no cross-day interpolation."""
    result = {}
    for channel in CHANNELS:
        values = pd.to_numeric(frame[channel],errors='coerce').replace([np.inf,-np.inf],np.nan).dropna().to_numpy()
        if len(values) < 30:
            current = [np.nan]*len(STATS)
        else:
            current = [float(values.mean()),float(values.std()),float(np.quantile(values,.1)),float(np.median(values)),
                       float(np.quantile(values,.9)),float(np.quantile(values,.75)-np.quantile(values,.25))]
        result.update({channel+'__'+stat:value for stat,value in zip(STATS,current)})
    return result


def history_features(days):
    """Previous seven *calendar* days only; neither current nor later values enter baseline."""
    days = days.sort_values(['participant','day']).copy()
    for name in BASE_FEATURES:
        days[name+'__delta'] = np.nan
    for _,person in days.groupby('participant'):
        indexed = person.set_index('day')
        reference = indexed[BASE_FEATURES].rolling('7D',closed='left',min_periods=2).median()
        delta = indexed[BASE_FEATURES]-reference
        days.loc[person.index,[f+'__delta' for f in BASE_FEATURES]] = delta.to_numpy()
    return days


def prepare(root):
    folder,provenance = acquire(root)
    outcomes,audit = labels(pd.read_csv(folder/'fatiguePROs.csv'))
    rows = [];sensor_audit = [];duplicates = 0
    for path in sorted(folder.glob('subjectID_*.csv')):
        person = 'S'+path.stem.split('_')[-1]
        minutes = pd.read_csv(path).rename(columns={'SkinTemperature.Value':'SkinTemperature'})
        minutes['time'] = pd.to_datetime(minutes.Timestamp,format='%d.%m.%y %H:%M',errors='raise')
        duplicates += int(minutes.time.duplicated().sum())
        # Multiple rows for the same minute contribute once; no oversampling of repeated minutes.
        minutes = minutes.groupby('time',as_index=False)[CHANNELS].mean()
        minutes['day'] = minutes.time.dt.normalize()
        for day,block in minutes.groupby('day'):
            observed = block[['HR','ActivityCounts']].notna().any(axis=1).sum()
            accepted = observed >= 288
            sensor_audit.append({'participant':person,'day':str(day.date()),'minutes_with_hr_or_activity':int(observed),'accepted':bool(accepted)})
            if accepted:
                rows.append({'participant':person,'day':day,**aggregate_day(block)})
    daily = history_features(pd.DataFrame(rows));tracks = []
    for track,lag in [('previous_day',1),('same_day_retrospective',0)]:
        features = daily.copy();features['feature_day'] = features.day
        features.day = features.day+pd.Timedelta(days=lag)
        joined = outcomes.merge(features,on=['participant','day'],validate='one_to_one')
        joined['track'] = track;joined['unit_id'] = joined.participant+'_'+joined.day.astype(str)
        tracks.append(joined)
    frame = pd.concat(tracks,ignore_index=True);frame['row_id'] = np.arange(len(frame))
    out = root/'data/prepared/fatigue-daily-v1';out.mkdir(parents=True,exist_ok=True)
    frame.to_csv(out/'days.csv.gz',index=False,compression={'method':'gzip','mtime':0})
    audit.update({'provenance':provenance,'sensor_day_inventory':sensor_audit,'duplicated_sensor_minutes_collapsed':duplicates,
                  'prepared_sha256':sha(out/'days.csv.gz'),'tracks':{name:{'rows':len(f),'people':int(f.participant.nunique()),
                   'labels':{target:int(f[target].notna().sum()) for target in TARGETS}} for name,f in frame.groupby('track')},
                  'timezone_limitation':'PRO has UTC/CET/CEST, sensor timezone undocumented. Primary track uses previous calendar day; same-day track is retrospective only.',
                  'device':'Everion upper-arm multimodal wearable, not wrist E4/WHOOP/Garmin validation',
                  'source_alias':'subjectID_4 SkinTemperature.Value mapped to SkinTemperature; no unit conversion',
                  'data_quality':'Require >=288 minutes/day with HR or activity; each feature channel requires >=30 finite minutes. No across-day imputation.'})
    (out/'audit.json').write_text(json.dumps(audit,indent=2)+'\n')
    return frame,audit
