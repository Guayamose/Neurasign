"""Reference semantics, temporal isolation and independent metrics for experiment021."""
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from neurasign_engine import workload_improvement as exp
from neurasign_engine.workload_improvement_report import context_diagnostic, metrics


class WorkloadImprovementTests(unittest.TestCase):
    def test_nested_person_folds_are_disjoint_and_complete(self):
        people = ['p'+str(i) for i in range(19)]
        outer = exp.person_folds(people, 4)
        self.assertEqual(sorted(sum(outer, [])), sorted(people))
        for held in outer:
            training = set(people)-set(held)
            for validation in exp.person_folds(training, 3):
                self.assertFalse(set(validation)&set(held))
                self.assertTrue(set(validation) <= training)

    def test_task_reference_excludes_current_and_future_windows(self):
        rows = pd.DataFrame({'source_end': np.arange(60., 660., 10.),
                             **{f: np.arange(60., dtype=float) for f in exp.SIGNALS}})
        task = rows[(rows.source_end >= 300)&(rows.source_end <= 400)]
        original = exp.aggregate_task(task, rows)
        changed = rows.copy();changed.loc[changed.source_end > 240, exp.SIGNALS] = 999999
        after = exp.aggregate_task(task, changed)
        for f in exp.SIGNALS:
            self.assertEqual(original[f+'__past_reference_delta'], after[f+'__past_reference_delta'])
        self.assertEqual(original[exp.SIGNALS[0]+'__late_minus_early'], 7.)

    def test_recorded_nasa_weights_are_verified_and_target_is_composite(self):
        import csv, hashlib, io
        dimensions = [d.lower().replace(' ', '_') for d in exp.DIMENSIONS]
        pairs = [a+'__vs__'+b for i, a in enumerate(dimensions) for b in dimensions[i+1:]]
        ratings = [10, 20, 30, 40, 50, 60];answers = [p.split('__vs__')[0] for p in pairs]
        score = sum(ratings[dimensions.index(answer)] for answer in answers)/15
        stream = io.StringIO();writer = csv.writer(stream)
        writer.writerow(['Task', *exp.DIMENSIONS, *pairs, 'Weighted Nasa Score'])
        writer.writerow(['example', *ratings, *answers, round(score, 2)])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'Task_Labels.csv';path.write_text(stream.getvalue())
            manifest = {path.name: {'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}}
            labels, audit = exp.recorded_tlx(path, Path(tmp), manifest)
            self.assertAlmostEqual(labels['example'], round(score, 2))
            self.assertEqual(audit['verified_scores'], 1)

    def test_predictors_cannot_include_reference_labels_or_metadata(self):
        for profile in exp.PROFILES:
            cols = exp.feature_columns(profile)
            self.assertFalse(set(cols)&{'target', 'participant', 'unit_id', 'active', 'source_windows', 'mental_demand'})
            self.assertFalse(any('frustration' in c or 'nasa' in c for c in cols))
        self.assertEqual(len(exp.CONFIGS), 24)

    def test_lab2_and_duplicate_tasks_cannot_fit(self):
        frame = pd.DataFrame({'session': ['Lab2'], 'target': [50], 'participant': ['a'], 'unit_id': ['one']})
        with self.assertRaises(ValueError):
            exp.fit(frame, {'profile': 'legacy', 'algorithm': 'constant'})
        frame.session = 'Lab1';frame = pd.concat([frame, frame])
        with self.assertRaises(ValueError):
            exp.fit(frame, {'profile': 'legacy', 'algorithm': 'constant'})

    def test_person_weights_and_continuous_metric_are_not_binary_accuracy(self):
        frame = pd.DataFrame({'participant': ['a', 'a', 'b'], 'target': [0., 100., 50.], 'prediction': [10., 90., 80.]})
        result = metrics(frame, 'prediction')
        self.assertAlmostEqual(result['mae'], 20.)
        self.assertAlmostEqual(result['agreement_within_10'], .5)
        self.assertAlmostEqual(result['extremes']['balanced_accuracy'], 1.)
        self.assertEqual(result['extremes']['excluded_middle_tasks'], 1)
        self.assertEqual(result['extremes']['roc_auc'], 1.)

    def test_post_hoc_context_baseline_uses_outer_training_only(self):
        data = pd.DataFrame({'participant': ['a', 'a', 'b', 'b'], 'unit_id': ['a0', 'a1', 'b0', 'b1'],
                             'row_id': ['a0', 'a1', 'b0', 'b1'], 'active': [False, True, False, True],
                             'target': [10., 70., 20., 80.]})
        folds = [{'fold': 0, 'training_people': ['a'], 'evaluation_people': ['b']},
                 {'fold': 1, 'training_people': ['b'], 'evaluation_people': ['a']}]
        before, _ = context_diagnostic(data, data, folds)
        changed = data.copy();changed.loc[changed.participant == 'b', 'target'] = [99., 1.]
        after, _ = context_diagnostic(changed, changed, folds)
        np.testing.assert_array_equal(before.loc[before.participant == 'b', 'context_only'],
                                      after.loc[after.participant == 'b', 'context_only'])
        np.testing.assert_array_equal(before.loc[before.participant == 'b', 'context_only'], [10., 70.])


if __name__ == '__main__':
    unittest.main()
