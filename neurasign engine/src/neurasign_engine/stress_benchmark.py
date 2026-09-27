"""Experiment 012: anonymous offline self-report labels, never product inference.

Prior physiology, holdouts and experiments are read-only. Model selection reads
Lab1 only; the separately prepared Lab2 data is opened only at evaluation.
"""
from __future__ import annotations

from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
import csv
from datetime import datetime, timezone
import io
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

from . import personalization as prior
from .data import verified_bytes
from .schema import normalize_likert
from .short_window import fit as fit_classifier, choose as choose_classifier
from .short_window_report import independent_metrics, align_pair
from .transfer_features import FEATURES
from .transfer_training import sha, thin, write_json

OUT = 'results/stress-v1'
PREPARED = 'data/prepared/stress-v1'
PROTOCOL = 'experiments/012-stress-protocol.json'
TARGET = 'self_reported_stress'
ARMS = tuple(prior.ARMS)
LEARNED = tuple(a for a in ARMS if not a.endswith('constant'))
META = ['participant', 'session', 'unit_id', 'source_end', 'window_end', 'row_id', 'segment', TARGET, 'outcome']


def binary_labels(values):
    values = np.asarray(values, float)
    if np.any(np.isfinite(values) & ~np.isin(values, [1, 2, 3, 4, 5])):
        raise ValueError('Stress answers must be the observed five-level questionnaire')
    return np.where(values <= 2, 0., np.where(values >= 4, 1., np.nan))


def parse_questionnaire(data):
    """Quarantine malformed/conflicting segments; preserve original line numbers."""
    reader = csv.reader(io.StringIO(data.decode('utf-8-sig')))
    header = next(reader, None)
    if not header or 'Task' not in header or len(header) != len(set(header)):
        raise ValueError('Expected unambiguous laboratory questionnaire headers')
    present = 'Mental stress level' in header
    audit = Counter(); records = {}; invalid = set()
    for line, cells in enumerate(reader, 2):
        audit['rows'] += 1
        if len(cells) != len(header):
            audit['malformed_width'] += 1
            if len(cells) > header.index('Task'):
                invalid.add(cells[header.index('Task')].strip().replace('video_baseline', 'relaxation_video'))
            continue
        row = dict(zip(header, cells)); segment = row['Task'].strip()
        segment = 'relaxation_video' if segment == 'video_baseline' else segment
        if not segment:
            audit['missing_segment'] += 1
            continue
        text = row.get('Mental stress level', '').strip()
        value = normalize_likert(text) if text else None
        reason = 'observed' if value is not None else ('invalid_answer' if text else 'missing_answer')
        if text and value is None:
            invalid.add(segment); audit['invalid_answer'] += 1
        if segment in records:
            audit['duplicate_segment'] += 1
            if records[segment]['value'] != value:
                invalid.add(segment); audit['conflicting_segment'] += 1
            records[segment]['lines'].append(line)
        else:
            records[segment] = {'value': value, 'lines': [line], 'reason': reason}
    for segment in invalid:
        record = records.setdefault(segment, {'lines': []})
        record.update(value=None, reason='ambiguous_or_malformed_segment')
    return records, {'stress_header_present': present, **dict(audit)}


def _read(path):
    return json.loads(path.read_text())


def _coverage(frame):
    units = frame.drop_duplicates('unit_id')
    result = {'windows': len(frame), 'tasks': len(units), 'people': int(frame.participant.nunique())}
    for label, mask in [('missing', frame[TARGET].isna()), ('neutral', frame[TARGET] == 3),
                        ('low', frame[TARGET].isin([1, 2])), ('high', frame[TARGET].isin([4, 5]))]:
        result[label+'_windows'] = int(mask.sum())
        result[label+'_tasks'] = int(frame.loc[mask, 'unit_id'].nunique())
    return result


def prepare(root):
    destination = root/PREPARED
    if (destination/'audit.json').exists():
        raise ValueError('Preparation is already frozen; verify instead of replacing it')
    source = root/'data/prepared/transfer-v1/universe.csv.gz'
    old_audit = _read(root/'data/prepared/personalization-v1/audit.json')
    if sha(source) != old_audit['input_sha256']:
        raise ValueError('Physiology input differs from the prior frozen source')
    frame = pd.read_csv(source); frame['row_id'] = frame.index
    split = _read(root/'experiments/split-v1.json')
    if not set(frame.participant) <= set(split['development']):
        raise ValueError('Input contains participants outside original development set')
    frame = frame.loc[frame.session.isin(['Lab1', 'Lab2']), [*FEATURES, *META[:5], 'row_id']].copy()
    if frame.duplicated(['participant', 'session', 'source_end']).any():
        raise ValueError('Duplicate physiological endpoints')
    provenance_path = root/'data/prepared/causal-v3/provenance.json'
    provenance_rows = _read(provenance_path)
    provenance = {r['unit_id']: r for r in provenance_rows}
    if len(provenance) != len(provenance_rows):
        raise ValueError('Duplicate provenance unit IDs')
    manifest_path = root/'data/universe/manifest.json'; manifest_doc = _read(manifest_path)
    if manifest_doc['summary']['status'] != 'complete':
        raise ValueError('Questionnaire acquisition is incomplete')
    manifest = {r['member']: r for r in manifest_doc['files']}
    extracted = root/'data/universe/extracted'
    sources = {}; cache = {}; assignments = []
    for unit, group in frame.groupby('unit_id', sort=True):
        record = provenance.get(unit)
        if record is None:
            raise ValueError('Physiological unit lacks provenance: '+str(unit))
        person, session = record['participant'], record['session']
        if set(group.participant) != {person} or set(group.session) != {session}:
            raise ValueError('Provenance identity disagrees with physiology')
        member = record['label_source']
        expected = f'UNIVERSE/{person}/{session}/Task_Labels.csv'
        if member != expected or not record['segment'].startswith(f'UNIVERSE/{person}/{session}/Labeled/'):
            raise ValueError('Unexpected questionnaire or segment location')
        if member not in cache:
            payload = verified_bytes(extracted/member, extracted, manifest)
            cache[member], audit = parse_questionnaire(payload)
            sources[member] = {'sha256': sha(extracted/member), 'participant': person, 'session': session, **audit}
        segment = Path(record['segment']).name
        label = cache[member].get(segment, {'value': None, 'lines': [], 'reason': 'unmatched_source_segment'})
        assignments.append({'unit_id': unit, 'participant': person, 'session': session,
                            'segment': segment, 'label_source': member, 'source_lines': label['lines'],
                            TARGET: label['value'], 'label_status': label['reason']})
    assigned = pd.DataFrame(assignments)
    frame = frame.merge(assigned[['unit_id', 'segment', TARGET]], on='unit_id', how='left', validate='many_to_one')
    frame['outcome'] = binary_labels(frame[TARGET])
    selected = frame[frame.outcome.notna()].copy(); selected.outcome = selected.outcome.astype(int)
    train = selected[selected.session == 'Lab1'].copy()
    paired = sorted(set(train.participant) & set(selected.loc[selected.session == 'Lab2', 'participant']))
    evaluation = selected[(selected.session == 'Lab2') & selected.participant.isin(paired)].copy()
    people = {}
    for person in paired:
        a = train[train.participant == person]; b = evaluation[evaluation.participant == person]
        one = a.drop_duplicates('unit_id').outcome.value_counts()
        two = b.drop_duplicates('unit_id').outcome.value_counts()
        people[person] = {'lab1_low_tasks': int(one.get(0, 0)), 'lab1_high_tasks': int(one.get(1, 0)),
                          'lab2_low_tasks': int(two.get(0, 0)), 'lab2_high_tasks': int(two.get(1, 0)),
                          'adequate_calibration': bool(min(one.get(0, 0), one.get(1, 0)) >= 2),
                          'single_class_calibration': len(one) < 2,
                          'both_lab2_classes': len(two) == 2,
                          'lab1_evidence_minutes': prior.union_seconds(a.source_end)/60}
    destination.mkdir(parents=True, exist_ok=True)
    files = {}
    for session, data in [('lab1', train), ('lab2', evaluation)]:
        path = destination/(session+'.csv.gz')
        data[[*FEATURES, *META]].to_csv(path, index=False, compression={'method': 'gzip', 'mtime': 0})
        files[path.name] = sha(path)
    write_json(destination/'label-provenance.json', assignments)
    result = {'protocol_sha256': sha(root/PROTOCOL), 'source_sha256': sha(source),
              'source_provenance_sha256': sha(provenance_path), 'manifest_sha256': sha(manifest_path),
              'label_provenance_sha256': sha(destination/'label-provenance.json'), 'sources': sources,
              'files': files, 'paired_people': paired, 'people': people,
              'source_coverage': {s: _coverage(frame[frame.session == s]) for s in ('Lab1', 'Lab2')},
              'lab1_labeled_people': sorted(train.participant.unique()),
              'lab1_scored_windows': len(train), 'lab2_scored_windows': len(evaluation),
              'lab2_scored_tasks': int(evaluation.unit_id.nunique()),
              'lab2_windows_in_paired_people': int(((frame.session == 'Lab2') & frame.participant.isin(paired)).sum()),
              'original_test_excluded': split['test'], 'features': list(FEATURES),
              'production_enabled': False, 'interpretation': 'Task-level self-report classification; not live or clinical truth'}
    write_json(destination/'audit.json', result)
    print(json.dumps({'paired_people': len(paired), 'Lab1': result['source_coverage']['Lab1'],
                      'Lab2': result['source_coverage']['Lab2'], 'scored_lab2_windows': len(evaluation)}), flush=True)
    return result


def load_frame(root, session):
    if session not in ('lab1', 'lab2'):
        raise ValueError('Unsupported session')
    audit = _read(root/PREPARED/'audit.json'); path = root/PREPARED/(session+'.csv.gz')
    if sha(path) != audit['files'][path.name]:
        raise ValueError('Prepared input changed')
    frame = pd.read_csv(path)
    if not set(frame.session) <= {session.capitalize()}:
        raise ValueError('Prepared file contains another session')
    if list(frame.columns) != [*FEATURES, *META] or not frame.outcome.isin([0, 1]).all():
        raise ValueError('Unexpected prepared features or outcomes')
    return frame


def preserved_files(root):
    paths = list((root/'src/neurasign_engine').glob('*.py')) + list((root/'scripts').glob('*.py'))
    paths += list((root/'tests').glob('test_*.py'))
    paths += [p for p in (root/'experiments').glob('*') if not p.name[:3].isdigit() or int(p.name[:3]) <= 11]
    paths += [root/p for p in ['data/prepared/transfer-v1/universe.csv.gz', 'data/prepared/causal-v3/provenance.json',
                              'results/transfer-v1/final/test-report.json', 'results/personalization-v1/report.json',
                              'results/short-window-v1/report.json', 'results/papagei-v1/report.json',
                              'results/swell-v1/report.json']]
    return {str(p.relative_to(root)): sha(p) for p in paths if p.is_file() and 'stress' not in p.name}


def _check_frozen(root, run):
    for name, digest in {PROTOCOL: run['protocol_sha256'], PREPARED+'/audit.json': run['audit_sha256'],
                         **run['code'], **run['preserved_files']}.items():
        if sha(root/name) != digest:
            raise ValueError('Frozen input/code changed: '+name)


def selection_job(root_string, mode, key, ids):
    root = Path(root_string); train = load_frame(root, 'lab1')
    train = train[train.participant.isin(ids)] if mode == 'personal' else train[~train.participant.isin(ids)]
    if train.empty:
        raise ValueError('No Lab1 training examples for '+mode+' '+str(key))
    selected = choose_classifier(train, 'legacy60', mode == 'personal')
    result = {'mode': mode, 'key': key, 'training_people': sorted(train.participant.unique()),
              'training_units': sorted(train.unit_id.unique()), **selected}
    write_json(root/OUT/'selection'/f'{mode}__{key}.json', result)
    return result


def select(root):
    out = root/OUT; out.mkdir(parents=True, exist_ok=True)
    if (out/'evaluation.json').exists() or (out/'frozen-selection.json').exists():
        raise ValueError('Selection already frozen; evaluate or verify instead')
    audit = _read(root/PREPARED/'audit.json')
    folds = _read(root/'results/transfer-v1/universe/protocol.json')['folds']
    code_paths = [Path(__file__), root/'scripts/run_stress_benchmark.py', root/'tests/test_stress_benchmark.py']
    run = {'protocol_sha256': sha(root/PROTOCOL), 'audit_sha256': sha(root/PREPARED/'audit.json'), 'folds': folds,
           'code': {str(p.relative_to(root)): sha(p) for p in code_paths}, 'preserved_files': preserved_files(root)}
    path = out/'selection-run.json'
    if path.exists() and _read(path) != run:
        raise ValueError('Cannot resume selection with changed inputs/code')
    write_json(path, run)
    jobs = [(str(root), 'generic', i, ids) for i, ids in enumerate(folds) if set(ids) & set(audit['paired_people'])]
    jobs += [(str(root), 'personal', p, [p]) for p in audit['paired_people']]
    results = []
    with ProcessPoolExecutor(max_workers=6) as pool:
        futures = []
        for job in jobs:
            cache = out/'selection'/f'{job[1]}__{job[2]}.json'
            if cache.exists():
                results.append(_read(cache))
            else:
                futures.append(pool.submit(selection_job, *job))
        for future in as_completed(futures):
            result = future.result(); results.append(result)
            print(json.dumps({'selected': len(results), 'of': len(jobs), 'mode': result['mode'], 'key': result['key'],
                              'algorithm': result['config']['algorithm']}), flush=True)
    results.sort(key=lambda r: (r['mode'], str(r['key'])))
    write_json(out/'frozen-selection.json', {'frozen_utc': datetime.now(timezone.utc).isoformat(),
                                            'run': run, 'selections': results})


def evaluation_job(root_string, person, fold, excluded, generic_config, personal_config):
    root = Path(root_string); train = load_frame(root, 'lab1'); future = load_frame(root, 'lab2')
    future = future[future.participant == person]
    generic = train[~train.participant.isin(excluded)]; personal = train[train.participant == person]
    frames = {'generic': generic, 'personal': personal, 'hybrid': pd.concat([generic, personal], ignore_index=True)}
    if set(generic.participant) & set(excluded) or set(personal.participant) != {person}:
        raise ValueError('Training groups overlap the wrong people')
    metadata = future[META].copy(); metadata['fold'] = fold; artifacts = []
    with threadpool_limits(limits=1):
        for arm in ARMS:
            mode, variant = arm.split('_')
            if variant == 'constant':
                score = np.full(len(future), prior.majority(frames[mode]), dtype=float)
            else:
                config = personal_config if mode == 'personal' else generic_config
                algorithm = 'logit1' if variant == 'fixed' else config['algorithm']
                artifact = fit_classifier(frames[mode], 'legacy60', algorithm, person if mode == 'hybrid' else None)
                artifact.update(target=TARGET, intended_use='Anonymous public-data offline self-report benchmark only',
                                deployment_approved=False, clinical_validation=False, production_enabled=False)
                score = prior.predict(artifact, future)
                path = root/'models/stress-v1'/person/(arm+'.joblib'); path.parent.mkdir(parents=True, exist_ok=True)
                joblib.dump(artifact, path)
                artifacts.append({'arm': arm, 'file': str(path.relative_to(root)), 'sha256': sha(path),
                                  'config': artifact['config'], 'single_class_fallback': 'constant' in artifact})
            metadata[arm] = score
    path = root/OUT/'predictions'/(person+'.csv.gz'); path.parent.mkdir(parents=True, exist_ok=True)
    metadata.to_csv(path, index=False, compression={'method': 'gzip', 'mtime': 0})
    return {'person': person, 'fold': fold, 'prediction_file': str(path.relative_to(root)),
            'predictions_sha256': sha(path), 'artifacts': artifacts}


def evaluate(root):
    out = root/OUT
    if (out/'evaluation.json').exists():
        raise ValueError('Lab2 evaluation is already saved; report or verify instead')
    frozen = _read(out/'frozen-selection.json'); run = frozen['run']; _check_frozen(root, run)
    audit = _read(root/PREPARED/'audit.json')
    choices = {(r['mode'], str(r['key'])): r['config'] for r in frozen['selections']}
    jobs = []
    for person in audit['paired_people']:
        fold = next(i for i, ids in enumerate(run['folds']) if person in ids)
        jobs.append((str(root), person, fold, run['folds'][fold], choices['generic', str(fold)], choices['personal', person]))
    write_json(out/'evaluation-start.json', {'started_utc': datetime.now(timezone.utc).isoformat(),
                                            'selection_sha256': sha(out/'frozen-selection.json')})
    results = []
    with ProcessPoolExecutor(max_workers=6) as pool:
        for future in as_completed([pool.submit(evaluation_job, *job) for job in jobs]):
            result = future.result(); results.append(result)
            print(json.dumps({'evaluated': len(results), 'of': len(jobs), 'person': result['person']}), flush=True)
    results.sort(key=lambda r: r['person'])
    write_json(out/'evaluation.json', {'selection_sha256': sha(out/'frozen-selection.json'), 'jobs': results})


def predictions(root):
    evaluation = _read(root/OUT/'evaluation.json'); parts = []
    for job in evaluation['jobs']:
        path = root/job['prediction_file']
        if sha(path) != job['predictions_sha256']:
            raise ValueError('Prediction checksum failed')
        parts.append(pd.read_csv(path))
    frame = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=[*META, *ARMS])
    if frame.row_id.duplicated().any():
        raise ValueError('Duplicate evaluation row IDs')
    return frame.sort_values('row_id').reset_index(drop=True)


def report(root):
    frame = predictions(root); audit = _read(root/PREPARED/'audit.json')
    groups = {'all_paired': frame, 'active_tasks_only': frame[frame.segment != 'relaxation_video']}
    results = {name: {arm: independent_metrics(part, arm) for arm in ARMS} for name, part in groups.items()}
    evaluation = _read(root/OUT/'evaluation.json')
    result = {'experiment': '012-anonymous-offline-self-report-stress', 'target': TARGET, 'audit': audit,
              'groups': results, 'production_enabled': False, 'claim_status': 'No validated accuracy or deployment claim',
              'single_class_artifacts': [r['file'] for job in evaluation['jobs'] for r in job['artifacts'] if r['single_class_fallback']],
              'evaluation_sha256': sha(root/OUT/'evaluation.json')}
    write_json(root/OUT/'report.json', result)
    def pct(value):
        return 'not estimable' if value is None else f'{value*100:.1f}%'
    a, b = audit['source_coverage']['Lab1'], audit['source_coverage']['Lab2']
    both = results['all_paired']['generic_constant']['people_with_both_classes']
    lines = ['# Experiment 012: anonymous self-reported stress benchmark', '',
             '**Result: insufficient evidence for a reliable stress classifier or an 80% accuracy claim. No model was enabled in the product.**', '',
             'This separate academic benchmark classifies the original UNIVERSE `Mental stress level` answers. Levels 1–2 mean low, 4–5 mean high, and neutral 3/missing answers are excluded. These are retrospective task answers, not measured instantaneous stress or clinical ground truth.', '',
             f'Only **{len(audit["paired_people"])} people** have eligible labeled windows in both laboratory sessions; **{both}** have both low and high labels in Lab2. This cannot satisfy the protocol requirement for an informative cohort of at least ten people with both evaluation classes. High ordinary accuracy on an imbalanced cohort cannot establish discrimination.', '',
             '## Source and coverage', '',
             '| Session | People in physiological input | Task intervals | Windows | Missing stress windows | Neutral windows | Low windows | High windows |',
             '|---|---:|---:|---:|---:|---:|---:|---:|']
    for name, item in [('Lab1', a), ('Lab2', b)]:
        lines.append(f'| {name} | {item["people"]} | {item["tasks"]} | {item["windows"]} | {item["missing_windows"]} | {item["neutral_windows"]} | {item["low_windows"]} | {item["high_windows"]} |')
    lines += ['', f'Lab1 fitting has {len(audit["lab1_labeled_people"])} people and {audit["lab1_scored_windows"]} eligible windows. The paired Lab2 evaluation contains {audit["lab2_scored_tasks"]} task answers and {audit["lab2_scored_windows"]} windows, drawn from {audit["lab2_windows_in_paired_people"]} physiological windows in those people before excluding missing/neutral labels. Windows repeat task answers and are not independent labeled cases.', '',
              'Questionnaires were checksum-verified against the acquisition manifest and joined through original causal provenance. Malformed or conflicting segment answers are quarantined. No other questionnaire enters a predictor. The original five UNIVERSE test participants and Mobile holdout remain closed.', '',
              '## Frozen comparison', '',
              'All fitting and selection use Lab1. General models exclude the evaluation person’s original participant fold; personal models use their own Lab1; hybrid models combine own and other-person Lab1 with the registered weighting. Fixed models use logistic regression; selected models choose among logistic, RBF SVC, ExtraTrees and CatBoost with whole-person or whole-task Lab1 validation. No configuration or cutoff was changed after Lab2 scoring.', '',
              'Metrics weight people equally and tasks equally within each person. Balanced accuracy averages low/high recall; within-person balanced accuracy includes only people with both Lab2 classes. Model scores are not calibrated confidence.', '']
    for name, items in results.items():
        lines += [f'### {name.replace("_", " ")}', '', '| Arm | Ordinary accuracy | Balanced accuracy | Within-person balanced accuracy | Low recall | High recall |',
                  '|---|---:|---:|---:|---:|---:|']
        for arm, item in items.items():
            lines.append('| '+arm+' | '+' | '.join(pct(item[k]) for k in ['accuracy', 'balanced_accuracy', 'within_person_balanced_accuracy', 'low_recall', 'high_recall'])+' |')
        item = items['generic_constant']
        lines += ['', f'This subset has {item["people"]} people, {item["tasks"]} tasks, {item["windows"]} windows and {item["people_with_both_classes"]} people with both classes.', '']
    lines += ['## Limits and artifacts', '',
              'Lab2 has already appeared in prior development experiments, so this is a reused development comparison, not a fresh external test. Source stress coverage is sparse in Lab1. Single-class calibration produces explicitly marked constant artifacts. Rest exclusion is a descriptive task-context check and cannot supply missing classes or justify model selection.', '',
              'No readiness or fatigue reference was created. No claim about employees, individual health, diagnosis, live monitoring or deployment follows from these results. More signal windows cannot supply missing independent target answers.', '',
              'The protocol is [012-stress-protocol.json](012-stress-protocol.json). Prepared data, source-line provenance, selections, predictions and non-production artifacts live in ignored `data/prepared/stress-v1/`, `results/stress-v1/` and `models/stress-v1/`. The verifier independently recalculates metrics, checks person/task/session separation, confirms preserved files and replays saved model predictions.', '',
              'Run `.venv/bin/python scripts/run_stress_benchmark.py verify` from the engine directory to inspect the completed artifacts. Stages are `prepare`, `select`, `evaluate`, `report`, `verify`; completed preparation, selection and evaluation refuse replacement.', '']
    (root/'experiments/012-stress-results.md').write_text('\n'.join(lines))
    print(json.dumps({'paired_people': len(audit['paired_people']), 'both_lab2_classes': both,
                      'selected': {arm: {k: results['all_paired'][arm][k] for k in ('accuracy', 'balanced_accuracy', 'within_person_balanced_accuracy')}
                                   for arm in ('generic_selected', 'personal_selected', 'hybrid_selected')}}), flush=True)
    return result


def verify(root):
    out = root/OUT; selection = _read(out/'frozen-selection.json'); run = selection['run']; _check_frozen(root, run)
    audit = _read(root/PREPARED/'audit.json'); evaluation = _read(out/'evaluation.json'); document = _read(out/'report.json')
    assert evaluation['selection_sha256'] == sha(out/'frozen-selection.json')
    assert document['evaluation_sha256'] == sha(out/'evaluation.json')
    assert sha(root/'data/prepared/transfer-v1/universe.csv.gz') == audit['source_sha256']
    assert sha(root/'data/prepared/causal-v3/provenance.json') == audit['source_provenance_sha256']
    assert sha(root/'data/universe/manifest.json') == audit['manifest_sha256']
    assert sha(root/PREPARED/'label-provenance.json') == audit['label_provenance_sha256']
    source_cache = {}
    for member, info in audit['sources'].items():
        path = root/'data/universe/extracted'/member; assert sha(path) == info['sha256']
        source_cache[member] = parse_questionnaire(path.read_bytes())[0]
    provenance = {r['unit_id']: r for r in _read(root/PREPARED/'label-provenance.json')}
    train, future = load_frame(root, 'lab1'), load_frame(root, 'lab2')
    original = pd.read_csv(root/'data/prepared/transfer-v1/universe.csv.gz'); original['row_id'] = original.index
    original = original.set_index('row_id', verify_integrity=True)
    for frame in (train, future):
        assert not set(frame.participant) & set(audit['original_test_excluded'])
        np.testing.assert_allclose(frame[FEATURES], original.loc[frame.row_id, FEATURES], rtol=0, atol=1e-10, equal_nan=True)
        for unit, group in frame.groupby('unit_id'):
            p = provenance[unit]; source = source_cache[p['label_source']][p['segment']]
            assert source['value'] == p[TARGET] and source['lines'] == p['source_lines']
            assert set(group[TARGET]) == {p[TARGET]}
            np.testing.assert_array_equal(group.outcome, binary_labels(group[TARGET]))
    assert not set(train.row_id) & set(future.row_id)
    assert {j['person'] for j in evaluation['jobs']} == set(audit['paired_people'])
    assert len(evaluation['jobs']) == len(audit['paired_people'])
    for chosen in selection['selections']:
        ids = run['folds'][int(chosen['key'])] if chosen['mode'] == 'generic' else [chosen['key']]
        fitting = train[~train.participant.isin(ids)] if chosen['mode'] == 'generic' else train[train.participant.isin(ids)]
        assert set(chosen['training_people']) == set(fitting.participant)
        assert set(chosen['training_units']) == set(fitting.unit_id)
        for fold in chosen['folds']:
            assert not set(fold['training_units']) & set(fold['validation_units'])
            assert set(fold['training_units']) | set(fold['validation_units']) == set(fitting.unit_id)
            if chosen['mode'] == 'generic':
                assert not set(fold['training_people']) & set(fold['validation_people'])
        if chosen['candidates']:
            best = max(chosen['candidates'], key=lambda r: -1 if r['balanced_accuracy'] is None else r['balanced_accuracy'])
            assert chosen['config'] == best['config']
    replayed = 0
    for job in evaluation['jobs']:
        saved = pd.read_csv(root/job['prediction_file']); assert sha(root/job['prediction_file']) == job['predictions_sha256']
        person = job['person']; selected_future = future[future.participant == person]
        saved, selected_future = align_pair(saved, selected_future)
        assert set(saved.session) == {'Lab2'} and set(saved.participant) == {person}
        excluded = run['folds'][job['fold']]; assert person in excluded
        generic = train[~train.participant.isin(excluded)]; personal = train[train.participant == person]
        frames = {'generic': generic, 'personal': personal, 'hybrid': pd.concat([generic, personal], ignore_index=True)}
        for mode in ('generic', 'personal'):
            majority = int(frames[mode].groupby(['participant', 'unit_id']).outcome.mean().groupby('participant').mean().mean() > .5)
            np.testing.assert_array_equal(saved[mode+'_constant'], np.full(len(saved), majority))
        assert {r['arm'] for r in job['artifacts']} == set(LEARNED)
        for record in job['artifacts']:
            path = root/record['file']; assert sha(path) == record['sha256']; artifact = joblib.load(path)
            mode, variant = record['arm'].split('_'); fitting = frames[mode]
            assert artifact['production_enabled'] is False and artifact['deployment_approved'] is False
            assert artifact['training_session'] == 'Lab1' and artifact['target'] == TARGET
            assert artifact['columns'] == list(FEATURES) and artifact['evidence_seconds'] == 60
            assert artifact['personal_id'] == (person if mode == 'hybrid' else None)
            assert set(artifact['training_people']) == set(fitting.participant)
            assert set(artifact['training_units']) == set(fitting.unit_id)
            assert artifact['fitting_row_ids'] == thin(fitting).row_id.tolist()
            assert artifact['config'] == record['config']
            if variant == 'fixed':
                assert artifact['config']['algorithm'] == 'logit1'
            else:
                key = person if mode == 'personal' else job['fold']; smode = 'personal' if mode == 'personal' else 'generic'
                matches = [s for s in selection['selections'] if s['mode'] == smode and str(s['key']) == str(key)]
                assert len(matches) == 1 and artifact['config'] == matches[0]['config']
            changed = selected_future.copy(); changed['outcome'] = 1-changed.outcome; changed[TARGET] = -999
            changed['participant'] = 'not_a_predictor'; changed['session'] = 'not_a_predictor'; changed['segment'] = 'not_a_predictor'
            with threadpool_limits(limits=1):
                np.testing.assert_allclose(prior.predict(artifact, changed), saved[record['arm']], rtol=0, atol=1e-12)
            replayed += 1
    frame = predictions(root); assert len(frame) == audit['lab2_scored_windows']
    checks = 0
    for name, part in {'all_paired': frame, 'active_tasks_only': frame[frame.segment != 'relaxation_video']}.items():
        for arm in ARMS:
            independent = independent_metrics(part, arm); assert independent == document['groups'][name][arm]
            if not part.empty:
                other = prior.metrics(part, part[arm])
                for key in ('accuracy', 'balanced_accuracy', 'within_person_balanced_accuracy', 'low_recall', 'high_recall'):
                    if independent[key] is None:
                        assert other[key] is None
                    else:
                        np.testing.assert_allclose(independent[key], other[key], rtol=0, atol=1e-12)
                    checks += 1
    result = {'status': 'passed', 'independent_metric_checks': checks, 'model_prediction_replays': replayed,
              'preserved_files_unchanged': len(run['preserved_files']), 'source_labels_and_feature_whitelist_verified': True,
              'selection_and_fitting_Lab1_only': True, 'production_enabled': False, 'report_sha256': sha(out/'report.json')}
    write_json(out/'verification.json', result); print(json.dumps(result), flush=True)
    return result
