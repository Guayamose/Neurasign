"""Report and independently verify the frozen across-session personalization trial."""
from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

from . import personalization as experiment
from .schema import SEED
from .transfer_training import sha, write_json


def predictions(root, target):
    out = root/'results/personalization-v1'
    evaluation = json.loads((out/'evaluation.json').read_text())
    parts = []
    for job in evaluation['jobs']:
        if job['target'] == target:
            path = root/job['prediction_file']
            assert sha(path) == job['predictions_sha256']
            parts.append(pd.read_csv(path))
    return pd.concat(parts, ignore_index=True).sort_values('row_id').reset_index(drop=True)


def paired(candidate, baseline, metric):
    people = sorted(p for p, v in candidate['per_person'].items()
                    if v[metric] is not None and baseline['per_person'][p][metric] is not None)
    if not people:
        return {'people': 0, 'mean_improvement': None, 'percentile_95_ci': None}
    delta = np.array([candidate['per_person'][p][metric]-baseline['per_person'][p][metric] for p in people])
    samples = np.random.default_rng(SEED).choice(delta, (10000, len(delta)), replace=True).mean(axis=1)
    return {'people': len(people), 'participants': people, 'mean_improvement': float(delta.mean()),
            'percentile_95_ci': np.quantile(samples, [.025, .975]).tolist(),
            'people_improved': int((delta > 1e-12).sum()), 'people_worse': int((delta < -1e-12).sum()),
            'metric': metric, 'interpretation': 'Exploratory paired participant interval, not fresh-test validation.'}


def summarize(frame):
    if frame.empty:
        return {'arms': {}, 'comparisons': {}, 'research_signal': {}}
    arms = {arm: experiment.metrics(frame, frame[arm]) for arm in experiment.ARMS}
    comparisons = {}
    gates = {}
    for variant in ('fixed', 'selected'):
        for mode in ('personal', 'hybrid'):
            arm = mode+'_'+variant
            comparisons[arm] = {}
            for baseline in ('generic_'+variant, 'personal_constant'):
                comparisons[arm][baseline] = {metric: paired(arms[arm], arms[baseline], metric)
                                             for metric in ('accuracy', 'balanced_accuracy')}
            if variant == 'selected':
                generic = comparisons[arm]['generic_selected']['balanced_accuracy']
                constant = comparisons[arm]['personal_constant']['balanced_accuracy']
                bacc = arms[arm]['within_person_balanced_accuracy']
                gates[arm] = bool(bacc is not None and bacc >= .70 and generic['people'] >= 10
                    and generic['mean_improvement'] >= .05 and generic['percentile_95_ci'][0] > 0
                    and constant['percentile_95_ci'][0] > 0)
    return {'arms': arms, 'comparisons': comparisons, 'research_signal': gates}


def percent(value):
    return 'n/a' if value is None else f'{value:.1%}'


def report(root):
    out = root/'results/personalization-v1'
    audit = json.loads((root/'data/prepared/personalization-v1/audit.json').read_text())
    selection = json.loads((out/'frozen-selection.json').read_text())
    provenance = json.loads((root/'data/prepared/causal-v3/provenance.json').read_text())
    resting = {p['unit_id'] for p in provenance if p['segment'].split('/')[-1] == 'relaxation_video'}
    targets = {}
    flat = []
    for target in experiment.OUTPUTS:
        frame = predictions(root, target)
        adequate = audit['targets'][target]['adequately_calibrated_people']
        groups = {'all_paired': frame, 'adequate_calibration': frame[frame.participant.isin(adequate)],
                  'active_tasks_only': frame[~frame.unit_id.isin(resting)]}
        targets[target] = {name: summarize(group) for name, group in groups.items()}
        for group, summary in targets[target].items():
            for arm, values in summary['arms'].items():
                flat.append({'target': target, 'population': group, 'arm': arm,
                             **{k: v for k, v in values.items() if not isinstance(v, (dict, list))}})
        frame.to_csv(out/(target+'-all-predictions.csv.gz'), index=False, compression={'method': 'gzip', 'mtime': 0})
    write_json(out/'report.json', {'targets': targets, 'data_audit_sha256': sha(root/'data/prepared/personalization-v1/audit.json'),
                                 'frozen_selection_sha256': sha(out/'frozen-selection.json'),
                                 'protocol_sha256': sha(root/'experiments/010-personalization-protocol.json'),
                                 'data_note_sha256': sha(root/'experiments/010-data-audit-note.md')})
    table = pd.DataFrame(flat);table.to_csv(out/'comparison.csv', index=False)
    lines = ['# Experiment 010: personal calibration across laboratory sessions', '',
             '**Lab1 training and selection; Lab2 evaluation. Wrist signals only. Research, not production validation.**', '',
             'The comparison asks whether knowing a person\'s labeled first session helps classify their second session. '
             'Every outcome uses the original questionnaire response. Task names, difficulty, participant IDs, EEG and other questionnaire fields are excluded from predictors.', '',
             '## Population and labels', '',
             'The [preregistered protocol](010-personalization-protocol.json) tests mental effort (1–2 low, 4–5 high) and mental demand (0–33⅓ low, 66⅔–100 high). '
             'Middle responses and missing labels are excluded and their coverage is reported. '
             'The [source-data note](010-data-audit-note.md) records a material limitation discovered before fitting: '
             'the mental-effort question is absent from 15 of the 19 Lab1 source CSVs. Only two people permit the first comparison; '
             '17 permit the separate mental-demand comparison. No missing answer is filled with another target or inferred from task difficulty.', '',
             '| Target | Paired people | People with ≥2 calibration tasks per class | Scored Lab2 windows / all available | Label coverage within paired people |',
             '|---|---:|---:|---:|---:|']
    for target in experiment.OUTPUTS:
        data = audit['targets'][target]
        lines.append(f"| {target} | {len(data['paired_people'])} | {len(data['adequately_calibrated_people'])} | {data['lab2_scored_windows']:,} / {data['lab2_total_windows']:,} | {data['lab2_scored_windows']/data['lab2_windows_in_paired_people']:.1%} |")
    lines += ['', '## Results', '',
              'Accuracy weights people equally, then tasks equally within each person. **Within-person balanced accuracy** '
              'averages low and high recall separately for each person, then averages people who have both classes. '
              'A constant prediction scores 50% on that measure even if high ratings are much more common. '
              'This is two-class discrimination, not exact questionnaire-score prediction or calibrated confidence.', '']
    labels = {'generic_constant': 'Other-person majority', 'personal_constant': 'Own-session majority',
              'generic_fixed': 'General · fixed logistic', 'personal_fixed': 'Personal · fixed logistic',
              'hybrid_fixed': 'Hybrid · fixed logistic', 'generic_selected': 'General · Lab1-selected',
              'personal_selected': 'Personal · Lab1-selected', 'hybrid_selected': 'Hybrid · Lab1-selected'}
    for target in ('mental_demand', 'mental_effort'):
        summary = targets[target]['all_paired']
        lines += [f'### {target}', '', '| Model | Accuracy | Within-person balanced accuracy | Low recall | High recall |',
                  '|---|---:|---:|---:|---:|']
        for arm in experiment.ARMS:
            m = summary['arms'][arm]
            lines.append(f"| {labels[arm]} | {percent(m['accuracy'])} | {percent(m['within_person_balanced_accuracy'])} | {percent(m['low_recall'])} | {percent(m['high_recall'])} |")
        lines += ['', 'Paired differences below use within-person balanced accuracy; positive means the calibrated arm performs better. '
                  'Intervals resample people, not the overlapping windows.', '',
                  '| Calibrated arm | Gain over general (percentage points, 95% interval) | Gain over own-session majority (percentage points, 95% interval) |',
                  '|---|---:|---:|']
        for arm in ['personal_fixed', 'hybrid_fixed', 'personal_selected', 'hybrid_selected']:
            generic = 'generic_'+arm.split('_')[1]
            cells = []
            for baseline in (generic, 'personal_constant'):
                result = summary['comparisons'][arm][baseline]['balanced_accuracy']
                if result['people']:
                    low, high = result['percentile_95_ci']
                    cells.append(f"{100*result['mean_improvement']:+.1f} [{100*low:+.1f}, {100*high:+.1f}]")
                else:
                    cells.append('n/a')
            lines.append('| '+labels[arm]+' | '+' | '.join(cells)+' |')
        lines += ['', 'Prespecified provisional research signal: '+', '.join(f"{labels[a]} = {'met' if passed else 'not met'}" for a, passed in summary['research_signal'].items())+'. '
                  'The criterion requires ≥70% balanced accuracy, ≥5-point improvement over general, positive paired intervals against general and the personal constant, and ≥10 evaluated people with both classes. '
                  'It is not a deployment certification.', '']
    lines += ['## Coverage and context checks', '',
              'The following restrictions were specified before outcome inspection and use the same saved predictions, without refitting or selecting a winner.', '',
              '| Target / subgroup | Evaluated people (both classes) | General selected | Personal selected | Hybrid selected |',
              '|---|---:|---:|---:|---:|']
    for target in experiment.OUTPUTS:
        for group in ['adequate_calibration', 'active_tasks_only']:
            arms = targets[target][group]['arms'];m = arms['generic_selected']
            values = [percent(arms[a]['within_person_balanced_accuracy']) for a in ['generic_selected', 'personal_selected', 'hybrid_selected']]
            lines.append(f"| {target} / {group} | {m['people']} ({m['people_with_both_classes']}) | "+' | '.join(values)+' |')
    lines += ['', 'Adequate calibration means at least two labeled Lab1 tasks per class. Active-only excludes the relaxation video. '
              'People with only one remaining class still contribute to accuracy and coverage but cannot support a within-person two-class balanced accuracy.', '',
              '## Calibration burden and fitting', '']
    for target in experiment.OUTPUTS:
        records = list(audit['targets'][target]['people'].values())
        minutes = [v['calibration_evidence_minutes'] for v in records]
        tasks = [v['lab1_tasks_low']+v['lab1_tasks_high'] for v in records]
        lines.append(f"- {target}: median {np.median(minutes):.1f} minutes of labeled physiological evidence (range {min(minutes):.1f}–{max(minutes):.1f}), "
                     f"median {np.median(tasks):.1f} labeled tasks, {sum(v['single_class_calibration'] for v in records)} people with only one calibration class. "
                     'Minutes are the union of observed evidence intervals, not the sum of overlapping windows.')
    fits = sum(len(s['candidates'])*len(s['folds']) for s in selection['selections'])
    evaluated = sum(len(audit['targets'][t]['paired_people']) for t in experiment.OUTPUTS)
    lines += ['', f'The bounded search used {fits} Lab1 candidate fold fits and {evaluated*6} final learned-arm fits/fallbacks. '
              'The same fixed logistic model is reported in all arms to isolate personalization from model choice. '
              'The additional selected models consider logistic regression, RBF SVM, ExtraTrees and CatBoost with raw or history-relative feature profiles. '
              'General selection uses person-disjoint Lab1 folds; personal selection uses whole-task Lab1 folds. '
              'Insufficient calibration groups trigger the declared fixed-model or single-class fallback. '
              'Hybrid fitting allocates half the pre-class-balancing weight to own Lab1 and half to other people.', '',
              '## Interpretation limits', '',
              '- Original five UNIVERSE test people and the Mobile test remain closed. Lab2 has appeared in prior development experiments, so this is a new session-separated development comparison, not fresh independent validation.',
              '- Both sessions repeat the same experimental task families. Success here would not prove transfer to arbitrary workplace activities, other wearable brands or unseen task types.',
              '- Ratings label whole tasks; repeating them on 60-second windows does not create instantaneous ground truth. Low/high cutoffs omit ambiguous middle ratings rather than solving them.',
              '- Personalization requires labeled calibration. This experiment uses the available first session and does not establish that a few onboarding minutes suffice. The phone app remains a sensor gateway.',
              '- The UNIVERSE publication\'s 71%/74% figures use a different personalized multimodal protocol including EEG and different labels/splits. They are not a directly comparable target for this wrist-only session transfer.', '',
              '## Reproduce and inspect', '', 'From `neurasign engine/`, with the existing `requirements-transfer.txt` environment:', '',
              '```bash', '.venv/bin/python scripts/run_personalization.py prepare',
              'OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python scripts/run_personalization.py select',
              'OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python scripts/run_personalization.py evaluate',
              '.venv/bin/python scripts/run_personalization.py report',
              '.venv/bin/python scripts/run_personalization.py verify', '```', '',
              'The evaluation stage refuses to overwrite an existing evaluation manifest. Predictions, individual results, '
              'candidate selections and the comparison figure are in ignored `results/personalization-v1/`; trained research artifacts '
              'are in ignored `models/personalization-v1/`. No interpretation was integrated into the product.', '',
              'Reference: [UNIVERSE original study](https://doi.org/10.1038/s41597-024-03738-7), '
              '[author code](https://github.com/HPI-CH/UNIVERSE). This is an adapted experiment, not an exact replication of the authors\' code.', '']
    (root/'experiments/010-personalization-results.md').write_text('\n'.join(lines))
    draw(out, targets)
    print(table[(table.target == 'mental_demand') & (table.population == 'all_paired')][
        ['arm', 'accuracy', 'within_person_balanced_accuracy', 'low_recall', 'high_recall']].to_string(index=False), flush=True)


def draw(out, targets):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8), constrained_layout=True)
    modes = ['personal_constant', 'generic_selected', 'personal_selected', 'hybrid_selected']
    labels = ['Own-session majority', 'General model', 'Personal model', 'Hybrid model']
    for ax, group, title in zip(axes, ['all_paired', 'active_tasks_only'], ['All eligible tasks', 'Active tasks only']):
        arms = targets['mental_demand'][group]['arms']
        values = [100*arms[a]['within_person_balanced_accuracy'] for a in modes]
        ax.barh(labels, values, color=['#9ca3af', '#2563eb', '#0d9488', '#7c3aed'])
        ax.invert_yaxis();ax.set_xlim(0, 100);ax.axvline(50, color='#475569', linestyle=':', linewidth=1)
        ax.set_xlabel('Within-person balanced accuracy (%)')
        ax.set_title(title+f" · {arms[modes[0]]['people_with_both_classes']} people with both classes")
        for i, v in enumerate(values):
            ax.text(min(v+1, 94), i, f'{v:.1f}%', va='center')
        ax.spines[['top', 'right']].set_visible(False)
    fig.suptitle('NEURASIGN · Personal calibration\nMental demand · Lab1 training → Lab2 evaluation · development research', fontsize=14)
    fig.savefig(out/'comparison.png', dpi=180);fig.savefig(out/'comparison.pdf');plt.close(fig)


def independent_metrics(frame, arm):
    """Recompute from task-level confusion matrices without the training metrics function."""
    people = {};cm = np.zeros((2, 2))
    for person, group in frame.groupby('participant'):
        pc = np.zeros((2, 2));count = group.unit_id.nunique()
        for _, task in group.groupby('unit_id'):
            y = task.outcome.to_numpy(int);p = (task[arm].to_numpy() >= .5).astype(int)
            local = np.zeros((2, 2));np.add.at(local, (y, p), 1/len(task))
            pc += local/count
        present = pc.sum(1) > 0
        perclass = np.diag(pc)[present]/pc.sum(1)[present]
        people[person] = {'accuracy': float(np.trace(pc)),
                          'balanced_accuracy': float(perclass.mean()) if present.all() else None}
        cm += pc/frame.participant.nunique()
    present = cm.sum(1) > 0
    balanced = [x['balanced_accuracy'] for x in people.values() if x['balanced_accuracy'] is not None]
    return {'accuracy': float(np.trace(cm)), 'balanced_accuracy': float((np.diag(cm)[present]/cm.sum(1)[present]).mean()) if present.all() else None,
            'within_person_balanced_accuracy': float(np.mean(balanced)) if balanced else None, 'per_person': people}


def verify(root):
    out = root/'results/personalization-v1'
    selection = json.loads((out/'frozen-selection.json').read_text())
    evaluation = json.loads((out/'evaluation.json').read_text())
    report_doc = json.loads((out/'report.json').read_text())
    audit = json.loads((root/'data/prepared/personalization-v1/audit.json').read_text())
    assert sha(Path(experiment.__file__)) == selection['run']['training_code_sha256']
    assert sha(out/'frozen-selection.json') == evaluation['selection_sha256']
    assert sha(root/'results/transfer-v1/final/test-report.json') == selection['old_test_report_sha256']
    assert sha(root/'results/papagei-v1/report.json') == selection['old_papagei_report_sha256']
    old = json.loads((root/'experiments/008-final-selection.json').read_text())
    assert all(sha(root/p) == h for p, h in old['code_hashes'].items())
    frames = {t: experiment.load_frame(root, t, 'lab1') for t in experiment.OUTPUTS}
    for chosen in selection['selections']:
        train = frames[chosen['target']]
        assert set(chosen['training_units']) <= set(train.unit_id)
        if chosen['mode'] == 'generic':
            excluded = set(selection['run']['folds'][int(chosen['key'])])
            assert not set(chosen['training_people']) & excluded
        else:
            assert chosen['training_people'] == [chosen['key']]
        for fold in chosen['folds']:
            assert not set(fold['training_units']) & set(fold['validation_units'])
            assert set(fold['training_units']) | set(fold['validation_units']) == set(chosen['training_units'])
            if chosen['mode'] == 'generic':
                assert not set(fold['training_people']) & set(fold['validation_people'])
        if chosen['candidates']:
            best = max(chosen['candidates'], key=lambda c: -1 if c['balanced_accuracy'] is None else c['balanced_accuracy'])
            assert best['config'] == chosen['config']
    replayed = 0
    with threadpool_limits(limits=1):
        for job in evaluation['jobs']:
            saved = pd.read_csv(root/job['prediction_file'])
            assert set(saved.session) == {'Lab2'} and set(saved.participant) == {job['person']}
            train = frames[job['target']]
            future = experiment.load_frame(root, job['target'], 'lab2')
            future = future[future.participant == job['person']]
            np.testing.assert_array_equal(saved.row_id, future.row_id)
            np.testing.assert_array_equal(saved.outcome, future.outcome)
            assert not set(saved.row_id) & set(train.row_id)
            for record in job['artifacts']:
                path = root/record['file'];assert sha(path) == record['sha256']
                artifact = joblib.load(path)  # Locally generated only.
                assert artifact['production_enabled'] is False and artifact['training_session'] == 'Lab1'
                assert set(artifact['fitting_row_ids']) <= set(train.row_id)
                if record['arm'].startswith('generic'):
                    assert not set(artifact['training_people']) & set(selection['run']['folds'][job['fold']])
                elif record['arm'].startswith('personal'):
                    assert artifact['training_people'] == [job['person']]
                else:
                    forbidden = set(selection['run']['folds'][job['fold']])-{job['person']}
                    assert not set(artifact['training_people']) & forbidden
                    assert job['person'] in artifact['training_people']
                # Outcomes and metadata cannot influence inference.
                changed = future.copy();changed['outcome'] = 1-changed.outcome;changed[job['target']] = -999
                result = experiment.predict(artifact, changed)
                np.testing.assert_allclose(result, saved[record['arm']], rtol=0, atol=1e-12)
                replayed += 1
    provenance = json.loads((root/'data/prepared/causal-v3/provenance.json').read_text())
    resting = {p['unit_id'] for p in provenance if p['segment'].split('/')[-1] == 'relaxation_video'}
    metric_checks = interval_checks = 0
    for target in experiment.OUTPUTS:
        frame = predictions(root, target)
        assert not frame.row_id.duplicated().any()
        assert len(frame) == audit['targets'][target]['lab2_scored_windows']
        adequate = audit['targets'][target]['adequately_calibrated_people']
        groups = {'all_paired': frame, 'adequate_calibration': frame[frame.participant.isin(adequate)],
                  'active_tasks_only': frame[~frame.unit_id.isin(resting)]}
        for name, group in groups.items():
            independent = {}
            summary = report_doc['targets'][target][name]
            for arm in experiment.ARMS:
                values = independent_metrics(group, arm);independent[arm] = values
                for key in ('accuracy', 'balanced_accuracy', 'within_person_balanced_accuracy'):
                    a, b = values[key], summary['arms'][arm][key]
                    if a is None:
                        assert b is None
                    else:
                        np.testing.assert_allclose(a, b, rtol=0, atol=1e-12)
                    metric_checks += 1
            for candidate, baselines in summary['comparisons'].items():
                for baseline, recorded in baselines.items():
                    for metric, original in recorded.items():
                        people = sorted(p for p, v in independent[candidate]['per_person'].items()
                                        if v[metric] is not None and independent[baseline]['per_person'][p][metric] is not None)
                        if not people:
                            assert original['people'] == 0
                            continue
                        deltas = np.array([independent[candidate]['per_person'][p][metric]-independent[baseline]['per_person'][p][metric] for p in people])
                        samples = np.random.default_rng(SEED).choice(deltas, (10000, len(deltas)), replace=True).mean(1)
                        np.testing.assert_allclose(np.quantile(samples, [.025, .975]), original['percentile_95_ci'], rtol=0, atol=1e-12)
                        interval_checks += 1
    write_json(out/'verification.json', {'status': 'passed', 'independent_metric_checks': metric_checks,
        'independent_interval_checks': interval_checks, 'full_prediction_artifact_replays': replayed,
        'old_008_code_files_unchanged': len(old['code_hashes']), 'old_test_and_009_report_unchanged': True,
        'selection_and_training_use_Lab1_only': True, 'report_sha256': sha(out/'report.json'),
        'verification_code_sha256': sha(Path(__file__))})
    print(json.dumps({'status': 'passed', 'metrics': metric_checks, 'intervals': interval_checks, 'artifact_replays': replayed}), flush=True)
