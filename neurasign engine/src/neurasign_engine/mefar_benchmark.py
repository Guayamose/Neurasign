"""Experiment 014: wrist-only CFS fatigue, grouped tuning and untouched people."""
from __future__ import annotations

import json
from pathlib import Path
import warnings

import joblib
import numpy as np
import pandas as pd
from scipy.special import expit
from sklearn.ensemble import ExtraTreesClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import RobustScaler
from sklearn.svm import SVC
from threadpoolctl import threadpool_limits

from . import mefar_data as source
from .personalization import observation_weights, training_weights
from .schema import SEED
from .short_window_report import independent_metrics
from .transfer_training import write_json

OUT = 'results/mefar-v1'
PROTOCOL = 'experiments/014-mefar-protocol.json'
ALGORITHMS = ['logit0.1','logit1','logit10','rbf0.1','rbf1','rbf10','extra6','extraNone','cat3','cat5']
CONFIGS = [{'width':width,'profile':profile,'algorithm':algorithm} for width in [60,180]
           for profile in source.PROFILES for algorithm in ALGORITHMS]
THRESHOLDS = [.35,.4,.45,.5,.55,.6,.65]


def key(config):
    return f"w{config['width']}_{config['profile']}_{config['algorithm']}"


def columns(config):
    if config not in CONFIGS:
        raise ValueError('Configuration must be predeclared')
    return [f"w{config['width']}__"+name for name in source.PROFILES[config['profile']]]


def estimator(algorithm):
    if algorithm.startswith('logit'):
        model = LogisticRegression(C=float(algorithm[5:]),max_iter=3000,random_state=SEED)
    elif algorithm.startswith('rbf'):
        model = SVC(C=float(algorithm[3:]),kernel='rbf',gamma='scale',probability=False)
    elif algorithm.startswith('extra'):
        depth = None if algorithm == 'extraNone' else 6
        model = ExtraTreesClassifier(n_estimators=300,max_depth=depth,min_samples_leaf=4,random_state=SEED,n_jobs=1)
    elif algorithm.startswith('cat'):
        from catboost import CatBoostClassifier
        model = CatBoostClassifier(iterations=350,depth=int(algorithm[3:]),learning_rate=.035,l2_leaf_reg=8,
            loss_function='Logloss',random_seed=SEED,thread_count=1,verbose=False,allow_writing_files=False)
    else:
        raise ValueError(algorithm)
    return make_pipeline(SimpleImputer(strategy='median',add_indicator=True,keep_empty_features=True),
                         RobustScaler(quantile_range=(10,90)),model)


def fit(frame,config):
    if frame.outcome.nunique() != 2:
        raise ValueError('Training requires both observed fatigue classes')
    cols = columns(config);model = estimator(config['algorithm'])
    with warnings.catch_warnings():
        warnings.simplefilter('ignore',category=RuntimeWarning)
        model.fit(frame[cols],frame.outcome,**{model.steps[-1][0]+'__sample_weight':training_weights(frame)})
    return {'model':model,'columns':cols,'config':config,'training_people':sorted(frame.participant.unique()),
            'training_units':sorted(frame.unit_id.unique()),'fitting_row_ids':frame.row_id.tolist(),
            'target':'MEFAR observed session CFS >= 12','production_enabled':False,
            'score_is_calibrated_confidence':False,'eeg_used':False}


def predict(artifact,frame):
    if artifact['columns'] != columns(artifact['config']):
        raise ValueError('Artifact has unexpected predictors')
    model = artifact['model'];values = frame[artifact['columns']]
    if artifact['config']['algorithm'].startswith('rbf'):
        return expit(model.decision_function(values))
    return model.predict_proba(values)[:,list(model.classes_).index(1)]


def metric(frame,scores,threshold=.5):
    data = frame[['participant','unit_id','outcome']].copy()
    data['decision'] = (np.asarray(scores) >= threshold).astype(float)
    return independent_metrics(data,'decision')


def bootstrap(frame,scores,threshold):
    """Cluster bootstrap people; never treat repeated windows as independent."""
    matrices = []
    for _,person in frame.assign(predicted=(np.asarray(scores) >= threshold).astype(int)).groupby('participant'):
        cm = np.zeros((2,2))
        for _,session in person.groupby('unit_id'):
            np.add.at(cm,(session.outcome.to_numpy(int),session.predicted.to_numpy(int)),1/(len(session)*person.unit_id.nunique()))
        matrices.append(cm)
    matrices = np.asarray(matrices)
    sampled = matrices[np.random.default_rng(SEED).integers(0,len(matrices),(5000,len(matrices)))].mean(axis=1)
    support = sampled.sum(axis=2);valid = (support > 0).all(axis=1)
    recall = np.divide(np.diagonal(sampled,axis1=1,axis2=2),support,out=np.full_like(support,np.nan),where=support>0)
    values = {'accuracy':np.trace(sampled,axis1=1,axis2=2),
              'balanced_accuracy':recall[valid].mean(axis=1),'low_recall':recall[valid,0],'high_recall':recall[valid,1]}
    return {'method':'5000 percentile person-cluster bootstrap samples; exploratory with five test people',
            'valid_both_class_resamples':int(valid.sum()),
            'percentile_95_ci':{k:np.quantile(v,[.025,.975]).tolist() for k,v in values.items()}}


def prepare(root):
    frame,audit = source.prepare(root)
    people = sorted(frame.participant.unique(),key=lambda p:int(p[1:]))
    shuffled = np.random.default_rng(SEED).permutation(people).tolist()
    test,development = sorted(shuffled[:5]),sorted(shuffled[5:])
    validation = [sorted(a.tolist()) for a in np.array_split(np.random.default_rng(SEED+1).permutation(development),4)]
    protocol = {'experiment':14,'dataset':source.DATASET,'paper':source.PAPER,'archive_sha256':source.ARCHIVE_SHA,
        'target':'Original CFS total >=12 versus <12, independently verified against questionnaire item marks',
        'window_seconds':[60,180],'stride_seconds':60,'first_endpoint_seconds':180,
        'split':{'seed':SEED,'development':development,'test':test,'development_validation_folds':validation},
        'selection':'Max pooled person/session-weighted development out-of-fold balanced accuracy; then minimum recall; deterministic order ties.',
        'candidate_configs':CONFIGS,'thresholds':THRESHOLDS,
        'ensemble':'Mean scores of top three distinct configurations ranked at 0.5; compare to each single configuration and all thresholds on development only.',
        'fixed_reference':{'width':60,'profile':'all_wrist','algorithm':'logit1'},
        'preprocessing':'Training-fold median imputation and RobustScaler; person/session-balanced then class-balanced training weights',
        'test_policy':'Freeze selected configuration(s)/threshold before a single final holdout evaluation; never select by test results',
        'gate':{'balanced_accuracy':.8,'minimum_each_recall':.7},
        'exclusions':['EEG','IBI','demographics','identity predictors','session/time predictors','author processed tables','other questionnaire predictors'],
        'interpretation':'Session-level self-reported general fatigue, including physical and mental items; not clinical diagnosis or independently labeled live state.'}
    path = root/PROTOCOL
    if path.exists() and json.loads(path.read_text()) != protocol:
        raise ValueError('Refusing to replace frozen protocol')
    write_json(path,protocol)
    print(json.dumps({'prepared':len(frame),'people':audit['people'],'test_people':test}),flush=True)
    return frame,audit,protocol


def run(root):
    out = root/OUT
    if (out/'evaluation.json').exists():
        raise ValueError('Completed evaluation is immutable; use verify')
    if not (root/'data/prepared/mefar-v1/windows.csv.gz').exists() or not (root/PROTOCOL).exists():
        prepare(root)
    data = pd.read_csv(root/'data/prepared/mefar-v1/windows.csv.gz')
    audit = json.loads((root/'data/prepared/mefar-v1/audit.json').read_text())
    protocol = json.loads((root/PROTOCOL).read_text())
    assert source.sha(root/'data/prepared/mefar-v1/windows.csv.gz') == audit['prepared_sha256']
    freeze = {'protocol_sha256':source.sha(root/PROTOCOL),'data_sha256':audit['prepared_sha256'],
              'code_sha256':{str(path.relative_to(root)):source.sha(path) for path in
                [Path(__file__),root/'src/neurasign_engine/mefar_data.py',root/'src/neurasign_engine/personalization.py',
                 root/'src/neurasign_engine/short_window_report.py']}}
    if (out/'run-start.json').exists() and json.loads((out/'run-start.json').read_text()) != freeze:
        raise ValueError('Source/protocol changed after development started')
    write_json(out/'run-start.json',freeze)
    development = data[data.participant.isin(protocol['split']['development'])].copy().reset_index(drop=True)
    heldout = data[data.participant.isin(protocol['split']['test'])].copy().reset_index(drop=True)
    assert not set(development.participant) & set(heldout.participant)
    predictions = development[['row_id','participant','unit_id','outcome','session']].copy()
    comparisons = []
    with threadpool_limits(limits=1):
        for i,config in enumerate(CONFIGS):
            checkpoint = out/'development-candidates'/(key(config)+'.csv')
            if checkpoint.exists():
                saved = pd.read_csv(checkpoint)
                assert np.array_equal(saved.row_id,development.row_id)
                scores = saved.score.to_numpy()
            else:
                scores = np.full(len(development),np.nan)
                for fold in protocol['split']['development_validation_folds']:
                    fitting = development[~development.participant.isin(fold)]
                    valid_mask = development.participant.isin(fold)
                    assert not set(fitting.participant) & set(development.loc[valid_mask,'participant'])
                    artifact = fit(fitting,config)
                    scores[valid_mask] = predict(artifact,development[valid_mask])
                assert np.isfinite(scores).all()
                checkpoint.parent.mkdir(parents=True,exist_ok=True)
                pd.DataFrame({'row_id':development.row_id,'score':scores}).to_csv(checkpoint,index=False)
            predictions[key(config)] = scores
            comparison = {'key':key(config),'config':config,'metrics':metric(development,scores)}
            comparisons.append(comparison)
            print(json.dumps({'mefar_candidate':i+1,'of':len(CONFIGS),'key':key(config),
                              'development_balanced_accuracy':comparison['metrics']['balanced_accuracy']}),flush=True)
    ranked = sorted(comparisons,key=lambda x:(x['metrics']['balanced_accuracy'],
                    min(x['metrics']['low_recall'],x['metrics']['high_recall'])),reverse=True)
    top = [c['key'] for c in ranked[:3]]
    predictions['ensemble_top3'] = predictions[top].mean(axis=1)
    choices = []
    for arm in [key(c) for c in CONFIGS]+['ensemble_top3']:
        for threshold in THRESHOLDS:
            values = metric(development,predictions[arm],threshold)
            choices.append({'arm':arm,'threshold':threshold,'metrics':values})
    winner = max(choices,key=lambda c:(c['metrics']['balanced_accuracy'],min(c['metrics']['low_recall'],c['metrics']['high_recall'])))
    selected_keys = top if winner['arm']=='ensemble_top3' else [winner['arm']]
    configs_by_key = {key(c):c for c in CONFIGS}
    selection = {'run':freeze,'winner':winner,'selected_configs':[configs_by_key[k] for k in selected_keys],
                 'top3_keys':top,'all_comparisons':comparisons,'threshold_comparisons':choices,
                 'development_people':sorted(development.participant.unique()),
                 'test_people':sorted(heldout.participant.unique())}
    write_json(out/'frozen-selection.json',selection)
    predictions.to_csv(out/'development-predictions.csv.gz',index=False,compression={'method':'gzip','mtime':0})
    print(json.dumps({'mefar_selection_frozen':winner['arm'],'threshold':winner['threshold'],
                      'development_balanced_accuracy':winner['metrics']['balanced_accuracy']}),flush=True)
    artifacts = [];scores = []
    with threadpool_limits(limits=1):
        for arm,configs in [('selected',selection['selected_configs']),('fixed',[protocol['fixed_reference']])]:
            current = []
            for index,config in enumerate(configs):
                artifact = fit(development,config)
                path = root/f'models/mefar-v1/{arm}-{index}.joblib';path.parent.mkdir(parents=True,exist_ok=True)
                joblib.dump(artifact,path)
                artifacts.append({'arm':arm,'index':index,'file':str(path.relative_to(root)),'sha256':source.sha(path)})
                current.append(predict(artifact,heldout))
            heldout[arm] = np.mean(current,axis=0)
    majority = int(np.dot(observation_weights(development),development.outcome) >= .5)
    heldout['majority'] = majority
    heldout['time_context_only'] = (heldout.session=='evening').astype(float)
    reports = {}
    for arm in ['selected','fixed','majority','time_context_only']:
        threshold = winner['threshold'] if arm=='selected' else .5
        reports[arm] = {**metric(heldout,heldout[arm],threshold),'threshold':threshold,
                        'uncertainty':bootstrap(heldout,heldout[arm],threshold)}
    selected = reports['selected'];gate = selected['balanced_accuracy'] >= .8 and min(selected['low_recall'],selected['high_recall']) >= .7
    report = {'test':reports,'development_selected':winner,'gate_passed':gate,'audit':audit,
              'scope':'Five previously untouched people; same MEFAR collection, not external generalization. No app integration.',
              'time_context_note':'Morning/evening baseline is a confounding diagnostic; never a wearable model input or candidate.'}
    heldout.to_csv(out/'test-predictions.csv.gz',index=False,compression={'method':'gzip','mtime':0})
    write_json(out/'report.json',report)
    write_json(out/'evaluation.json',{'test_predictions_sha256':source.sha(out/'test-predictions.csv.gz'),
        'development_predictions_sha256':source.sha(out/'development-predictions.csv.gz'),
        'selection_sha256':source.sha(out/'frozen-selection.json'),'artifacts':artifacts})
    write_report(root,report,selection)
    print(json.dumps({'mefar_test':{arm:{k:v[k] for k in ['accuracy','balanced_accuracy','low_recall','high_recall']} for arm,v in reports.items()},
                      'gate_passed':gate}),flush=True)


def write_report(root,report,selection):
    selected = selection['winner'];audit = report['audit']
    lines = ['# Experiment 014: MEFAR observed fatigue from wrist signals','',
        '**Offline research only. No production integration, clinical claim or calibrated confidence.**','',
        'Sources: [MEFAR v5]('+source.DATASET+') and [original data paper]('+source.PAPER+'), CC BY 4.0. '
        'The raw archive SHA256 matches the publisher. All 46 CFS questionnaire totals were independently '
        'recomputed from the 11 marked items and agree with the source summary. Fatigue means CFS ≥12, '
        'as defined by this dataset; the scale combines mental and physical fatigue. These are two ratings '
        'per person, not independently labeled instantaneous states.','',
        f"Data: {audit['people']} people, {audit['sessions']} sessions, {audit['windows']} matched endpoints. "
        'Inputs are raw wrist BVP, EDA, temperature, acceleration and device HR only. No EEG, demographics, '
        'session/time-of-day or questionnaire values are predictors. The author-normalized and oversampled '
        'processed data are excluded. Each causal feature window ends before prediction; signal summaries '
        'and pulse variability are computed from the trailing 60 or 180 seconds, at 60-second steps. '
        'Pulse variability extracted from moving wrist BVP is exploratory, not ECG-validated HRV.','',
        'Eighteen people are used for four person-disjoint development folds; five people are reserved '
        'before training and evaluated once. All sessions/windows from a person stay together. The fixed '
        'search contains 60 configurations: two window lengths, three signal profiles and ten settings '
        'across logistic regression, RBF SVM, ExtraTrees and CatBoost. A top-three score ensemble and '
        'seven predefined decision thresholds are compared on development predictions only. '
        'Imputation/scaling are fitted on each training fold; training weights balance people, sessions '
        'and classes. Evaluation weights people equally, then sessions equally.','',
        'Development people: '+', '.join(selection['development_people'])+'. Test people: '+', '.join(selection['test_people'])+'.','',
        f"Development-selected arm: `{selected['arm']}` at threshold {selected['threshold']:.2f}. "
        f"Development balanced accuracy: {selected['metrics']['balanced_accuracy']:.1%}. This is a selection score, not an unbiased accuracy claim.",'',
        '| Untouched test arm | Accuracy | Balanced accuracy | Low recall | Fatigue recall | Within-person balanced |',
        '|---|---:|---:|---:|---:|---:|']
    for arm,values in report['test'].items():
        lines.append('| '+arm+' | '+' | '.join('n/a' if values[k] is None else f'{values[k]:.1%}' for k in
            ['accuracy','balanced_accuracy','low_recall','high_recall','within_person_balanced_accuracy'])+' |')
    interval = report['test']['selected']['uncertainty']['percentile_95_ci']['balanced_accuracy']
    lines += ['',f"Selected test balanced accuracy 95% person-bootstrap interval: {interval[0]:.1%}–{interval[1]:.1%}. "
        'Only five test people make uncertainty large; repeated windows do not add independent people.', '',
        f"Predeclared gate (balanced accuracy ≥80% and both recalls ≥70%): **{'passed' if report['gate_passed'] else 'not reached'}**.",'',
        'The time-context baseline predicts low in the morning and high in the evening; it diagnoses '
        'collection confounding and is never a candidate or model input. The fixed logistic reference '
        'is reported regardless of whether it beats the development-selected model; final test outcomes '
        'must not be used to change the selection. Generalization across devices, workplaces and days '
        'is not established. This does not train readiness or workload.','',
        'Reproduce: `.venv/bin/python scripts/run_mefar.py prepare`, then `run`; inspect the completed '
        'immutable evaluation using `verify`. Full comparisons, frozen selection, source audit, local '
        'weights and predictions remain in ignored data/results/models directories.']
    (root/'experiments/014-mefar-results.md').write_text('\n'.join(lines)+'\n')


def verify(root):
    out = root/OUT;selection = json.loads((out/'frozen-selection.json').read_text())
    report = json.loads((out/'report.json').read_text());evaluation = json.loads((out/'evaluation.json').read_text())
    freeze = selection['run'];protocol = json.loads((root/PROTOCOL).read_text())
    assert source.sha(root/PROTOCOL) == freeze['protocol_sha256']
    for path,digest in freeze['code_sha256'].items():
        assert source.sha(root/path) == digest
    assert source.sha(root/'data/prepared/mefar-v1/windows.csv.gz') == freeze['data_sha256']
    for path,digest in report['audit']['source_hashes'].items():
        assert source.sha(root/path) == digest
    assert source.sha(root/'data/external/mefar/raw/MEFAR/general_info.xlsx') == report['audit']['labels_sha256']
    assert source.sha(out/'test-predictions.csv.gz') == evaluation['test_predictions_sha256']
    assert source.sha(out/'development-predictions.csv.gz') == evaluation['development_predictions_sha256']
    assert source.sha(out/'frozen-selection.json') == evaluation['selection_sha256']
    test = pd.read_csv(out/'test-predictions.csv.gz');dev = pd.read_csv(out/'development-predictions.csv.gz')
    assert set(test.participant) == set(protocol['split']['test'])
    assert set(dev.participant) == set(protocol['split']['development'])
    assert not set(test.participant) & set(dev.participant)
    assert not set(test.row_id) & set(dev.row_id)
    assert not test.row_id.duplicated().any() and not dev.row_id.duplicated().any()
    saved_predictions = {'fixed':[],'selected':[]}
    with threadpool_limits(limits=1):
        for item in evaluation['artifacts']:
            assert source.sha(root/item['file']) == item['sha256']
            artifact = joblib.load(root/item['file'])
            assert artifact['production_enabled'] is False
            assert set(artifact['training_people']) == set(dev.participant)
            assert set(artifact['fitting_row_ids']) == set(dev.row_id)
            score = predict(artifact,test)
            changed = test.copy();changed['outcome'] = 1-changed.outcome
            changed['cfs'] = -999;changed['participant'] = 'changed';changed['session'] = 'changed';changed['window_end'] = 0
            np.testing.assert_allclose(score,predict(artifact,changed),atol=1e-12)
            saved_predictions[item['arm']].append(score)
    for arm,values in saved_predictions.items():
        np.testing.assert_allclose(np.mean(values,axis=0),test[arm],atol=1e-12)
    checks = 0
    for arm,values in report['test'].items():
        # Independent direct person/session weights and confusion matrix, separate from reporting helper.
        tasks = test.groupby('participant').unit_id.transform('nunique').to_numpy()
        windows = test.groupby(['participant','unit_id']).unit_id.transform('size').to_numpy()
        weight = 1/(tasks*windows*test.participant.nunique())
        decisions = test[arm].to_numpy() >= values['threshold'];actual = test.outcome.to_numpy(int)
        low = np.sum(weight*(actual==0)*~decisions)/np.sum(weight*(actual==0))
        high = np.sum(weight*(actual==1)*decisions)/np.sum(weight*(actual==1))
        for name,value in [('accuracy',np.sum(weight*(decisions==actual))),('balanced_accuracy',(low+high)/2),('low_recall',low),('high_recall',high)]:
            np.testing.assert_allclose(value,values[name],atol=1e-12);checks += 1
    winner = selection['winner']
    assert winner == max(selection['threshold_comparisons'],key=lambda c:(c['metrics']['balanced_accuracy'],min(c['metrics']['low_recall'],c['metrics']['high_recall'])))
    for choice in selection['all_comparisons']:
        np.testing.assert_allclose(metric(dev,dev[choice['key']])['balanced_accuracy'],choice['metrics']['balanced_accuracy'],atol=1e-12)
    for fold in protocol['split']['development_validation_folds']:
        assert not set(fold) & set(test.participant)
    assert sorted(p for fold in protocol['split']['development_validation_folds'] for p in fold) == sorted(dev.participant.unique())
    result = {'verified':True,'independent_test_metric_checks':checks,'development_comparisons':len(selection['all_comparisons']),
              'artifact_replays':len(evaluation['artifacts']),'source_hashes':len(report['audit']['source_hashes'])}
    write_json(out/'verification.json',result);print(json.dumps(result),flush=True)
