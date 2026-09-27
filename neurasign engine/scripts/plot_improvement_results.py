#!/usr/bin/env python3
"""Plot aggregate saved results; never retrain, rank or modify model outcomes."""
import csv
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
COLORS = {'Constant': '#94a3b8', 'Prior method': '#64748b', 'Fixed logistic': '#64748b',
          'New procedure': '#2563eb', 'Context only*': '#d97706'}


def read(name):
    return json.loads((ROOT / 'results' / name / 'report.json').read_text())


def main():
    readiness = read('readiness-refinement-v1')
    fatigue = read('fatigue-nested-v1/classification')
    workload = read('workload-improvement-v1')
    stress = read('wesad-stress-022')
    panels = [
        ('Stress condition · WESAD', 'Balanced accuracy (%) ↑',
         [(label, 100 * stress['arms'][arm]['balanced_accuracy']) for label, arm in
          [('Constant', 'majority'), ('Fixed logistic', 'fixed_logit'), ('New procedure', 'selected')]],
         '3 unseen people · 60-second wrist windows\nBaseline vs TSST protocol; not live employee stress.', True),
        ('Daily readiness · Oura score', 'Mean absolute error / 100 ↓',
         [(label, readiness['outer'][arm]['mae']) for label, arm in
          [('Constant', 'constant'), ('Prior method', 'fixed'), ('New procedure', 'selected')]],
         '14 development people · nested evaluation\nVendor daily-score approximation; not live readiness.', False),
        ('Daily fatigue · DailySense', 'Person-weighted balanced accuracy (%) ↑',
         [(label, 100 * fatigue['outer_metrics'][arm]['balanced_accuracy']) for label, arm in
          [('Constant', 'training_constant'), ('Prior method', 'fixed_cardiac_extra5'),
           ('New procedure', 'inner_selected')]],
         '28 development people · nested evaluation\nObserved daily fatigue rating; the new classifier is weaker.', True),
        ('Overall workload · NASA-TLX', 'Mean absolute error / 100 ↓',
         [('Prior method', workload['groups']['all_tasks']['arms']['fixed_prior']['mae']),
          ('New procedure', workload['groups']['all_tasks']['arms']['selected']['mae']),
          ('Context only*', workload['post_hoc_context_only']['groups']['all_tasks']['metrics']['mae'])],
         '19 development people · nested evaluation\n*Post-hoc rest/activity baseline; no established physiology gain.', False),
    ]
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10, 'axes.titleweight': 'bold',
                         'axes.edgecolor': '#cbd5e1', 'text.color': '#0f172a',
                         'axes.labelcolor': '#334155', 'xtick.color': '#334155', 'ytick.color': '#64748b'})
    fig, axes = plt.subplots(2, 2, figsize=(13, 9))
    fig.patch.set_facecolor('white')
    records = []
    for ax, (title, ylabel, bars, note, percent) in zip(axes.flat, panels):
        labels, values = zip(*bars)
        containers = ax.bar(labels, values, width=.56, color=[COLORS[label] for label in labels], zorder=3)
        ax.bar_label(containers, labels=[f'{value:.1f}%' if percent else f'{value:.2f}' for value in values],
                     padding=6, fontsize=12, fontweight='bold')
        ax.set_title(title, loc='left', pad=18, fontsize=13)
        ax.set_ylabel(ylabel, fontsize=10)
        ax.set_ylim(0, 113 if percent else max(values) * 1.25)
        if percent:
            ax.set_yticks([0, 25, 50, 75, 100])
        ax.grid(axis='y', color='#e2e8f0', zorder=0)
        ax.spines[['top', 'right']].set_visible(False)
        ax.tick_params(axis='x', length=0)
        ax.text(0, -.24, note, transform=ax.transAxes, fontsize=9, linespacing=1.6, va='top')
        records += [{'panel': title, 'metric': ylabel, 'arm': label, 'value': value} for label, value in bars]
    fig.suptitle('NEURASIGN · Research results', x=.07, ha='left', y=.99, fontsize=23, fontweight='bold')
    fig.text(.07, .945, 'Experiments 019–022 | Saved evaluation results | Different targets and cohorts: do not combine scores.',
             fontsize=11, color='#475569')
    fig.subplots_adjust(left=.07, right=.98, top=.86, bottom=.20, hspace=.68, wspace=.28)
    fig.text(.07, .025, 'Research artifacts only. Uncertainty intervals, coverage, source timing and licensing limits are in the experiment reports.\n'
             'Prior held-out results remain unchanged. No claim of clinical, workplace or cross-device validation.',
             fontsize=9, color='#475569', linespacing=1.6)
    public = ROOT / 'experiments' / 'figures'
    public.mkdir(exist_ok=True)
    output = ROOT / 'results' / 'improvement-round'
    output.mkdir(parents=True, exist_ok=True)
    fig.savefig(public / '019-022-results.png', dpi=180, facecolor='white')
    fig.savefig(output / '019-022-results.pdf', facecolor='white')
    plt.close(fig)
    with (output / '019-022-results.csv').open('w', newline='') as destination:
        writer = csv.DictWriter(destination, fieldnames=['panel', 'metric', 'arm', 'value'])
        writer.writeheader()
        writer.writerows(records)
    print(json.dumps({'figure': str((public / '019-022-results.png').relative_to(ROOT)),
                      'export_directory': str(output.relative_to(ROOT))}))


if __name__ == '__main__':
    main()
