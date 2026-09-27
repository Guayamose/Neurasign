#!/usr/bin/env python3
"""Aggregate-only experiment 022 figure from the saved, verified report."""
from pathlib import Path
import json

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'results/wesad-stress-022'

if __name__ == '__main__':
    report = json.loads((OUT / 'report.json').read_text())
    verification = json.loads((OUT / 'verification.json').read_text())
    assert verification['status'] == 'passed' and report['production_enabled'] is False
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 11, 'axes.spines.top': False,
                         'axes.spines.right': False, 'axes.spines.left': False, 'axes.edgecolor': '#dce4e8',
                         'text.color': '#142b2a', 'axes.labelcolor': '#53646c', 'xtick.color': '#53646c', 'ytick.color': '#53646c'})
    fig, ax = plt.subplots(figsize=(11, 6.2), facecolor='#f5f7fa')
    ax.set_facecolor('#f5f7fa')
    metric_keys = ['balanced_accuracy', 'baseline_recall', 'stress_condition_recall']
    xs = np.arange(3); width = .23
    for offset, (arm, label, color) in enumerate([
        ('majority', 'Majority baseline', '#bcc8ce'), ('fixed_logit', 'Fixed logistic baseline', '#78aaa0'),
        ('selected', 'Selected model', '#107c68')]):
        values = [report['arms'][arm][key] * 100 for key in metric_keys]
        bars = ax.bar(xs + (offset - 1) * width, values, width, label=label, color=color, zorder=3)
        ax.bar_label(bars, labels=[f'{value:.1f}%' for value in values], padding=5, fontsize=10, color='#142b2a')
    ax.set_xticks(xs, ['Balanced accuracy', 'Baseline recall', 'TSST condition recall'])
    ax.set_ylim(0, 112); ax.set_yticks([0, 25, 50, 75, 100], ['0%', '25%', '50%', '75%', '100%'])
    ax.tick_params(axis='both', length=0, pad=9); ax.grid(axis='y', color='#e0e6e9', zorder=0)
    ax.legend(loc='upper center', bbox_to_anchor=(.5, 1.17), ncol=3, frameon=False, fontsize=10)
    fig.text(.09, .94, 'WESAD · wrist condition benchmark', fontsize=21, fontweight='bold')
    fig.text(.09, .89, 'Baseline vs TSST protocol condition · 60-second windows · 3 unseen participants', fontsize=11, color='#53646c')
    selected = report['arms']['selected']
    fig.text(.09, .095, f"Selected ordinary accuracy: {selected['accuracy']:.1%} · {selected['windows']} eligible held-out windows · No abstention", fontsize=10)
    fig.text(.09, .056, 'Lab-condition recognition, not individual stress or workplace validation. Scientific non-commercial research only.', fontsize=9, color='#53646c')
    fig.subplots_adjust(left=.09, right=.97, top=.73, bottom=.2)
    fig.savefig(OUT / 'aggregate-results.png', dpi=180)
    fig.savefig(OUT / 'aggregate-results.pdf')
    print(OUT / 'aggregate-results.png')
