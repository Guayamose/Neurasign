"""Task/person-weighted results and independent checks for workload experiment 021."""
from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, r2_score, roc_auc_score
from threadpoolctl import threadpool_limits

from . import workload_improvement as exp
from .transfer_training import sha, write_json


def metrics(frame, arm):
    """Equal weight per person and per observed task within that person."""
    if frame.empty:
        return {'people': 0, 'tasks': 0, 'mae': None, 'per_person': {}}
    p = frame[arm].to_numpy(float);y = frame.target.to_numpy(float)
    if not np.isfinite(p).all() or not ((p >= 0)&(p <= 100)).all():
        raise ValueError('Predictions must be finite workload scores in 0–100')
    people = {};count = frame.participant.nunique();w = np.zeros(len(frame))
    for person in sorted(frame.participant.unique()):
        mask = (frame.participant == person).to_numpy();one_y = y[mask];one_p = p[mask]
        w[mask] = 1/(count*mask.sum())
        people[person] = {'tasks': int(mask.sum()), 'mae': float(np.abs(one_y-one_p).mean()),
                          'rmse': float(np.sqrt(np.mean((one_y-one_p)**2))),
                          'agreement_within_10': float((np.abs(one_y-one_p) <= 10).mean())}
    mean = np.dot(w, y);denominator = np.dot(w, (y-mean)**2)
    extremes = (y <= 100/3)|(y >= 200/3)
    subset = frame.loc[extremes].reset_index(drop=True);low_high = (subset.target.to_numpy() >= 200/3).astype(int)
    class_scores = subset[arm].to_numpy();cm = np.zeros((2, 2));within = []
    class_weights = np.zeros(len(subset))
    for person, group in subset.groupby('participant'):
        ids = group.index.to_numpy();actual = low_high[ids];predicted = (class_scores[ids] >= 50).astype(int)
        local = np.zeros((2, 2));np.add.at(local, (actual, predicted), 1/len(ids))
        cm += local/subset.participant.nunique()
        class_weights[ids] = 1/(subset.participant.nunique()*len(ids))
        if (local.sum(1) > 0).all():
            within.append(float((np.diag(local)/local.sum(1)).mean()))
    recalls = [float(cm[i, i]/cm[i].sum()) if cm[i].sum() else None for i in (0, 1)]
    auc = None
    if len(np.unique(low_high)) == 2:
        # Independent weighted Mann–Whitney implementation, including ties.
        high = np.flatnonzero(low_high == 1);low = np.flatnonzero(low_high == 0)
        comparisons = (class_scores[high, None] > class_scores[low]).astype(float)+.5*(class_scores[high, None] == class_scores[low])
        mass = class_weights[high, None]*class_weights[low]
        auc = float((comparisons*mass).sum()/mass.sum())
    return {'people': len(people), 'tasks': len(frame), 'mae': float(np.dot(w, np.abs(y-p))),
            'rmse': float(np.sqrt(np.dot(w, (y-p)**2))), 'r2': float(1-np.dot(w, (y-p)**2)/denominator) if denominator else None,
            'agreement_within_10': float(np.dot(w, np.abs(y-p) <= 10)), 'per_person': people,
            'extremes': {'tasks': int(extremes.sum()), 'excluded_middle_tasks': int((~extremes).sum()),
                'coverage': float(extremes.mean()), 'people': int(subset.participant.nunique()),
                'low_tasks': int((low_high == 0).sum()), 'high_tasks': int((low_high == 1).sum()),
                'accuracy': float(np.trace(cm)), 'balanced_accuracy': float(np.mean(recalls)) if all(v is not None for v in recalls) else None,
                'within_person_balanced_accuracy': float(np.mean(within)) if within else None,
                'people_with_both_classes': len(within), 'low_recall': recalls[0], 'high_recall': recalls[1],
                'roc_auc': auc, 'confusion_matrix_person_task_weighted': cm.tolist(), 'prediction_threshold': 50}}


def paired_improvement(candidate, baseline):
    people = sorted(candidate['per_person'])
    if set(people) != set(baseline['per_person']):
        raise ValueError('Paired errors require identical participants')
    differences = np.array([baseline['per_person'][p]['mae']-candidate['per_person'][p]['mae'] for p in people])
    bootstrap = np.random.default_rng(exp.SEED).choice(differences, (10000, len(people)), replace=True).mean(axis=1)
    return {'participants': people, 'people': len(people), 'mean_mae_reduction': float(differences.mean()),
            'percentile_95_ci': np.quantile(bootstrap, [.025, .975]).tolist(),
            'people_improved': int((differences > 1e-12).sum()), 'people_worse': int((differences < -1e-12).sum())}


def context_diagnostic(data, predictions, folds):
    """Post-hoc context-only diagnostic; never an eligible physiological model."""
    result = predictions.copy();result['context_only'] = np.nan;records = []
    for spec in folds:
        training = data[data.participant.isin(spec['training_people'])]
        evaluation = result.participant.isin(spec['evaluation_people'])
        assert not set(training.participant)&set(result.loc[evaluation, 'participant'])
        medians = {}
        for active, name in [(False, 'relaxation'), (True, 'active')]:
            group = training[training.active.astype(bool) == active]
            if group.empty:
                raise ValueError('Outer training has no reference for a context')
            median = exp.weighted_median(group.target, exp.observation_weights(group))
            medians[name] = {'median': median, 'training_people': sorted(group.participant.unique()),
                             'training_units': sorted(group.unit_id)}
            result.loc[evaluation & (result.active.astype(bool) == active), 'context_only'] = median
        records.append({'fold': spec['fold'], 'training_people': spec['training_people'],
                        'evaluation_people': spec['evaluation_people'], 'context_medians': medians})
    assert result.context_only.notna().all()
    return result, records


def report(root):
    root = Path(root);out = root/exp.OUT;frame = exp.load_predictions(root)
    audit = json.loads((root/exp.DATA/'audit.json').read_text());evaluation = json.loads((out/'evaluation.json').read_text())
    source = pd.read_csv(root/exp.DATA/'tasks.csv.gz')
    reference_columns = [c for c in source if c.endswith('__past_reference_delta')]
    availability = source[reference_columns].notna().any(axis=1)
    context_audit = {name: {'tasks': int(mask.sum()), 'any_earlier_reference': int((mask&availability).sum()),
                           'no_earlier_reference': int((mask&~availability).sum())}
                     for name, mask in [('relaxation', ~source.active.astype(bool)), ('active', source.active.astype(bool))]}
    freeze = json.loads((out/'run-freeze.json').read_text())
    context_frame, context_records = context_diagnostic(source, frame, freeze['folds'])
    context_frame[['row_id', 'participant', 'unit_id', 'target', 'active', 'fold', 'context_only']].to_csv(
        out/'post-hoc-context-predictions.csv.gz', index=False, compression={'method': 'gzip', 'mtime': 0})
    diagnostic = {'status': 'post_hoc_descriptive_diagnostic', 'candidate_for_selection': False,
                  'definition': 'Separate person/task-weighted outer-training target medians for relaxation and active contexts. Uses recorded task context; not a wearable model.',
                  'folds': context_records, 'groups': {}}
    groups = {'all_tasks': frame, 'active_tasks_only': frame[frame.active.astype(bool)]}
    results = {};flat = []
    for name, group in groups.items():
        arms = {arm: metrics(group, arm) for arm in exp.ARMS}
        results[name] = {'arms': arms, 'selected_improvement': {arm: paired_improvement(arms['selected'], arms[arm]) for arm in exp.ARMS[:-1]}}
        context_group = context_frame if name == 'all_tasks' else context_frame[context_frame.active.astype(bool)]
        diagnostic['groups'][name] = {'metrics': metrics(context_group, 'context_only'),
                                     'selected_improvement': paired_improvement(arms['selected'], metrics(context_group, 'context_only'))}
        for arm, values in arms.items():
            flat.append({'population': name, 'arm': arm, **{k: v for k, v in values.items() if not isinstance(v, (dict, list))}})
    selections = [json.loads((root/job['selection']).read_text()) for job in evaluation['jobs']]
    doc = {'groups': results, 'reference_availability_context_audit': context_audit,
           'post_hoc_context_only': diagnostic,
           'coverage': {k: audit[k] for k in ['people', 'tasks', 'windows', 'active_tasks', 'extreme_low_tasks', 'extreme_high_tasks', 'middle_tasks']},
           'selections': [{'fold': s['fold'], 'selected': s['selected']} for s in selections],
           'protocol_sha256': sha(root/exp.PROTOCOL), 'data_audit_sha256': sha(root/exp.DATA/'audit.json'),
           'evaluation_sha256': sha(out/'evaluation.json'), 'run_freeze_sha256': sha(out/'run-freeze.json'),
           'interpretation': 'Exploratory anonymous development-only overall NASA-TLX regression; no independent validation or production deployment.'}
    write_json(out/'report.json', doc)
    write_json(out/'post-hoc-context-diagnostic.json', {**diagnostic,
        'predictions_sha256': sha(out/'post-hoc-context-predictions.csv.gz'),
        'run_freeze_sha256': sha(out/'run-freeze.json'), 'data_sha256': freeze['data_sha256']})
    frame.to_csv(out/'all-predictions.csv.gz', index=False, compression={'method': 'gzip', 'mtime': 0})
    pd.DataFrame(flat).to_csv(out/'comparison.csv', index=False)
    pd.DataFrame([{'feature': f, 'available_fraction': v} for f, v in audit['features_available'].items()]).to_csv(out/'feature-availability.csv', index=False)
    primary = results['all_tasks']['arms'];gain = results['all_tasks']['selected_improvement']['fixed_prior']
    selected = primary['selected'];low, high = gain['percentile_95_ci']
    active = results['active_tasks_only']['arms']['selected']
    active_gain = results['active_tasks_only']['selected_improvement']['fixed_prior']
    active_low, active_high = active_gain['percentile_95_ci']
    contextual = diagnostic['groups']['all_tasks']
    context_gain = contextual['selected_improvement'];context_low, context_high = context_gain['percentile_95_ci']
    outcome = 'reduced' if selected['mae'] < primary['fixed_prior']['mae'] else 'did not reduce'
    lines = ['# Experiment 021: improving overall workload prediction', '',
        f"**Assessment:** The nested development-selected model {outcome} overall workload error versus the fixed prior algorithm: "
        f"MAE {selected['mae']:.2f} versus {primary['fixed_prior']['mae']:.2f} points on the 0–100 recorded NASA-TLX scale. "
        f"The training-median baseline scores {primary['constant']['mae']:.2f}. Paired mean error reduction versus the prior is "
        f"{gain['mean_mae_reduction']:+.2f} points (exploratory 95% interval {low:+.2f} to {high:+.2f}). "
        f"Selected weighted R² is {selected['r2']:.3f}. These are development results from {audit['people']} previously studied people, not untouched-test or workplace validation.", '',
        f"**Material limitation:** The earlier-reference availability perfectly separates the initial relaxation context from active tasks: "
        f"{context_audit['relaxation']['no_earlier_reference']}/{context_audit['relaxation']['tasks']} relaxation tasks lack a reference, while "
        f"{context_audit['active']['any_earlier_reference']}/{context_audit['active']['tasks']} active tasks have one. "
        'All outer winners use this profile, so missingness indicators offer a task-context shortcut; the overall gain cannot be attributed to physiological discrimination alone. '
        f"On active tasks alone, MAE is {active['mae']:.2f}, R² {active['r2']:.3f}, and gain over the fixed prior is "
        f"{active_gain['mean_mae_reduction']:+.2f} [{active_low:+.2f}, {active_high:+.2f}] points. "
        f"Active-only extreme-label balanced accuracy is {active['extremes']['balanced_accuracy']:.1%}. "
        'The frozen experiment therefore does not establish a reliable improvement in active-workload discrimination. '
        'This descriptive audit does not change features, selection, predictions or cutoffs after scoring.', '',
        f"The separately requested **post-hoc context-only diagnostic** reaches MAE {contextual['metrics']['mae']:.2f} "
        'using only the relaxation/active context and outer-training medians, with no physiology. '
        f"The selected model's additional MAE reduction is just {context_gain['mean_mae_reduction']:+.2f} "
        f"[{context_low:+.2f}, {context_high:+.2f}] points. This diagnostic is not a wearable model or a new selection candidate.", '',
        '## What was predicted', '',
        'The target is the source **Weighted Nasa Score**, the overall subjective NASA-TLX score. Every retained questionnaire total '
        'was checked against all 15 recorded pairwise weights and all six recorded ratings, divided by 15, agreeing within 0.011 source rounding. '
        'Values and component ratings were checked against 0–100 units. This is a distinct target from the Mental Demand component used in 010/011; '
        'their percentages must not be relabeled or directly compared with this experiment.', '',
        'NASA-TLX combines mental, physical and temporal demand, performance, effort and frustration. '
        'The questionnaire fields serve only to verify the overall outcome; none are predictors and no separate emotional-state output is trained. '
        'This is anonymous academic research, with the earlier employee-product output exclusions preserved. '
        '[NASA instrument definition](https://www.nasa.gov/human-systems-integration-division/nasa-task-load-index-tlx/); '
        '[UNIVERSE source study](https://www.nature.com/articles/s41597-024-03738-7).', '',
        '## Frozen comparison', '',
        f"Only Lab1 of the original development people is used: {audit['tasks']} completed tasks and {audit['windows']:,} previously eligible 60-second windows. "
        'One task contributes one reference score, so overlapping windows cannot inflate the number of labels. The entire task is aggregated before prediction; '
        'these are post-task estimates, not instantaneous estimates or an improvement to the one-second experiment. '
        'Lab2, the original five UNIVERSE test people and Mobile evaluation records are outside this experiment.', '',
        'Four outer person folds evaluate the bounded procedure. Three inner person folds select preprocessing, model and ensemble within each outer-training population. '
        'All 28 candidates and fold assignments were registered before scoring. The 24 base candidates combine three feature profiles with eight regularized ridge/SVR/tree models; '
        'four further candidates average the top three inner-ranked base models globally or within a profile. Selection uses equal-person/equal-task MAE. '
        'The winning ensemble members are never chosen using outer outcomes.', '',
        'Added features include robust temporal task summaries, gap-safe native pulse-interval variability with verified waveform alignment, '
        'log transforms, quality/availability indicators and earlier unlabeled personal references. Missing signals are imputed only within training folds. '
        'Task names, difficulty, timestamps, person IDs, questionnaire answers, future-task observations and target history are excluded as input columns. '
        'The initial-reference missingness shortcut remains, as audited above. '
        'The fixed comparator uses the original 28 signal features aggregated as medians and fixed Ridge 100; it is refitted on the identical tasks and folds, '
        'rather than reusing any model that has seen evaluation people.', '',
        '## Continuous-score results', '',
        '| Population | Model | People / tasks | MAE ↓ | RMSE ↓ | Weighted R² ↑ | Within 10 points |',
        '|---|---|---:|---:|---:|---:|---:|']
    for name, summary in results.items():
        for arm, m in summary['arms'].items():
            lines.append(f"| {name} | {arm} | {m['people']} / {m['tasks']} | {m['mae']:.2f} | {m['rmse']:.2f} | {m['r2']:.3f} | {m['agreement_within_10']:.1%} |")
    lines += ['', 'Agreement within 10 points is regression tolerance agreement, not classification accuracy. '
              'MAE/RMSE and R² give people equal weight, then divide their weight equally across tasks.', '',
              '| Population | Comparison | Paired MAE reduction [95% interval] | People improved / worse |',
              '|---|---|---:|---:|']
    for name, summary in results.items():
        for arm, m in summary['selected_improvement'].items():
            lo, hi = m['percentile_95_ci']
            lines.append(f"| {name} | selected versus {arm} | {m['mean_mae_reduction']:+.2f} [{lo:+.2f}, {hi:+.2f}] | {m['people_improved']} / {m['people_worse']} |")
    lines += ['', 'Intervals use 10,000 paired whole-person resamples. They are exploratory and do not account for overlapping training populations '
              'or the broader history of development experimentation. An interval crossing zero does not demonstrate improvement.', '',
              '## Prespecified low/high description', '',
              'This secondary description keeps true reference scores ≤33⅓ or ≥66⅔ and excludes the middle; '
              'the prediction threshold is fixed at 50. The regression models are neither refitted nor selected for this subset. '
              'A high binary percentage is not accuracy at predicting the continuous workload score.', '',
              '| Population | Model | Low / high / excluded-middle tasks | Coverage | Balanced accuracy | Low recall | High recall | ROC AUC |',
              '|---|---|---:|---:|---:|---:|---:|---:|']
    fmt = lambda v: 'n/a' if v is None else f'{v:.1%}'
    for name, summary in results.items():
        for arm, m in summary['arms'].items():
            x = m['extremes'];auc = 'n/a' if x['roc_auc'] is None else f"{x['roc_auc']:.3f}"
            lines.append(f"| {name} | {arm} | {x['low_tasks']} / {x['high_tasks']} / {x['excluded_middle_tasks']} | "
                         f"{x['coverage']:.1%} | {fmt(x['balanced_accuracy'])} | {fmt(x['low_recall'])} | {fmt(x['high_recall'])} | {auc} |")
    lines += ['', 'Active-only excludes relaxation video tasks using the same saved predictions, without refitting or choosing another winner. '
              'It checks whether separation survives beyond the deliberately resting context.', '', '## Selection and limitations', '',
              '| Outer fold | Inner-selected configuration | Inner selection MAE |', '|---|---|---:|']
    for choice in selections:
        selected_config = choice['selected'];members = ', '.join(exp.CONFIGS[i]['profile']+'/'+exp.CONFIGS[i]['algorithm'] for i in selected_config['members'])
        lines.append(f"| {choice['fold']} | {members} | {selected_config['inner_mae']:.2f} |")
    lines += ['', '## Post-hoc context-only diagnostic', '',
              'After discovering the missing-reference shortcut, a separate descriptive baseline uses recorded task context alone. '
              'For each frozen outer fold, it computes the person/task-weighted training target median separately for relaxation and active tasks, '
              'then applies the appropriate median to the held people. It uses no physiological value and performs no candidate or threshold selection. '
              '**It is not a wearable model, was not a preregistered candidate and does not replace or retune the frozen primary results.** '
              'This diagnostic tests how much error reduction can be obtained simply by knowing the experimental context.', '',
              '| Population | Context-only MAE | Context-only R² | Selected minus context improvement in MAE [95% interval] |',
              '|---|---:|---:|---:|']
    for name, result in diagnostic['groups'].items():
        m = result['metrics'];improvement = result['selected_improvement'];lo, hi = improvement['percentile_95_ci']
        lines.append(f"| {name} | {m['mae']:.2f} | {m['r2']:.3f} | {improvement['mean_mae_reduction']:+.2f} [{lo:+.2f}, {hi:+.2f}] |")
    lines += ['', 'Positive improvement means the selected physiological model has lower error than this context-only diagnostic. '
              'The paired intervals remain exploratory; the diagnostic was requested after outcome inspection and cannot be presented as a fresh confirmatory comparison.']
    lines += ['', '- Inner selection figures are optimization scores, not independent performance estimates. '
              'Outer predictions evaluate the registered selection procedure; no single universal winner is claimed.',
              '- Task-level questionnaire ratings remain subjective and retrospective. Native pulse intervals are not ECG truth; '
              'manufacturing filters and source offline clock alignment persist. Personal references are earlier unlabeled physiology, not verified rest.',
              '- All people were already used in earlier development. This nested comparison controls the new search but does not erase prior researcher exposure. '
              'A future independent cohort is needed before generalization claims.',
              '- Aggregating complete tasks consumes minutes of evidence, and source eligibility inherits previous 60-second quality screening. '
              'This is not a continuous live, one-second, cross-device or workplace validation.',
              '- Research artifacts remain production-disabled; no named employee, phone app or dashboard integration was made.', '',
              '## Artifacts and reproduction', '',
              'Protocol: [021-workload-improvement-protocol.json](021-workload-improvement-protocol.json). '
              'Data: `data/prepared/workload-improvement-v1/`; predictions, selections, CSV/PNG/PDF results and verification: '
              '`results/workload-improvement-v1/`; saved fold models: `models/workload-improvement-v1/`.', '',
              '```bash', '.venv/bin/python scripts/run_workload_improvement.py prepare',
              'OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python scripts/run_workload_improvement.py run',
              '.venv/bin/python scripts/run_workload_improvement.py report', '.venv/bin/python scripts/run_workload_improvement.py verify', '```', '',
              'Preparation and training refuse to overwrite an existing registered run. Earlier experiments are checked by hashes; '
              'no thresholds or candidates are changed after outer evaluation.', '']
    (root/'experiments/021-workload-improvement-results.md').write_text('\n'.join(lines))
    draw(out, results, diagnostic)
    print(json.dumps(results, indent=2), flush=True)


def draw(out, results, diagnostic):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.8), constrained_layout=True)
    for ax, (name, group) in zip(axes, results.items()):
        values = [group['arms'][a]['mae'] for a in exp.ARMS]+[diagnostic['groups'][name]['metrics']['mae']]
        bars = ax.bar(['Training\nmedian', 'Fixed\nprior', 'Nested\nselected', 'Context only\n(post-hoc)'], values,
                      color=['#94a3b8', '#2563eb', '#0d9488', '#d97706'])
        bars[-1].set_hatch('//')
        ax.bar_label(bars, fmt='%.2f', padding=3);ax.set_ylim(0, max(values)*1.22)
        ax.set_ylabel('Person-balanced MAE (NASA-TLX points; lower is better)')
        ax.set_title(name.replace('_', ' '));ax.spines[['top', 'right']].set_visible(False)
    fig.suptitle('Overall subjective workload · anonymous development research\nFrozen primary models + post-hoc context-only diagnostic (no physiology)', fontsize=13)
    fig.savefig(out/'comparison.png', dpi=180);fig.savefig(out/'comparison.pdf');plt.close(fig)


def verify(root):
    root = Path(root);out = root/exp.OUT
    freeze = json.loads((out/'run-freeze.json').read_text());audit = json.loads((root/exp.DATA/'audit.json').read_text())
    evaluation = json.loads((out/'evaluation.json').read_text());document = json.loads((out/'report.json').read_text())
    assert sha(Path(exp.__file__)) == freeze['code_sha256']
    assert sha(root/exp.PROTOCOL) == freeze['protocol_sha256'] == document['protocol_sha256']
    assert sha(root/exp.DATA/'audit.json') == freeze['audit_sha256'] == document['data_audit_sha256']
    assert sha(root/exp.DATA/'tasks.csv.gz') == freeze['data_sha256'] == audit['table_sha256']
    assert sha(out/'run-freeze.json') == evaluation['run_sha256'] == document['run_freeze_sha256']
    assert sha(out/'evaluation.json') == document['evaluation_sha256']
    for path, digest in freeze['preserved_files'].items():
        assert sha(root/path) == digest, path
    assert sha(root/'data/prepared/transfer-v1/universe.csv.gz') == audit['base_features_sha256']
    assert sha(root/'data/prepared/transfer-v1/universe-native.csv.gz') == audit['native_features_sha256']
    assert sha(root/'data/prepared/transfer-v1/universe-native-audit.json') == audit['native_alignment_audit_sha256']
    for name, digest in audit['source_labels_sha256'].items():
        assert '/Lab1/' in name and sha(root/'data/universe/extracted'/name) == digest
    data = pd.read_csv(root/exp.DATA/'tasks.csv.gz');saved = exp.load_predictions(root)
    reference_columns = [c for c in data if c.endswith('__past_reference_delta')]
    available = data[reference_columns].notna().any(axis=1)
    for name, mask in [('relaxation', ~data.active.astype(bool)), ('active', data.active.astype(bool))]:
        assert document['reference_availability_context_audit'][name] == {
            'tasks': int(mask.sum()), 'any_earlier_reference': int((mask&available).sum()),
            'no_earlier_reference': int((mask&~available).sum())}
    assert set(data.session) == {'Lab1'} and set(data.row_id) == set(saved.row_id)
    assert not set(data.participant)&set(audit['original_test_excluded'])
    base = data.sort_values('row_id').reset_index(drop=True)
    np.testing.assert_array_equal(base.target, saved.target)
    assert len(freeze['candidates']) == 24 and len(freeze['folds']) == 4
    context_frame, context_records = context_diagnostic(data, saved, freeze['folds'])
    context_saved = pd.read_csv(out/'post-hoc-context-predictions.csv.gz')
    np.testing.assert_array_equal(context_frame.row_id, context_saved.row_id)
    np.testing.assert_allclose(context_frame.context_only, context_saved.context_only, rtol=0, atol=1e-10)
    diagnostic = json.loads((out/'post-hoc-context-diagnostic.json').read_text())
    assert sha(out/'post-hoc-context-predictions.csv.gz') == diagnostic['predictions_sha256']
    assert context_records == document['post_hoc_context_only']['folds'] == diagnostic['folds']
    assert document['post_hoc_context_only']['candidate_for_selection'] is False
    prediction_replays = selection_checks = 0
    with threadpool_limits(limits=1):
        for job in evaluation['jobs']:
            spec = freeze['folds'][job['fold']]
            train = data[data.participant.isin(spec['training_people'])]
            future = data[data.participant.isin(spec['evaluation_people'])]
            for filename, checksum in [('selection', 'selection_sha256'), ('inner_predictions', 'inner_predictions_sha256'), ('predictions', 'predictions_sha256')]:
                assert sha(root/job[filename]) == job[checksum]
            selection = json.loads((root/job['selection']).read_text())
            oof = pd.read_csv(root/job['inner_predictions'])
            assert set(oof.row_id) == set(train.row_id) and not set(train.participant)&set(future.participant)
            assert len(selection['candidates']) == 28
            for inner in selection['inner_folds']:
                a, b = set(inner['training_people']), set(inner['validation_people'])
                assert not a&b and a|b == set(train.participant)
                assert set(inner['training_units']) == set(train.loc[train.participant.isin(a), 'unit_id'])
                assert set(inner['validation_units']) == set(train.loc[train.participant.isin(b), 'unit_id'])
            assert set.union(*(set(f['validation_people']) for f in selection['inner_folds'])) == set(train.participant)
            for candidate in selection['candidates']:
                score = oof[[f'base{i}' for i in candidate['members']]].mean(axis=1).to_numpy()
                error = sum(np.abs(group.target.to_numpy()-score[group.index]).mean() for _, group in oof.groupby('participant'))/oof.participant.nunique()
                np.testing.assert_allclose(error, candidate['inner_mae'], rtol=0, atol=1e-10);selection_checks += 1
            assert min(selection['candidates'], key=lambda row: row['inner_mae']) == selection['selected']
            prediction = pd.read_csv(root/job['predictions']).sort_values('row_id').reset_index(drop=True)
            future = future.sort_values('row_id').reset_index(drop=True)
            np.testing.assert_array_equal(prediction.row_id, future.row_id)
            for record in job['artifacts']:
                assert sha(root/record['file']) == record['sha256'];artifact = joblib.load(root/record['file'])
                assert not artifact['production_enabled'] and artifact['training_session'] == 'Lab1'
                assert set(artifact['training_people']) == set(train.participant)
                assert set(artifact['training_units']) == set(train.unit_id)
                for member in artifact.get('members', [artifact]):
                    assert set(member['training_people']) == set(train.participant)
                    assert set(member['training_units']) == set(train.unit_id)
                    if 'model' in member:
                        assert member['columns'] == exp.feature_columns(member['config']['profile'])
                        assert not any(c in member['columns'] for c in ['target', 'participant', 'active', 'unit_id', 'source_windows'])
                        # Training-only preprocessing: medians equal the outer-training inputs.
                        expected = np.array([train[c].median() if train[c].notna().any() else 0. for c in member['columns']])
                        np.testing.assert_allclose(member['model'].steps[0][1].statistics_, expected, rtol=0, atol=1e-10)
                changed = future.copy();changed['target'] = 100-changed.target
                changed['participant'] = 'metadata_only';changed['active'] = ~changed.active
                np.testing.assert_allclose(exp.predict(artifact, changed), prediction[record['arm']], rtol=0, atol=1e-10)
                prediction_replays += 1
    metric_checks = 0
    for name, group in [('all_tasks', saved), ('active_tasks_only', saved[saved.active.astype(bool)])]:
        recomputed = {}
        for arm in exp.ARMS:
            result = metrics(group, arm);recomputed[arm] = result
            assert result == document['groups'][name]['arms'][arm]
            weights = 1/group.groupby('participant').participant.transform('size').to_numpy(float)
            np.testing.assert_allclose(result['mae'], mean_absolute_error(group.target, group[arm], sample_weight=weights), atol=1e-10)
            np.testing.assert_allclose(result['r2'], r2_score(group.target, group[arm], sample_weight=weights), atol=1e-10)
            extreme = group[(group.target <= 100/3)|(group.target >= 200/3)]
            if extreme.target.nunique() > 1 and (extreme.target <= 100/3).any() and (extreme.target >= 200/3).any():
                weights = 1/extreme.groupby('participant').participant.transform('size').to_numpy(float)
                np.testing.assert_allclose(result['extremes']['roc_auc'], roc_auc_score(extreme.target >= 200/3, extreme[arm], sample_weight=weights), atol=1e-10)
            metric_checks += 3
        for arm in exp.ARMS[:-1]:
            assert paired_improvement(recomputed['selected'], recomputed[arm]) == document['groups'][name]['selected_improvement'][arm]
        context_group = context_frame if name == 'all_tasks' else context_frame[context_frame.active.astype(bool)]
        context_metrics = metrics(context_group, 'context_only')
        assert context_metrics == document['post_hoc_context_only']['groups'][name]['metrics']
        assert paired_improvement(recomputed['selected'], context_metrics) == document['post_hoc_context_only']['groups'][name]['selected_improvement']
    result = {'status': 'passed', 'saved_artifact_replays': prediction_replays, 'independent_metric_checks': metric_checks,
              'inner_selection_score_checks': selection_checks, 'frozen_files_unchanged': len(freeze['preserved_files']),
              'training_only_preprocessing_checked': True, 'outer_and_inner_person_disjoint': True,
              'post_hoc_context_diagnostic_separate_and_outer_training_only': True,
              'original_test_and_Lab2_not_evaluated': True, 'report_sha256': sha(out/'report.json'),
              'verification_code_sha256': sha(Path(__file__))}
    write_json(out/'verification.json', result);print(json.dumps(result), flush=True)
