"""Independent weighting and paired-observation checks for experiment 011."""
import unittest

import numpy as np
import pandas as pd

from neurasign_engine.short_window_report import align_pair, duration_effect, independent_metrics


def observations():
    rows = []
    # A: one low task correct, nine repeated high windows incorrect => accuracy .5.
    # B: a single low-only task correct => accuracy 1, excluded from within-person BA.
    for person, task, outcome, score, count in [('A', 'a0', 0, 0., 1), ('A', 'a1', 1, 0., 9), ('B', 'b0', 0, 0., 3)]:
        for _ in range(count):
            i = len(rows)
            rows.append({'row_id': i, 'participant': person, 'session': 'Lab2', 'unit_id': task,
                         'source_end': 100+i, 'window_end': 60+i, 'outcome': outcome, 'score': score})
    return pd.DataFrame(rows)


class ShortWindowReportTests(unittest.TestCase):
    def test_weights_people_then_tasks_not_windows(self):
        result = independent_metrics(observations(), 'score')
        self.assertAlmostEqual(result['accuracy'], .75)
        self.assertAlmostEqual(result['balanced_accuracy'], .5)
        self.assertAlmostEqual(result['within_person_balanced_accuracy'], .5)
        self.assertEqual(result['people_with_both_classes'], 1)
        self.assertIsNone(result['per_person']['B']['balanced_accuracy'])

    def test_duplicate_windows_do_not_reweight_tasks(self):
        frame = observations()
        more = pd.concat([frame, frame[frame.unit_id == 'a1']], ignore_index=True)
        for key in ('accuracy', 'balanced_accuracy', 'within_person_balanced_accuracy'):
            self.assertAlmostEqual(independent_metrics(frame, 'score')[key], independent_metrics(more, 'score')[key])

    def test_pairing_accepts_reordered_rows_but_rejects_changed_labels(self):
        frame = observations();other = frame.iloc[::-1].copy()
        left, right = align_pair(frame, other)
        np.testing.assert_array_equal(left.row_id, right.row_id)
        other.loc[0, 'outcome'] = 1
        with self.assertRaisesRegex(ValueError, 'outcome'):
            align_pair(frame, other)

    def test_pairing_rejects_missing_or_duplicated_observations(self):
        frame = observations()
        with self.assertRaisesRegex(ValueError, 'counts'):
            align_pair(frame, frame.iloc[:-1])
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            align_pair(frame, pd.concat([frame, frame.iloc[:1]]))

    def test_duration_interval_resamples_people_not_windows(self):
        baseline = observations();candidate = baseline.copy();candidate['score'] = candidate.outcome
        effect = duration_effect(candidate, baseline, 'score')
        balanced = effect['balanced_accuracy']
        self.assertEqual(balanced['participants'], ['A'])
        self.assertAlmostEqual(balanced['mean_difference'], .5)
        np.testing.assert_array_equal(balanced['percentile_95_ci'], [.5, .5])
        self.assertAlmostEqual(effect['accuracy']['mean_difference'], .25)
        self.assertEqual(effect['accuracy']['people'], 2)

    def test_empty_or_invalid_predictions(self):
        frame = observations()
        self.assertIsNone(independent_metrics(frame.iloc[:0], 'score')['accuracy'])
        frame.loc[0, 'score'] = np.nan
        with self.assertRaises(ValueError):
            independent_metrics(frame, 'score')


if __name__ == '__main__':
    unittest.main()
