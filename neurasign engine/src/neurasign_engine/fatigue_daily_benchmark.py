"""Experiment 017: independent daily-fatigue regression, never a live label claim."""
from __future__ import annotations
import json
from pathlib import Path
import warnings
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import ExtraTreesRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import RobustScaler
from sklearn.svm import SVR
from threadpoolctl import threadpool_limits
from . import fatigue_daily_data as source
from .schema import SEED
from .transfer_training import write_json

PROTOCOL = 'experiments/017-fatigue-daily-protocol.json'
OUT = 'results/fatigue-daily-v1'
ALGORITHMS = ['ridge.1','ridge1','ridge10','ridge100','svr1','svr10','svr100','extra4','extraNone','cat3','cat5']
CONFIGS = [{'profile':profile,'algorithm':algorithm} for profile in source.PROFILES for algorithm in ALGORITHMS]
TRACKS = ['previous_day','same_day_retrospective']
FIXED = {'profile':'vitals','algorithm':'ridge10'}


def key(config):
    return config['profile']+'_'+config['algorithm']


def weights(frame):
    value = 1/frame.groupby('participant').participant.transform('size').to_numpy()
    return value/value.mean()


def constant(frame,target):
    order = np.argsort(frame[target].to_numpy());values = frame[target].to_numpy()[order]
    weight = weights(frame)[order]
    return float(values[np.searchsorted(np.cumsum(weight),weight.sum()/2)])


def fit(frame,target,config):
    if config not in CONFIGS or target not in source.TARGETS:
        raise ValueError('Unexpected target/configuration')
    algorithm = config['algorithm'];columns = source.PROFILES[config['profile']]
    if algorithm.startswith('ridge'):
        model = Ridge(alpha=float(algorithm[5:]))
    elif algorithm.startswith('svr'):
        model = SVR(C=float(algorithm[3:]),kernel='rbf',epsilon=.1)
    elif algorithm.startswith('extra'):
        model = ExtraTreesRegressor(n_estimators=250,min_samples_leaf=3,max_depth=4 if algorithm=='extra4' else None,random_state=SEED,n_jobs=1)
    elif algorithm.startswith('cat'):
        from catboost import CatBoostRegressor
        model = CatBoostRegressor(iterations=250,depth=int(algorithm[3:]),learning_rate=.04,l2_leaf_reg=10,
            loss_function='RMSE',random_seed=SEED,thread_count=1,verbose=False,allow_writing_files=False)
    else:
        raise ValueError(algorithm)
    pipeline = make_pipeline(SimpleImputer(strategy='median',add_indicator=True,keep_empty_features=True),
                             RobustScaler(quantile_range=(10,90)),model)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore',category=RuntimeWarning)
        pipeline.fit(frame[columns],frame[target],**{pipeline.steps[-1][0]+'__sample_weight':weights(frame)})
    return {'model':pipeline,'columns':columns,'config':config,'target':target,'training_people':sorted(frame.participant.unique()),
            'training_row_ids':frame.row_id.tolist(),'production_enabled':False,'scale':source.TARGETS[target]['range'],
            'score_is_calibrated_confidence':False}


def predict(artifact,frame):
    if artifact['columns'] != source.PROFILES[artifact['config']['profile']]:
        raise ValueError('Unexpected artifact predictor columns')
    low,high = artifact['scale']
    return np.clip(artifact['model'].predict(frame[artifact['columns']]),low,high)


def metrics(frame,target,prediction):
    truth = frame[target].to_numpy(float);prediction = np.asarray(prediction,float)
    if not np.isfinite(truth).all() or not np.isfinite(prediction).all():
        raise ValueError('Finite outcomes/predictions required')
    weight = weights(frame);weight /= weight.sum();error = prediction-truth
    mse = float(np.dot(weight,error**2));total = float(np.dot(weight,(truth-np.dot(weight,truth))**2))
    tolerance = source.TARGETS[target]['tolerance']
    person = {}
    for name,indices in frame.groupby('participant').indices.items():
        person[name] = {'mae':float(np.abs(error[indices]).mean()),'mse':float((error[indices]**2).mean()),
                        'within_tolerance':float((np.abs(error[indices]) <= tolerance).mean()),'days':len(indices)}
    return {'mae':float(np.dot(weight,np.abs(error))),'rmse':mse**.5,'r2':1-mse/total if total>0 else None,
            'within_tolerance':float(np.dot(weight,np.abs(error)<=tolerance)),'tolerance_points':tolerance,
            'people':int(frame.participant.nunique()),'days':len(frame),'per_person':person}


def uncertainty(metric):
    values = np.array([[v['mae'],v['within_tolerance']] for v in metric['per_person'].values()])
    resampled = values[np.random.default_rng(SEED).integers(0,len(values),(5000,len(values)))].mean(axis=1)
    return {'method':'5000 person-cluster percentile bootstrap; small heldout-person sample',
            'mae_95_ci':np.quantile(resampled[:,0],[.025,.975]).tolist(),
            'within_tolerance_95_ci':np.quantile(resampled[:,1],[.025,.975]).tolist()}


def prepare(root):
    frame,audit = source.prepare(root)
    people = sorted(frame.participant.unique(),key=lambda p:int(p[1:]))
    order = np.random.default_rng(SEED).permutation(people).tolist()
    count = int(np.ceil(len(people)*.2));test,development = sorted(order[:count]),sorted(order[count:])
    folds = [sorted(chunk.tolist()) for chunk in np.array_split(np.random.default_rng(SEED+1).permutation(development),4)]
    protocol = {'experiment':17,'dataset':source.DATASET,'paper':source.PAPER,'license':'CC BY 4.0',
        'split':{'seed':SEED,'development':development,'test':test,'development_validation_folds':folds},
        'targets':source.TARGETS,'tracks':TRACKS,'candidate_configs':CONFIGS,'fixed_reference':FIXED,
        'selection':'Minimum person-balanced development out-of-fold MAE independently per target and track; deterministic order breaks ties.',
        'primary_track':'previous_day: predict current daily fatigue from previous calendar-day sensors only',
        'secondary_track':'same_day_retrospective: same-day association; contains potentially post-questionnaire readings; never live validation',
        'preprocessing':'Training-fold median imputation and RobustScaler; person-balanced sample weights; clip predictions to original scale',
        'history':'Unlabeled sensor baselines from strictly earlier seven calendar days; current and future values excluded',
        'quality':'At least 288 minutes with HR or activity/day; per-channel features require 30 finite minutes',
        'labels':'Original VAS 1–10; exhaustion frequency Never 1/Sometimes 2/Regularly 3/Often 4/Always 5. Latest daily answer; conflicting simultaneous answers excluded.',
        'exclusions':['other PROs','relative fatigue compared to yesterday','sport questionnaire','timezone','calendar/time','participant identity','barometer'],
        'evaluation':'Hold out whole people before modeling; freeze all six selections before one test evaluation.',
        'research_gate':'For each target, >=20% test MAE improvement over training-person-weighted median and positive weighted R2; not a classification-accuracy gate.'}
    path = root/PROTOCOL
    if path.exists() and json.loads(path.read_text()) != protocol:
        raise ValueError('Refusing to replace frozen protocol')
    write_json(path,protocol)
    print(json.dumps({'prepared_tracks':audit['tracks'],'test_people':test}),flush=True)
    return frame,audit,protocol


def run(root):
    out = root/OUT
    if (out/'evaluation.json').exists():
        raise ValueError('Completed run is immutable; use verify')
    if not (root/PROTOCOL).exists():
        prepare(root)
    protocol = json.loads((root/PROTOCOL).read_text());audit = json.loads((root/'data/prepared/fatigue-daily-v1/audit.json').read_text())
    prepared = root/'data/prepared/fatigue-daily-v1/days.csv.gz';frame = pd.read_csv(prepared)
    assert source.sha(prepared) == audit['prepared_sha256']
    freeze = {'protocol_sha256':source.sha(root/PROTOCOL),'data_sha256':source.sha(prepared),
              'source_code_sha256':{str(p.relative_to(root)):source.sha(p) for p in [Path(__file__),root/'src/neurasign_engine/fatigue_daily_data.py']}}
    if (out/'run-start.json').exists() and json.loads((out/'run-start.json').read_text()) != freeze:
        raise ValueError('Source/protocol changed after tuning began')
    write_json(out/'run-start.json',freeze)
    selections = [];all_predictions = []
    with threadpool_limits(limits=1):
        for track in TRACKS:
            for target in source.TARGETS:
                rows = frame[(frame.track==track)&frame[target].notna()&frame.participant.isin(protocol['split']['development'])].copy().reset_index(drop=True)
                candidates = [];predictions = rows[['row_id','participant','unit_id',target]].copy()
                for index,config in enumerate(CONFIGS):
                    checkpoint = out/'development-candidates'/f'{track}-{target}-{key(config)}.csv'
                    if checkpoint.exists():
                        saved = pd.read_csv(checkpoint);assert np.array_equal(saved.row_id,rows.row_id);scores = saved.score.to_numpy()
                    else:
                        scores = np.full(len(rows),np.nan)
                        for valid_people in protocol['split']['development_validation_folds']:
                            valid = rows.participant.isin(valid_people)
                            if not valid.any():
                                continue
                            artifact = fit(rows[~valid],target,config);scores[valid] = predict(artifact,rows[valid])
                        assert np.isfinite(scores).all()
                        checkpoint.parent.mkdir(parents=True,exist_ok=True)
                        pd.DataFrame({'row_id':rows.row_id,'score':scores}).to_csv(checkpoint,index=False)
                    values = metrics(rows,target,scores)
                    candidates.append({'config':config,'metrics':values})
                    predictions[key(config)] = scores
                    print(json.dumps({'fatigue_daily_track':track,'target':target,'candidate':index+1,'of':len(CONFIGS),'mae':values['mae']}),flush=True)
                winner = min(candidates,key=lambda c:c['metrics']['mae'])
                selections.append({'track':track,'target':target,'selected':winner,'candidates':candidates})
                predictions['target'] = target;predictions['track'] = track
                all_predictions.append(predictions)
    selection = {'run':freeze,'selections':selections}
    write_json(out/'frozen-selection.json',selection)
    pd.concat(all_predictions,ignore_index=True).to_csv(out/'development-predictions.csv.gz',index=False,compression={'method':'gzip','mtime':0})
    print(json.dumps({'fatigue_daily_all_selections_frozen':len(selections)}),flush=True)
    reports = [];artifacts = [];predictions = []
    with threadpool_limits(limits=1):
        for job in selections:
            target,track = job['target'],job['track']
            eligible = frame[(frame.track==track)&frame[target].notna()]
            development = eligible[eligible.participant.isin(protocol['split']['development'])]
            heldout = eligible[eligible.participant.isin(protocol['split']['test'])].copy()
            assert not set(development.participant) & set(heldout.participant)
            heldout['constant'] = constant(development,target)
            for arm,config in [('selected',job['selected']['config']),('fixed',FIXED)]:
                artifact = fit(development,target,config);artifact['track'] = track
                path = root/f'models/fatigue-daily-v1/{track}-{target}-{arm}.joblib';path.parent.mkdir(parents=True,exist_ok=True)
                joblib.dump(artifact,path);heldout[arm] = predict(artifact,heldout)
                artifacts.append({'track':track,'target':target,'arm':arm,'file':str(path.relative_to(root)),'sha256':source.sha(path)})
            values = {arm:metrics(heldout,target,heldout[arm]) for arm in ['selected','fixed','constant']}
            for v in values.values():
                v['uncertainty'] = uncertainty(v)
            gain = 1-values['selected']['mae']/values['constant']['mae']
            gate = gain>=.2 and values['selected']['r2'] is not None and values['selected']['r2']>0
            reports.append({'target':target,'track':track,'test':values,'mae_improvement_fraction':gain,'gate_passed':gate,
                            'selected_config':job['selected']['config'],'development_mae':job['selected']['metrics']['mae']})
            heldout['target'] = target;predictions.append(heldout)
    pd.concat(predictions,ignore_index=True).to_csv(out/'test-predictions.csv.gz',index=False,compression={'method':'gzip','mtime':0})
    report = {'reports':reports,'audit':audit,'scope':'Daily fatigue only. Upper-arm Everion wearable; no live wrist fatigue validation or app integration.'}
    write_json(out/'report.json',report)
    write_json(out/'evaluation.json',{'artifacts':artifacts,'test_predictions_sha256':source.sha(out/'test-predictions.csv.gz'),
       'development_predictions_sha256':source.sha(out/'development-predictions.csv.gz'),'selection_sha256':source.sha(out/'frozen-selection.json')})
    write_report(root,report,protocol)
    print(json.dumps({'fatigue_daily_results':[{k:item[k] for k in ['target','track','mae_improvement_fraction','gate_passed']}|{'mae':item['test']['selected']['mae']} for item in reports]}),flush=True)


def write_report(root,report,protocol):
    lines = ['# Experiment 017: daily fatigue from an independent wearable dataset','',
        '**Offline daily-fatigue research. No production integration or instantaneous fatigue claim.**','',
        'Sources: [Luo/De Luca public dataset]('+source.DATASET+') and [original paper]('+source.PAPER+'). '
        'All 29 downloaded files match publisher checksums; local SHA256 manifests are retained. Dataset license: CC BY 4.0. '
        'The device is a Biovotion Everion worn on the upper arm, rather than a validated wrist-device transfer.','',
        'Targets stay distinct: overall fatigue VAS 1–10 and physical/mental exhaustion frequency encoded '
        'Never 1, Sometimes 2, Regularly 3, Often 4, Always 5. No sleepiness, stress, readiness or workload labels are invented. '
        'Simultaneous conflicting answers are excluded; latest daily responses are used.','',
        'Primary track uses the previous calendar day of wearable readings. Sensor timezone is undocumented '
        'while questionnaire timezone varies between UTC/CET/CEST; previous-day features avoid using the full outcome day. '
        'The secondary same-day track is explicitly retrospective: some readings can occur after the questionnaire. '
        'Neither track establishes within-minute fatigue detection.','',
        'Sensors: HR, device HRV, respiration, blood perfusion/pulse-wave summaries, skin conductance, '
        'skin temperature, activity counts, energy expenditure and steps. Barometer, identity, calendar, '
        'timezone and every other questionnaire are excluded as predictors. Each day requires 288 minutes '
        'with HR or activity; a channel requires 30 finite minutes. The history profile uses only preceding '
        'seven-calendar-day unlabeled sensor medians. No global imputation or future-baseline normalization.','',
        f"People: {len(protocol['split']['development'])} development, {len(protocol['split']['test'])} untouched test. "
        'Four person-disjoint development folds compare 33 configurations per target/track (ridge, RBF SVR, '
        'ExtraTrees, CatBoost; physiological/all wearable/history profiles). Person-balanced MAE selects '
        'all six configurations before any test evaluation. Targets are never predictors for another target.','',
        'Test people: '+', '.join(protocol['split']['test'])+'.','',
        '| Track | Target / scale | Days / people | Selected MAE | Constant MAE | Within tolerance | Tolerance | Weighted R² |',
        '|---|---|---:|---:|---:|---:|---:|---:|']
    for item in report['reports']:
        selected = item['test']['selected'];baseline = item['test']['constant'];target = item['target']
        lines.append(f"| {item['track']} | {target} / {source.TARGETS[target]['range']} | {selected['days']} / {selected['people']} | "
                     f"{selected['mae']:.3f} | {baseline['mae']:.3f} | {selected['within_tolerance']:.1%} | ±{selected['tolerance_points']:g} | {selected['r2']:.3f} |")
    lines += ['','**Within-tolerance percentages are regression agreement, not classification accuracy or confidence.** '
        'VAS tolerance is one original scale point; frequency tolerance is half a category. MAE is reported in original '
        'units, not converted into a fabricated percentage accuracy. The constant predicts the development-person-weighted '
        'median. Full fixed-reference results, person-bootstrap intervals, all 198 development comparisons and 12 saved '
        'artifact audits are retained in the ignored results directory.','',
        'Research gate requires at least 20% test MAE reduction against the constant and positive weighted R². Results:']
    for item in report['reports']:
        ci = item['test']['selected']['uncertainty']['mae_95_ci']
        lines.append(f"- {item['track']} / {item['target']}: {'passed' if item['gate_passed'] else 'not reached'}; "
                     f"MAE improvement {item['mae_improvement_fraction']:.1%}; MAE 95% person-bootstrap interval {ci[0]:.3f}–{ci[1]:.3f}.")
    lines += ['','No test-based selection or retuning. Small numbers of people and changing data coverage limit transportability. '
        'Daily questionnaire labels and session CFS labels from MEFAR are not pooled as equivalent outcomes.','',
        'Reproduce: `.venv/bin/python scripts/run_fatigue_daily.py prepare`, then `run`; use `verify` after completion.']
    (root/'experiments/017-fatigue-daily-results.md').write_text('\n'.join(lines)+'\n')


def verify(root):
    out = root/OUT;selection = json.loads((out/'frozen-selection.json').read_text());evaluation = json.loads((out/'evaluation.json').read_text())
    report = json.loads((out/'report.json').read_text());protocol = json.loads((root/PROTOCOL).read_text());freeze = selection['run']
    assert source.sha(root/PROTOCOL) == freeze['protocol_sha256']
    for path,digest in freeze['source_code_sha256'].items():
        assert source.sha(root/path) == digest
    assert source.sha(root/'data/prepared/fatigue-daily-v1/days.csv.gz') == freeze['data_sha256']
    for name,digest in report['audit']['provenance']['sha256'].items():
        assert source.sha(root/'data/external/fatigue_daily'/name) == digest
    for filename,keyname in [('test-predictions.csv.gz','test_predictions_sha256'),('development-predictions.csv.gz','development_predictions_sha256'),('frozen-selection.json','selection_sha256')]:
        assert source.sha(out/filename) == evaluation[keyname]
    test = pd.read_csv(out/'test-predictions.csv.gz');dev = pd.read_csv(out/'development-predictions.csv.gz')
    assert not set(test.participant) & set(dev.participant)
    assert set(test.participant) <= set(protocol['split']['test']) and set(dev.participant) <= set(protocol['split']['development'])
    prior = test[test.track=='previous_day']
    assert (pd.to_datetime(prior.feature_day) < pd.to_datetime(prior.day)).all()
    with threadpool_limits(limits=1):
        for item in evaluation['artifacts']:
            assert source.sha(root/item['file']) == item['sha256']
            artifact = joblib.load(root/item['file']);rows = test[(test.track==item['track'])&(test.target==item['target'])]
            assert not artifact['production_enabled'] and not set(artifact['training_people']) & set(rows.participant)
            np.testing.assert_allclose(predict(artifact,rows),rows[item['arm']],atol=1e-10)
            changed = rows.copy()
            for target in source.TARGETS:
                changed[target] = -999
            changed['participant'] = 'different';changed['day'] = 'different'
            np.testing.assert_allclose(predict(artifact,changed),rows[item['arm']],atol=1e-10)
    checks = 0
    for item in report['reports']:
        rows = test[(test.track==item['track'])&(test.target==item['target'])]
        for arm,saved in item['test'].items():
            perperson = []
            for _,person in rows.groupby('participant'):
                error = np.abs(person[arm]-person[item['target']])
                perperson.append([error.mean(),(error<=source.TARGETS[item['target']]['tolerance']).mean()])
            actual = np.mean(perperson,axis=0)
            np.testing.assert_allclose(actual,[saved['mae'],saved['within_tolerance']],atol=1e-12);checks += 2
    for job in selection['selections']:
        assert job['selected'] == min(job['candidates'],key=lambda c:c['metrics']['mae'])
        rows = dev[(dev.track==job['track'])&(dev.target==job['target'])]
        for candidate in job['candidates']:
            value = metrics(rows,job['target'],rows[key(candidate['config'])])
            np.testing.assert_allclose(value['mae'],candidate['metrics']['mae'],atol=1e-12)
    summary = {'verified':True,'artifact_replays':len(evaluation['artifacts']),'independent_test_metrics':checks,
               'source_files_verified':len(report['audit']['provenance']['sha256']),'development_comparisons':sum(len(j['candidates']) for j in selection['selections'])}
    write_json(out/'verification.json',summary);print(json.dumps(summary),flush=True)
