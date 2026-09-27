"""Session isolation, task splits, label coverage and weighting for experiment 010."""
import unittest

import numpy as np
import pandas as pd

from neurasign_engine.personalization import (FEATURES, FIXED, columns, fit_model, labels, metrics,
    predict, select_configuration, training_weights, tuning_splits, union_seconds)


def fixture():
    rows = []
    for person in ['A', 'B', 'C']:
        for task in range(6):
            for window in range(3):
                rows.append({'participant': person, 'unit_id': person+str(task), 'session': 'Lab1',
                             'outcome': task % 2, 'source_end': task*600+60+window*10,
                             'row_id': len(rows), **{f: float(task % 2)+window*.01 for f in FEATURES}})
    return pd.DataFrame(rows)


class PersonalizationTests(unittest.TestCase):
    def test_fixed_real_label_thresholds_exclude_neutral_and_missing(self):
        np.testing.assert_equal(labels([1, 2, 3, 4, 5, np.nan], 'mental_effort'), [0, 0, np.nan, 1, 1, np.nan])
        np.testing.assert_equal(labels([0, 100/3, 50, 200/3, 100, np.nan], 'mental_demand'),
                                [0, 0, np.nan, 1, 1, np.nan])

    def test_lab2_is_rejected_by_training_and_selection(self):
        frame = fixture();frame.loc[0, 'session'] = 'Lab2'
        with self.assertRaises(ValueError):
            fit_model(frame, FIXED)
        with self.assertRaises(AssertionError):
            select_configuration(frame, False)

    def test_inner_splits_keep_whole_tasks_or_people_together(self):
        frame = fixture()
        for train, valid in tuning_splits(frame, False):
            self.assertFalse(set(train.participant) & set(valid.participant))
        for train, valid in tuning_splits(frame[frame.participant == 'A'], True):
            self.assertFalse(set(train.unit_id) & set(valid.unit_id))
            self.assertEqual(train.outcome.nunique(), 2)
            self.assertEqual(valid.outcome.nunique(), 2)

    def test_calibration_and_class_weights_have_declared_totals(self):
        frame = fixture();w = training_weights(frame, 'A');w /= w.sum()
        self.assertAlmostEqual(w[frame.participant == 'A'].sum(), .5)
        self.assertAlmostEqual(w[frame.outcome == 0].sum(), .5)
        self.assertAlmostEqual(w[frame.outcome == 1].sum(), .5)

    def test_prediction_does_not_read_labels_or_ids(self):
        frame = fixture();artifact = fit_model(frame, FIXED)
        future = frame.copy();future['session'] = 'Lab2'
        before = predict(artifact, future)
        future['outcome'] = 1-future.outcome
        future['mental_demand'] = 100
        future['participant'] = 'unknown'
        np.testing.assert_array_equal(before, predict(artifact, future))
        self.assertNotIn('outcome', columns(FIXED))

    def test_single_class_calibration_is_explicit_fallback(self):
        frame = fixture();one = frame[frame.outcome == 1]
        artifact = fit_model(one, FIXED)
        self.assertEqual(artifact['constant'], 1)
        np.testing.assert_array_equal(predict(artifact, frame), np.ones(len(frame)))

    def test_constant_balanced_accuracy_and_nonoverlapping_duration(self):
        frame = fixture();result = metrics(frame, np.ones(len(frame)))
        self.assertAlmostEqual(result['within_person_balanced_accuracy'], .5)
        self.assertAlmostEqual(result['balanced_accuracy'], .5)
        self.assertEqual(union_seconds([60, 70, 80, 180]), 140)


if __name__ == '__main__':
    unittest.main()
