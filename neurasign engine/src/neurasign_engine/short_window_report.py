"""Independent reporting and saved-artifact audit for experiment 011."""
from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

from .personalization import ARMS, metrics as training_metrics
from .schema import SEED
from .transfer_training import sha, thin, write_json

PROFILES = ('short1', 'short60', 'legacy60')
TARGETS = ('mental_demand', 'mental_effort')
LEARNED = tuple(a for a in ARMS if not a.endswith('constant'))
GROUPS = ('all_paired', 'adequate_calibration', 'active_tasks_only')
IDENTITY = ['row_id', 'participant', 'session', 'unit_id', 'source_end', 'window_end', 'outcome']


def independent_metrics(frame, arm):
    """Average task confusion matrices within people, then average people equally."""
    if frame.empty:
        return {'accuracy': None, 'balanced_accuracy': None, 'within_person_balanced_accuracy': None,
                'low_recall': None, 'high_recall': None, 'people': 0, 'people_with_both_classes': 0,
                'tasks': 0, 'windows': 0, 'per_person': {}, 'confusion_matrix_person_task_weighted': [[0., 0.], [0., 0.]]}
    scores = frame[arm].to_numpy(float)
    if not np.isfinite(scores).all() or ((scores < 0) | (scores > 1)).any():
        raise ValueError('Predictions must be finite scores between zero and one')
    if not frame.outcome.isin([0, 1]).all() or frame.groupby('unit_id').outcome.nunique().max() != 1:
        raise ValueError('Each task must carry one observed binary outcome')
    people = {};cm = np.zeros((2, 2))
    for person, rows in frame.groupby('participant'):
        pc = np.zeros((2, 2))
        for _, task in rows.groupby('unit_id'):
            local = np.zeros((2, 2))
            np.add.at(local, (task.outcome.to_numpy(int), (task[arm].to_numpy() >= .5).astype(int)), 1/len(task))
            pc += local/rows.unit_id.nunique()
        recall = [float(pc[i, i]/pc[i].sum()) if pc[i].sum() else None for i in (0, 1)]
        people[person] = {'accuracy': float(np.trace(pc)),
                         'balanced_accuracy': float(np.mean(recall)) if all(v is not None for v in recall) else None,
                         'low_recall': recall[0], 'high_recall': recall[1],
                         'tasks': int(rows.unit_id.nunique()), 'windows': len(rows)}
        cm += pc/frame.participant.nunique()
    recall = [float(cm[i, i]/cm[i].sum()) if cm[i].sum() else None for i in (0, 1)]
    balanced = [v['balanced_accuracy'] for v in people.values() if v['balanced_accuracy'] is not None]
    return {'accuracy': float(np.trace(cm)),
            'balanced_accuracy': float(np.mean(recall)) if all(v is not None for v in recall) else None,
            'within_person_balanced_accuracy': float(np.mean(balanced)) if balanced else None,
            'low_recall': recall[0], 'high_recall': recall[1], 'people': len(people),
            'people_with_both_classes': len(balanced), 'tasks': int(frame.unit_id.nunique()),
            'windows': len(frame), 'per_person': people, 'confusion_matrix_person_task_weighted': cm.tolist()}


def align_pair(candidate, baseline):
    """Refuse a duration comparison unless it uses identical observations and labels."""
    for frame in (candidate, baseline):
        if frame.row_id.duplicated().any():
            raise ValueError('Paired predictions contain duplicate row IDs')
    left = candidate.sort_values('row_id').reset_index(drop=True)
    right = baseline.sort_values('row_id').reset_index(drop=True)
    if len(left) != len(right):
        raise ValueError('Paired predictions have different observation counts')
    for key in IDENTITY:
        same = (np.allclose(left[key].to_numpy(), right[key].to_numpy(), rtol=0, atol=1e-6)
                if key in ('source_end', 'window_end') else np.array_equal(left[key].to_numpy(), right[key].to_numpy()))
        if not same:
            raise ValueError('Paired predictions disagree on '+key)
    return left, right


def paired_metrics(candidate, baseline, metric='balanced_accuracy'):
    if set(candidate['per_person']) != set(baseline['per_person']):
        raise ValueError('Paired metrics must contain the same participants')
    people = sorted(p for p, v in candidate['per_person'].items()
                    if v[metric] is not None and baseline['per_person'][p][metric] is not None)
    if not people:
        return {'people': 0, 'participants': [], 'mean_difference': None, 'percentile_95_ci': None,
                'metric': metric, 'people_improved': 0, 'people_worse': 0}
    differences = np.array([candidate['per_person'][p][metric]-baseline['per_person'][p][metric] for p in people])
    samples = np.random.default_rng(SEED).choice(differences, (10000, len(people)), replace=True).mean(axis=1)
    return {'people': len(people), 'participants': people, 'mean_difference': float(differences.mean()),
            'percentile_95_ci': np.quantile(samples, [.025, .975]).tolist(), 'metric': metric,
            'people_improved': int((differences > 1e-12).sum()), 'people_worse': int((differences < -1e-12).sum()),
            'interpretation': 'Exploratory paired-person bootstrap; repeated development data, uncorrected comparisons.'}


def duration_effect(candidate, baseline, arm):
    candidate, baseline = align_pair(candidate, baseline)
    return {metric: paired_metrics(independent_metrics(candidate, arm), independent_metrics(baseline, arm), metric)
            for metric in ('accuracy', 'balanced_accuracy')}


def predictions(root, profile, target):
    out = root/'results/short-window-v1'
    evaluation = json.loads((out/'evaluation.json').read_text())
    parts = []
    for job in evaluation['jobs']:
        if job['profile'] == profile and job['target'] == target:
            path = root/job['prediction_file']
            assert sha(path) == job['predictions_sha256']
            parts.append(pd.read_csv(path))
    if not parts:
        raise ValueError(f'No saved predictions for {profile}/{target}')
    result = pd.concat(parts, ignore_index=True).sort_values('row_id').reset_index(drop=True)
    if result.row_id.duplicated().any():
        raise ValueError('Evaluation jobs duplicated predictions')
    return result


def subsets(frame, target_audit, resting):
    return {'all_paired': frame,
            'adequate_calibration': frame[frame.participant.isin(target_audit['adequately_calibrated_people'])],
            'active_tasks_only': frame[~frame.unit_id.isin(resting)]}


def references(root):
    audit = json.loads((root/'data/prepared/personalization-v1/audit.json').read_text())
    provenance = json.loads((root/'data/prepared/causal-v3/provenance.json').read_text())
    resting = {p['unit_id'] for p in provenance if p['segment'].split('/')[-1] == 'relaxation_video'}
    return audit, resting


def percent(value):
    return 'n/a' if value is None else f'{value:.1%}'


def difference(value):
    if value['mean_difference'] is None:
        return 'n/a'
    low, high = value['percentile_95_ci']
    return f"{100*value['mean_difference']:+.1f} [{100*low:+.1f}, {100*high:+.1f}]"


def report(root):
    root = Path(root);out = root/'results/short-window-v1'
    audit, resting = references(root)
    feature_audit = json.loads((root/'data/prepared/short-window-v1/audit.json').read_text())
    availability = [{'evidence_seconds': int(width), 'feature': feature, 'finite_rows': count,
                     'matched_rows': feature_audit['rows'], 'fraction_available': count/feature_audit['rows']}
                    for width, info in feature_audit['quality'].items()
                    for feature, count in info['finite_rows_by_feature'].items()]
    pd.DataFrame(availability).to_csv(out/'feature-availability.csv', index=False)
    targets = {};flat = [];deltas = []
    for target in TARGETS:
        frames = {p: predictions(root, p, target) for p in PROFILES}
        align_pair(frames['short1'], frames['short60']);align_pair(frames['short1'], frames['legacy60'])
        groups = {p: subsets(frame, audit['targets'][target], resting) for p, frame in frames.items()}
        summaries = {p: {name: {'arms': {a: independent_metrics(group, a) for a in ARMS}}
                        for name, group in by_group.items()} for p, by_group in groups.items()}
        effects = {name: {a: duration_effect(groups['short1'][name], groups['short60'][name], a)
                          for a in LEARNED} for name in GROUPS}
        targets[target] = {'profiles': summaries, 'duration_effect_short1_minus_short60': effects,
                           'coverage': audit['targets'][target]}
        for profile, by_group in summaries.items():
            for population, summary in by_group.items():
                for arm, values in summary['arms'].items():
                    flat.append({'target': target, 'profile': profile, 'population': population, 'arm': arm,
                                 **{k: v for k, v in values.items() if not isinstance(v, (dict, list))}})
        for population, by_arm in effects.items():
            for arm, by_metric in by_arm.items():
                for metric, values in by_metric.items():
                    interval = values['percentile_95_ci'] or [None, None]
                    deltas.append({'target': target, 'population': population, 'arm': arm, 'metric': metric,
                                   'people': values['people'], 'short1_minus_short60': values['mean_difference'],
                                   'ci_low': interval[0], 'ci_high': interval[1]})
        for profile, frame in frames.items():
            frame.to_csv(out/f'{profile}-{target}-all-predictions.csv.gz', index=False, compression={'method': 'gzip', 'mtime': 0})
    document = {'targets': targets, 'feature_availability': availability,
                'frozen_selection_sha256': sha(out/'frozen-selection.json'),
                'evaluation_sha256': sha(out/'evaluation.json'),
                'protocol_sha256': sha(root/'experiments/011-short-window-protocol.json'),
                'data_audit_sha256': sha(root/'data/prepared/short-window-v1/audit.json'),
                'reference_010_audit_sha256': sha(root/'data/prepared/personalization-v1/audit.json')}
    write_json(out/'report.json', document)
    table = pd.DataFrame(flat);table.to_csv(out/'comparison.csv', index=False)
    pd.DataFrame(deltas).to_csv(out/'duration-effects.csv', index=False)
    lines = ['# Experiment 011: one second versus sixty seconds of sensor evidence', '',
             '**Lab1 fitting and selection; the same Lab2 observations in all comparisons. Development research only.**', '',
             'This experiment changes the amount of evidence consumed per prediction, not the output cadence. '
             'The matched profiles use exactly the same 23 statistics of BVP, EDA, skin temperature and acceleration '
             'over [end−1, end) or [end−60, end). They use no history, HRV, vendor heart rate, or filter state from outside the window. '
             'Predictions remain at the original ten-second endpoints to hold rows and fitting volume fixed. '
             'The historical 60-second, 28-feature profile is an additional control; its feature set also changes, so it cannot isolate duration.', '',
             'Vendor heart rate is excluded from both matched profiles because [Empatica documents ten-second averaging]'
             '(https://www.empatica.com/blog/decoding-wearable-sensor-signals-what-to-expect-from-your-e4-data/). '
             'One timestamped HR output would otherwise import evidence older than one second.', '',
             '## Population and label coverage', '',
             '| Target | Paired people | Adequately calibrated | Scored Lab2 windows / all available | Coverage within paired people |',
             '|---|---:|---:|---:|---:|']
    for target in TARGETS:
        a = audit['targets'][target]
        lines.append(f"| {target} | {len(a['paired_people'])} | {len(a['adequately_calibrated_people'])} | "
                     f"{a['lab2_scored_windows']:,} / {a['lab2_total_windows']:,} | {a['lab2_scored_windows']/a['lab2_windows_in_paired_people']:.1%} |")
    lines += ['', f"Both matched feature tables retain {feature_audit['rows']:,} union rows across {feature_audit['units']} tasks. "
              f"Across their 23 features, observed availability ranges from {min(v['fraction_available'] for v in availability):.1%} "
              f"to {max(v['fraction_available'] for v in availability):.1%}; per-feature counts are in `feature-availability.csv`. "
              'These counts describe the matched, previously eligible rows, not all raw sensor time.', '',
              'Mental demand uses questionnaire ≤33⅓ versus ≥66⅔; mental effort uses ratings 1–2 versus 4–5. '
              'Neutral and missing ratings remain excluded. Mental effort has only two paired people and cannot support a population conclusion. '
              'No new model is selected from Lab2 results.', '', '## All paired people', '',
              'Accuracy weights people equally and tasks equally within people. Within-person balanced accuracy averages low/high recall '
              'within each person before averaging people with both classes. Low/high recall columns use the aggregate person/task weights; '
              'their average can differ from the within-person balanced measure.', '']
    for target in TARGETS:
        lines += [f'### {target}', '', '| Profile | Arm | Accuracy | Within-person balanced accuracy | Low recall | High recall |',
                  '|---|---|---:|---:|---:|---:|']
        for profile in PROFILES:
            for arm in ARMS:
                m = targets[target]['profiles'][profile]['all_paired']['arms'][arm]
                lines.append(f"| {profile} | {arm} | {percent(m['accuracy'])} | {percent(m['within_person_balanced_accuracy'])} | {percent(m['low_recall'])} | {percent(m['high_recall'])} |")
        lines += ['', '| Arm | One second minus sixty seconds, points [95% interval] | Paired people with both classes |',
                  '|---|---:|---:|']
        for arm in LEARNED:
            m = targets[target]['duration_effect_short1_minus_short60']['all_paired'][arm]['balanced_accuracy']
            lines.append(f"| {arm} | {difference(m)} | {m['people']} |")
        lines += ['']
    lines += ['## Prespecified subgroup checks', '',
              'These subsets reuse saved predictions without refitting. Adequate calibration requires two Lab1 tasks per class. '
              'Active-only excludes the relaxation video. Counts explicitly show people retaining both Lab2 classes.', '',
              '| Target | Group | Arm | People (both classes) | 1s balanced | 60s balanced | Difference, points [95% interval] |',
              '|---|---|---|---:|---:|---:|---:|']
    for target in TARGETS:
        for group in GROUPS[1:]:
            for arm in LEARNED:
                left = targets[target]['profiles']['short1'][group]['arms'][arm]
                right = targets[target]['profiles']['short60'][group]['arms'][arm]
                effect = targets[target]['duration_effect_short1_minus_short60'][group][arm]['balanced_accuracy']
                lines.append(f"| {target} | {group} | {arm} | {left['people']} ({left['people_with_both_classes']}) | "
                             f"{percent(left['within_person_balanced_accuracy'])} | {percent(right['within_person_balanced_accuracy'])} | {difference(effect)} |")
    lines += ['', '## Interpretation and reproducibility', '',
              '- Fixed arms use logistic regression C=1. Selected arms choose among logistic C=1, RBF SVM C=1, ExtraTrees and CatBoost using Lab1 alone. '
              'General selection holds out people; personal selection holds out whole tasks; hybrid uses the general selection. '
              'A maximum of 20 rows per training task and the original person/task/class balancing are shared across profiles.',
              '- Bootstrap intervals resample paired people 10,000 times, never individual windows. They are exploratory, uncorrected for multiple comparisons, '
              'and do not establish equivalence if they include zero. A selected-model difference also includes the effect of independent Lab1 model selection; fixed arms hold the algorithm constant.',
              '- Task-level questionnaires are not one-second ground truth. The same task families recur across sessions. '
              'This experiment cannot establish one-second response latency, change detection, workplace validity, or cross-device performance.',
              '- One second means samples in the released, offline-aligned recording. Sensor transfer functions and the authors’ clock synchronization are not validated here. '
              'Rows inherit the earlier 60-second quality/availability screen, so this is a matched-row duration test, not an independent assessment of first-second startup or deployment coverage.',
              '- Labeled Lab1 calibration still spans complete tasks. Shorter inference windows do not establish a one-second onboarding procedure. '
              'Lab2 has been used in earlier development experiments; original UNIVERSE held-out people and Mobile test data are not used for fitting or selection.',
              '- No production, phone or dashboard integration is enabled. These artifacts are research models, and scores are not calibrated confidence.', '',
              'Protocol: [011-short-window-protocol.json](011-short-window-protocol.json). '
              'Saved predictions, per-person metrics, duration intervals and CSV/PNG/PDF comparisons are in `results/short-window-v1/`; '
              'artifacts are in `models/short-window-v1/`. `verification.json` records independent metric checks and exact saved-artifact prediction replays.', '']
    (root/'experiments/011-short-window-results.md').write_text('\n'.join(lines))
    draw(out, targets)
    print(table[(table.target == 'mental_demand') & (table.population == 'all_paired')][
        ['profile', 'arm', 'accuracy', 'within_person_balanced_accuracy']].to_string(index=False), flush=True)


def draw(out, targets):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(12, 5.5), constrained_layout=True)
    arms = ['generic_fixed', 'personal_fixed', 'hybrid_fixed', 'generic_selected', 'personal_selected', 'hybrid_selected']
    labels = ['General fixed', 'Personal fixed', 'Hybrid fixed', 'General selected', 'Personal selected', 'Hybrid selected']
    for ax, group, title in zip(axes, ['all_paired', 'active_tasks_only'], ['All eligible tasks', 'Active tasks only']):
        for index, (profile, label, color) in enumerate(zip(PROFILES, ['1s · matched features', '60s · matched features', '60s · historical features'], ['#0d9488', '#2563eb', '#94a3b8'])):
            values = [targets['mental_demand']['profiles'][profile][group]['arms'][a]['within_person_balanced_accuracy'] for a in arms]
            ax.barh(np.arange(len(arms))+(index-1)*.24, [np.nan if v is None else 100*v for v in values],
                    height=.22, label=label, color=color)
        ax.set_yticks(np.arange(len(arms)), labels);ax.invert_yaxis();ax.set_xlim(0, 100)
        ax.axvline(50, color='#475569', linestyle=':', linewidth=1)
        n = targets['mental_demand']['profiles']['short1'][group]['arms']['generic_fixed']['people_with_both_classes']
        ax.set_title(f'{title} · {n} people with both classes');ax.set_xlabel('Within-person balanced accuracy (%)')
        ax.spines[['top', 'right']].set_visible(False)
    axes[0].legend(loc='lower right', fontsize=8)
    fig.suptitle('NEURASIGN · Evidence duration\nMental demand · Lab1 → Lab2 · development research', fontsize=14)
    fig.savefig(out/'comparison.png', dpi=180);fig.savefig(out/'comparison.pdf');plt.close(fig)


def verify(root):
    from . import short_window as experiment
    root = Path(root);out = root/'results/short-window-v1'
    selection = json.loads((out/'frozen-selection.json').read_text())
    evaluation = json.loads((out/'evaluation.json').read_text())
    document = json.loads((out/'report.json').read_text())
    audit, resting = references(root);run = selection['run']
    assert sha(Path(experiment.__file__)) == run['training_code_sha256']
    assert sha(root/'experiments/011-short-window-protocol.json') == run['protocol_sha256'] == document['protocol_sha256']
    assert sha(root/'data/prepared/short-window-v1/audit.json') == run['data_audit_sha256'] == document['data_audit_sha256']
    assert sha(out/'frozen-selection.json') == evaluation['selection_sha256'] == document['frozen_selection_sha256']
    assert sha(out/'evaluation.json') == document['evaluation_sha256']
    assert sha(Path(experiment.__file__).with_name('short_window_features.py')) == run['feature_code_sha256']
    for name, digest in run['feature_files'].items():
        assert sha(root/'data/prepared/short-window-v1'/name) == digest
    assert sha(root/'data/prepared/personalization-v1/audit.json') == document['reference_010_audit_sha256']
    feature_tables = {width: pd.read_csv(root/f'data/prepared/short-window-v1/window-{width}.csv.gz') for width in (1, 60)}
    for entry in document['feature_availability']:
        source = feature_tables[entry['evidence_seconds']]
        assert len(source) == entry['matched_rows']
        assert int(np.isfinite(source[entry['feature']]).sum()) == entry['finite_rows']
        assert entry['fraction_available'] == entry['finite_rows']/entry['matched_rows']
    for path, digest in run['preserved_files'].items():
        assert sha(root/path) == digest, 'Previously frozen file changed: '+path
    assert tuple(experiment.feature_columns('short1')) == tuple(experiment.feature_columns('short60'))
    assert len(experiment.feature_columns('short1')) == 23
    forbidden = {'outcome', 'participant', 'session', 'unit_id', 'source_end', 'window_end', 'row_id', *TARGETS}
    for profile in PROFILES:
        cols = experiment.feature_columns(profile)
        assert not set(cols) & forbidden and not any('__delta' in col for col in cols)
        if profile != 'legacy60':
            assert not any(any(word in col for word in ('heart_rate', 'interval', 'hrv', 'reference')) for col in cols)
    frames = {(p, t, s): experiment.load_frame(root, p, t, s) for p in PROFILES for t in TARGETS for s in ('lab1', 'lab2')}
    for target in TARGETS:
        for session in ('lab1', 'lab2'):
            base = frames['short1', target, session]
            assert set(base.session) == {session.capitalize()}
            for profile in PROFILES[1:]:
                align_pair(base, frames[profile, target, session])
    for chosen in selection['selections']:
        train = frames[chosen['profile'], chosen['target'], 'lab1']
        expected = train[~train.participant.isin(run['folds'][int(chosen['key'])])] if chosen['mode'] == 'generic' else train[train.participant == chosen['key']]
        assert set(chosen['training_units']) == set(expected.unit_id)
        assert set(chosen['training_people']) == set(expected.participant)
        for fold in chosen['folds']:
            assert not set(fold['training_units']) & set(fold['validation_units'])
            assert set(fold['training_units']) | set(fold['validation_units']) == set(expected.unit_id)
            if chosen['mode'] == 'generic':
                assert not set(fold['training_people']) & set(fold['validation_people'])
        if chosen['candidates']:
            best = max(chosen['candidates'], key=lambda c: -1 if c['balanced_accuracy'] is None else c['balanced_accuracy'])
            assert best['config'] == chosen['config']
    expected_jobs = {(p, t, person) for p in PROFILES for t in TARGETS for person in audit['targets'][t]['paired_people']}
    actual_jobs = [(j['profile'], j['target'], j['person']) for j in evaluation['jobs']]
    assert set(actual_jobs) == expected_jobs and len(actual_jobs) == len(expected_jobs)
    replayed = 0
    with threadpool_limits(limits=1):
        for job in evaluation['jobs']:
            p, t, person = job['profile'], job['target'], job['person']
            assert sha(root/job['prediction_file']) == job['predictions_sha256']
            saved = pd.read_csv(root/job['prediction_file'])
            train = frames[p, t, 'lab1'];future = frames[p, t, 'lab2']
            future = future[future.participant == person]
            saved, future = align_pair(saved, future)
            assert set(saved.session) == {'Lab2'} and set(saved.participant) == {person}
            assert not set(saved.row_id) & set(train.row_id)
            generic = train[~train.participant.isin(run['folds'][job['fold']])]
            personal = train[train.participant == person]
            by_mode = {'generic': generic, 'personal': personal, 'hybrid': pd.concat([generic, personal], ignore_index=True)}
            for mode in ('generic', 'personal'):
                one = by_mode[mode]
                majority = int(one.groupby(['participant', 'unit_id']).outcome.mean().groupby('participant').mean().mean() > .5)
                np.testing.assert_array_equal(saved[mode+'_constant'], np.full(len(saved), majority))
            assert {r['arm'] for r in job['artifacts']} == set(LEARNED)
            for record in job['artifacts']:
                path = root/record['file'];assert sha(path) == record['sha256']
                artifact = joblib.load(path)  # Locally generated files, verified against frozen checksums.
                assert artifact['production_enabled'] is False and artifact['training_session'] == 'Lab1'
                assert artifact['evidence_seconds'] == (1 if p == 'short1' else 60)
                assert artifact['score_is_calibrated_confidence'] is False
                assert artifact['columns'] == list(experiment.feature_columns(p))
                assert artifact['config'] == record['config'] and artifact['config']['profile'] == p
                mode, variant = record['arm'].split('_');fitting = by_mode[mode]
                assert set(artifact['training_people']) == set(fitting.participant)
                assert set(artifact['training_units']) == set(fitting.unit_id)
                assert set(artifact['fitting_row_ids']) == set(thin(fitting).row_id)
                assert len(artifact['fitting_row_ids']) == len(set(artifact['fitting_row_ids']))
                assert artifact['personal_id'] == (person if mode == 'hybrid' else None)
                if variant == 'fixed':
                    assert artifact['config']['algorithm'] == 'logit1'
                else:
                    selection_mode = 'personal' if mode == 'personal' else 'generic'
                    key = person if mode == 'personal' else job['fold']
                    matches = [s for s in selection['selections'] if s['profile'] == p and s['target'] == t
                               and s['mode'] == selection_mode and str(s['key']) == str(key)]
                    assert len(matches) == 1 and artifact['config'] == matches[0]['config']
                changed = future.copy();changed['outcome'] = 1-changed.outcome;changed[t] = -999
                changed['participant'] = 'not_a_predictor';changed['session'] = 'not_a_predictor'
                np.testing.assert_allclose(experiment.predict(artifact, changed), saved[record['arm']], rtol=0, atol=1e-12)
                replayed += 1
    metric_checks = interval_checks = 0
    for target in TARGETS:
        groups = {}
        for profile in PROFILES:
            frame = predictions(root, profile, target)
            assert len(frame) == audit['targets'][target]['lab2_scored_windows']
            groups[profile] = subsets(frame, audit['targets'][target], resting)
            for name, group in groups[profile].items():
                for arm in ARMS:
                    independent = independent_metrics(group, arm)
                    saved = document['targets'][target]['profiles'][profile][name]['arms'][arm]
                    assert independent == saved
                    if not group.empty:
                        other = training_metrics(group, group[arm])
                        for key in ('accuracy', 'balanced_accuracy', 'within_person_balanced_accuracy', 'low_recall', 'high_recall'):
                            if independent[key] is None:
                                assert other[key] is None
                            else:
                                np.testing.assert_allclose(independent[key], other[key], rtol=0, atol=1e-12)
                            metric_checks += 1
        for name in GROUPS:
            align_pair(groups['short1'][name], groups['short60'][name])
            for arm in LEARNED:
                actual = duration_effect(groups['short1'][name], groups['short60'][name], arm)
                saved = document['targets'][target]['duration_effect_short1_minus_short60'][name][arm]
                assert actual == saved
                interval_checks += 2
    result = {'status': 'passed', 'independent_metric_checks': metric_checks, 'paired_interval_checks': interval_checks,
              'full_prediction_artifact_replays': replayed, 'frozen_files_unchanged': len(run['preserved_files']),
              'matched_rows_labels_and_feature_whitelists_verified': True, 'selection_and_fitting_Lab1_only': True,
              'report_sha256': sha(out/'report.json'), 'verification_code_sha256': sha(Path(__file__))}
    write_json(out/'verification.json', result);print(json.dumps(result), flush=True)
