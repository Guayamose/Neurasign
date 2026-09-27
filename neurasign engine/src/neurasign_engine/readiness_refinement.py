"""Nested, development-only refinement of an observed daily vendor readiness score.

All enhanced features use physiological/sleep/activity measurements at or before
completed sleep. No vendor score, contributor, questionnaire or target history.
"""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
from . import readiness_oura as old
from .reference_benchmark import save, sha

NAME = 'readiness-refinement-v1'
SEED = 20260927
HISTORY = ['hr_average', 'hr_lowest', 'rmssd', 'breath_average', 'temperature_delta',
           'total', 'deep', 'rem', 'efficiency', 'onset_latency', 'restless']
ACTIVITY = ['steps', 'cal_active', 'average_met', 'inactive', 'low', 'medium', 'high']
SLEEP_COLUMNS = list(dict.fromkeys(old.SLEEP + ['date', 'bedtime_start_timestamp',
    'bedtime_end_timestamp', 'bedtime_start_midnight_delta', 'bedtime_end_midnight_delta']))


def ratio(a, b):
    return a / np.maximum(b, 1e-6)


def enhance(sleep, activity, heart):
    """Pure single-person transformation; later measurements cannot alter a row."""
    sleep = sleep[SLEEP_COLUMNS].copy().sort_values('bedtime_end_timestamp').reset_index(drop=True)
    endings = pd.to_datetime(sleep.bedtime_end_timestamp, unit='ms', utc=True)
    numeric = sleep[old.SLEEP].apply(pd.to_numeric, errors='coerce')
    for name in old.CARDIAC[:-1]:
        numeric[name] = numeric[name].where(numeric[name] > 0)
    f = pd.DataFrame(index=sleep.index)
    for name in ['awake', 'light', 'rem', 'deep', 'total']:
        f[name+'_fraction'] = ratio(numeric[name], numeric.duration)
    f['log_rmssd'] = np.log1p(numeric.rmssd.clip(lower=0))
    f['heart_average_above_lowest'] = numeric.hr_average - numeric.hr_lowest
    f['heart_average_lowest_ratio'] = ratio(numeric.hr_average, numeric.hr_lowest)
    f['sleep_below_eight_hours'] = np.maximum(0, 8*3600-numeric.total)/3600
    f['bedtime_duration_hours'] = numeric.duration/3600
    for column in ['bedtime_start_midnight_delta', 'bedtime_end_midnight_delta']:
        phase = pd.to_numeric(sleep[column], errors='coerce') * 2*np.pi/(24*3600)
        f[column+'_sin'] = np.sin(phase)
        f[column+'_cos'] = np.cos(phase)
    indexed = numeric[HISTORY].copy()
    indexed.index = pd.DatetimeIndex(endings)
    for days in (7, 14, 28):
        past = indexed.rolling(f'{days}D', closed='left', min_periods=3)
        median, std = past.median(), past.std()
        delta = indexed-median
        # Robust scale has a floor to avoid amplifying nearly constant histories.
        spread = past.quantile(.75)-past.quantile(.25)
        for name in HISTORY:
            f[f'{name}_history{days}_median'] = median[name].to_numpy()
            f[f'{name}_history{days}_delta'] = delta[name].to_numpy()
            f[f'{name}_history{days}_relative'] = (delta[name]/median[name].abs().clip(lower=1)).to_numpy()
            f[f'{name}_history{days}_robust_z'] = (delta[name]/spread[name].clip(lower=1)).clip(-10, 10).to_numpy()
        f[f'sleep_debt_history{days}'] = ((8*3600-past.mean()['total']).clip(lower=0)/3600).to_numpy()
    activity = activity[['day_end_timestamp', *ACTIVITY]].copy().sort_values('day_end_timestamp')
    heart = heart[['timestamp', 'heart_rate', 'heart_rmssd']].copy().sort_values('timestamp')
    ht = heart.timestamp.to_numpy(float)
    for i, row in sleep.iterrows():
        end = float(row.bedtime_end_timestamp)
        before = activity[activity.day_end_timestamp <= end]
        for days in (7, 14):
            relevant = before[before.day_end_timestamp > end-days*86400000]
            for name in ACTIVITY:
                values = pd.to_numeric(relevant[name], errors='coerce').dropna()
                f.loc[i, f'activity_history{days}_{name}_mean'] = values.mean() if len(values)>=3 else np.nan
                f.loc[i, f'activity_history{days}_{name}_std'] = values.std() if len(values)>=3 else np.nan
                f.loc[i, f'activity_history{days}_{name}_last_delta'] = values.iloc[-1]-values.mean() if len(values)>=3 else np.nan
        start = float(row.bedtime_start_timestamp)
        left, right = np.searchsorted(ht, [start, end], side='left')
        night = heart.iloc[left:right]
        relative = (night.timestamp.to_numpy(float)-start)/max(end-start, 1)
        for name in ['heart_rate', 'heart_rmssd']:
            values = pd.to_numeric(night[name], errors='coerce').to_numpy(float)
            valid = np.isfinite(values)&(values>0)&(values<300)
            if name=='heart_rate':
                valid &= values>=30
            v, t = values[valid], relative[valid]
            for stat in ['q10','q50','q90','early_median','late_median','late_minus_early',
                         'slope','lowest_position','early_above_lowest','high_fraction']:
                f.loc[i, name+'_trajectory_'+stat] = np.nan
            if len(v)<10:
                continue
            early = v[t<1/3];late = v[t>=2/3]
            early_median = np.median(early) if len(early)>=3 else np.nan
            late_median = np.median(late) if len(late)>=3 else np.nan
            smooth = pd.Series(v).rolling(3, center=True, min_periods=3).median().to_numpy()
            minimum = int(np.nanargmin(smooth))
            q10, q50, q90 = np.quantile(v, [.1,.5,.9])
            stats = [q10, q50, q90, early_median, late_median, late_median-early_median,
                np.polyfit(t, v, 1)[0] if np.ptp(t)>.1 else np.nan, t[minimum],
                early_median-smooth[minimum], np.mean(v>q10+5)]
            for stat, value in zip(['q10','q50','q90','early_median','late_median','late_minus_early',
                                   'slope','lowest_position','early_above_lowest','high_fraction'], stats):
                f.loc[i, name+'_trajectory_'+stat] = value
    f['date'] = sleep.date.to_numpy()
    assert not np.isinf(f.drop(columns='date').to_numpy(float)).any()
    return f


def prepare(root):
    out = root/'data/prepared'/NAME
    protocol_path = root/'experiments/019-readiness-refinement-protocol.json'
    if protocol_path.exists():
        raise ValueError('Frozen refinement protocol exists; do not overwrite')
    prior = json.loads((root/'experiments/016-readiness-oura-protocol.json').read_text())
    original_path = root/'data/prepared/readiness-oura-v1/days.csv.gz'
    original = pd.read_csv(original_path)
    data = original[original.participant.isin(prior['split']['development'])].copy()
    assert set(data.participant).isdisjoint(prior['split']['test'])
    directory = root/'data/external/ifh_readiness'
    manifest = json.loads((directory/'manifest.json').read_text())
    records = {r['member']: r for r in manifest['files']}
    frames = [];sources = {}
    for person, group in data.groupby('participant', sort=True):
        p = directory/'extracted'/person/'oura'
        raw = {}
        for filename, columns in [('sleep.csv', SLEEP_COLUMNS), ('activity.csv', ['day_end_timestamp',*ACTIVITY]),
                                   ('heart_rate.csv', ['timestamp','heart_rate','heart_rmssd'])]:
            path = p/filename
            member = str(path.relative_to(directory/'extracted'))
            assert sha(path)==records[member]['sha256']
            sources[str(path.relative_to(root))] = sha(path)
            raw[filename] = pd.read_csv(path, usecols=columns)
        features = enhance(raw['sleep.csv'],raw['activity.csv'],raw['heart_rate.csv'])
        frame = group.merge(features, on='date', how='left', validate='one_to_one')
        assert len(frame)==len(group)
        frames.append(frame)
    frame = pd.concat(frames,ignore_index=True).sort_values('row_id').reset_index(drop=True)
    original_columns = prior['profiles']['sleep_physiology_history_activity']
    extra = [c for c in frame if c not in original.columns]
    assert all('score' not in c and c not in {'target','participant','row_id','date'} for c in extra)
    profiles = {'original':original_columns, 'recovery_context':original_columns+extra}
    out.mkdir(parents=True,exist_ok=True)
    path = out/'days.csv.gz';frame.to_csv(path,index=False,compression={'method':'gzip','mtime':0})
    from .readiness_refinement_training import CONFIGS, nested_folds
    protocol = {
        'experiment':19,'name':NAME,'target':'Observed daily Oura readiness1–100; vendor-score approximation, not independent live employee readiness.',
        'evaluation':'Exploratory nested development evaluation only. Original four test people stay excluded; not fresh external validation or a direct comparison with the prior3.98testMAE.',
        'people':sorted(frame.participant.unique()),'old_test_people_excluded':prior['split']['test'],
        'rows':len(frame),'profiles':profiles,'configurations':CONFIGS,'folds':nested_folds(frame),
        'fixed_reference':'Re-fit the experiment016 SVR C10 + CatBoost depths3/5 ensemble on each outer training fold using original features.',
        'selection':'Four outer person folds. Three inner person folds select minimum person-weighted MAE among registered configurations and optional mean of best three. No outer targets in selection.',
        'features':'Prior pipeline plus sleep-stage fractions, sleep timing phase,7/14/28-day preceding physiology medians/deviations, preceding activity histories and raw overnight heart trajectories. No score/contributor/target history/questionnaire/identity/calendar date predictors.',
        'cutoff':'End of completed sleep. All prior histories end strictly before it; activity ends no later than it. Heart samples only inside the completed night. Same-date alignment inherited without shifts.',
        'source_license':'CC0-1.0; https://zenodo.org/records/10458511',
        'metrics':'Equal person weights; MAE, RMSE, R2, agreement within ±5/±10. Paired person bootstrap against the refit fixed reference.',
        'fitting':'Weighted scaler and estimator for new candidates, training-fold median imputation only. Fixed reference preserves original unweighted scaling. Spline features and robust losses are selected inside inner folds.',
        'gate':'At least10% lower outer MAE than the fixed reference, MAE<=4, R2>=0.5; not production validation.',
        'production_enabled':False,'data_sha256':sha(path),'prior_prepared_sha256':sha(original_path),
        'source_sha256':sources,'code_sha256':{str(p.relative_to(root)):sha(p) for p in [Path(__file__),root/'src/neurasign_engine/readiness_refinement_training.py',root/'src/neurasign_engine/reference_benchmark.py',root/'src/neurasign_engine/readiness_oura.py']},
    }
    save(protocol_path,protocol)
    save(out/'audit.json',{'rows':len(frame),'people':frame.participant.nunique(),'feature_count':{p:len(c) for p,c in profiles.items()},
        'availability':frame[profiles['recovery_context']].notna().mean().to_dict(),'no_old_test_people':True})
    return {'rows':len(frame),'people':frame.participant.nunique(),'features':{p:len(c) for p,c in profiles.items()}}
