#!/usr/bin/env python3
"""Independently audit classification metrics/intervals and draw the saved comparison."""
import hashlib
import json
from pathlib import Path
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from neurasign_engine.schema import SEED


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == '__main__':
    out = ROOT/'results/papagei-v1'
    report = json.loads((out/'report.json').read_text())
    selection = json.loads((out/'selection.json').read_text())
    old = json.loads((ROOT/'experiments/008-final-selection.json').read_text())
    assert all(digest(ROOT/p) == h for p, h in old['code_hashes'].items())
    per_person = {}
    for result in report['results']:
        target = result['target']
        frame = pd.read_csv(out/(target+'__'+result['name']+'.csv.gz'))
        low, high = (1, 5) if target == 'mental_effort' else (0, 100)
        assert frame.prediction.between(low, high).all()
        if target == 'mental_effort':
            y = frame[target].to_numpy(int)-1
            p = np.floor(frame.prediction.to_numpy()+.5).astype(int)-1
            n = 5
        else:
            y = np.minimum((frame[target].to_numpy()/(100/3)).astype(int), 2)
            p = np.minimum((frame.prediction.to_numpy()/(100/3)).astype(int), 2)
            n = 3
        cm = np.zeros((n, n))
        for _, person in frame.groupby('participant'):
            for _, task in person.groupby('unit_id'):
                idx = task.index.to_numpy()
                np.add.at(cm, (y[idx], p[idx]), 1/(len(task)*person.unit_id.nunique()*frame.participant.nunique()))
        present = cm.sum(axis=1) > 0
        balanced = (np.diag(cm)[present]/cm.sum(axis=1)[present]).mean()
        np.testing.assert_allclose(balanced, result['metrics']['balanced_accuracy'], rtol=1e-10)
        person_error = frame.assign(error=abs(frame[target]-frame.prediction)).groupby(['participant', 'unit_id']).error.mean().groupby('participant').mean()
        per_person[(target, result['name'])] = person_error.sort_index().to_numpy()
    intervals = 0
    for target, choices in selection.items():
        candidate = per_person[(target, choices['papagei']['name'])]
        for kind in ('constant', 'engineered'):
            delta = per_person[(target, choices[kind]['name'])]-candidate
            sampled = np.random.default_rng(SEED).choice(delta, (10000, len(delta)), replace=True).mean(axis=1)
            expected = choices['vs_'+kind]
            # Saved float32 predictions round-trip through decimal CSV strings.
            np.testing.assert_allclose(np.quantile(sampled, [.025, .975]), expected['percentile_95_ci'], rtol=0, atol=1e-6)
            intervals += 1
    names = {'mental_effort': 'Mental effort (1–5)', 'mental_demand': 'Mental demand (0–100)',
             'physical_demand': 'Physical demand (0–100)', 'temporal_demand': 'Time pressure (0–100)',
             'perceived_performance': 'Self-rated performance (0–100)', 'effort': 'Effort (0–100)'}
    fig, axes = plt.subplots(2, 3, figsize=(13, 6.6), constrained_layout=True)
    for ax, (target, choices) in zip(axes.flat, selection.items()):
        values = [choices[k]['metrics']['mae'] for k in ('constant', 'engineered', 'papagei')]
        ax.barh(['Constant', 'Engineered', 'PaPaGei'], values, color=['#9ca3af', '#2563eb', '#0d9488'])
        ax.invert_yaxis()
        ax.set_title(names[target], fontweight='bold')
        ax.set_xlim(0, max(values)*1.25)
        ax.set_xlabel('Mean absolute error · lower is better')
        for i, value in enumerate(values):
            ax.text(value+max(values)*.025, i, f'{value:.2f}', va='center')
        ax.spines[['top', 'right']].set_visible(False)
    fig.suptitle('NEURASIGN · PaPaGei development comparison\n19 people · same eligible windows · participant-disjoint folds · no independent test', fontsize=15)
    fig.savefig(out/'comparison.png', dpi=180)
    fig.savefig(out/'comparison.pdf')
    plt.close(fig)
    audit = {'status': 'passed', 'independent_balanced_accuracy_checks': len(report['results']),
             'independent_interval_checks': intervals, 'preserved_008_code_files': len(old['code_hashes']),
             'training_report_sha256': digest(out/'report.json'), 'selection_sha256': digest(out/'selection.json')}
    (out/'additional-verification.json').write_text(json.dumps(audit, indent=2)+'\n')
    print(json.dumps(audit))
