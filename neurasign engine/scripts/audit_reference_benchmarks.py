#!/usr/bin/env python3
"""Independently recompute reference-benchmark metrics and constant predictions."""
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def person_weights(frame):
    people, inverse, counts = np.unique(frame.participant.astype(str), return_inverse=True, return_counts=True)
    return 1 / (len(people) * counts[inverse])


def check(actual, expected):
    if expected is None:
        assert actual is None
    else:
        np.testing.assert_allclose(actual, expected, atol=1e-10, rtol=1e-10)


def audit(name):
    folder = ROOT/'results'/name
    freeze = json.loads((folder/'run-start.json').read_text())
    protocol = json.loads((ROOT/freeze['protocol']).read_text())
    report = json.loads((folder/'report.json').read_text())
    source = pd.read_csv(ROOT/freeze['data'], dtype={'participant': str})
    predictions = pd.read_csv(folder/'test-predictions.csv.gz', dtype={'participant': str})
    truth = source.set_index('row_id').loc[predictions.row_id]
    assert predictions.row_id.is_unique
    np.testing.assert_array_equal(truth.participant, predictions.participant)
    np.testing.assert_array_equal(truth.target, predictions.target)
    assert set(predictions.participant) == set(protocol['split']['test'])
    assert set(protocol['split']['development']).isdisjoint(protocol['split']['test'])
    development = source[source.participant.isin(protocol['split']['development'])]
    constant = np.dot(person_weights(development), development.target)
    # DummyRegressor mean and DummyClassifier positive-class prior must equal
    # this direct calculation, independent of the training/scoring implementation.
    np.testing.assert_allclose(predictions.baseline, constant, atol=1e-10)
    w = person_weights(predictions)
    y = predictions.target.to_numpy(float)
    checks = 0
    for arm in ('selected', 'baseline'):
        p = predictions[arm].to_numpy(float)
        expected = report[arm]
        if protocol['kind'] == 'regression':
            error = y-p
            residual = np.abs(error)
            denominator = np.dot(w, (y-np.dot(w, y))**2)
            measured = {
                'mae': np.dot(w, residual),
                'rmse': np.sqrt(np.dot(w, error**2)),
                'r2': 1-np.dot(w, error**2)/denominator,
                'agreement_within_5': np.dot(w, residual <= 5),
                'agreement_within_10': np.dot(w, residual <= 10),
            }
        else:
            labels = (p >= .5).astype(int)
            counts = np.zeros((2, 2), dtype=int)
            mass = np.zeros((2, 2))
            for target in (0, 1):
                for predicted in (0, 1):
                    mask = (y == target) & (labels == predicted)
                    counts[target, predicted] = int(mask.sum())
                    mass[target, predicted] = w[mask].sum()
            recalls = [mass[c, c]/mass[c].sum() if mass[c].sum() else None for c in (0, 1)]
            f1 = [2*mass[c, c]/(mass[c].sum()+mass[:, c].sum()) if mass[c].sum()+mass[:, c].sum() else 0 for c in (0, 1)]
            positive, negative = y == 1, y == 0
            auc = None
            if positive.any() and negative.any():
                pair_weight = w[positive, None]*w[None, negative]
                comparisons = (p[positive, None] > p[None, negative]) + .5*(p[positive, None] == p[None, negative])
                auc = float((pair_weight*comparisons).sum()/pair_weight.sum())
            within = []
            for person in predictions.participant.unique():
                mask = predictions.participant.to_numpy() == person
                if len(np.unique(y[mask])) == 2:
                    within.append(np.mean([np.mean(labels[mask & (y == c)] == c) for c in (0, 1)]))
            measured = {
                'accuracy': np.dot(w, y == labels),
                'balanced_accuracy': float(np.mean(recalls)) if all(v is not None for v in recalls) else None,
                'low_recall': recalls[0], 'high_recall': recalls[1],
                'macro_f1': np.mean(f1), 'roc_auc': auc,
                'confusion_counts': counts.tolist(),
                'within_person_balanced_accuracy': float(np.mean(within)) if within else None,
                'people_with_both_classes': len(within),
            }
        for key, value in measured.items():
            check(value, expected[key])
            checks += 1
    record = {'benchmark': name, 'independent_metric_checks': checks, 'baseline_recomputed_from_training_people': True, 'passed': True}
    (folder/'independent-audit.json').write_text(json.dumps(record, indent=2)+'\n')
    return record


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('benchmarks', nargs='*')
    args = parser.parse_args()
    names = args.benchmarks or [
        'fatigueset-physical-v1', 'fatigueset-mental-v1', 'readiness-oura-v1',
        'dailysense-classification-v1', 'dailysense-regression-v1',
    ]
    for name in names:
        print(json.dumps(audit(name)), flush=True)


if __name__ == '__main__':
    main()
