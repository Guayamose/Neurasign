"""Observed-label integrity and independent evaluation for experiment 012."""
import unittest

import numpy as np
import pandas as pd

from neurasign_engine import stress_benchmark as benchmark


class StressBenchmarkTests(unittest.TestCase):
    def test_neutral_missing_and_invalid_answers_are_not_classes(self):
        np.testing.assert_equal(benchmark.binary_labels([1, 2, 3, 4, 5, np.nan]), [0, 0, np.nan, 1, 1, np.nan])
        with self.assertRaises(ValueError):
            benchmark.binary_labels([0, 6])

    def test_source_headers_are_missing_rather_than_fabricated(self):
        records, audit = benchmark.parse_questionnaire(b'Task,Mental Demand\na,50\n')
        self.assertFalse(audit['stress_header_present'])
        self.assertIsNone(records['a']['value'])

    def test_conflicts_and_malformed_rows_quarantine_whole_task(self):
        data = (b'Task,Mental stress level\na,low\na,high\nb,low\nb,low,shifted\n'
                b'c,nonsense\nvideo_baseline,very very low\nd,high\nd,high\n')
        records, audit = benchmark.parse_questionnaire(data)
        for segment in ('a', 'b', 'c'):
            self.assertIsNone(records[segment]['value'])
        self.assertEqual(records['relaxation_video']['value'], 1)
        self.assertEqual(records['d']['value'], 4)
        self.assertEqual(records['d']['lines'], [8, 9])
        self.assertEqual(audit['conflicting_segment'], 1)
        self.assertEqual(audit['malformed_width'], 1)

    def test_duplicate_headers_and_wrong_session_shape_rejected(self):
        for data in [b'Task,Mental stress level,Mental stress level\n', b'Labeled folder names,Mental stress level\n']:
            with self.assertRaises(ValueError):
                benchmark.parse_questionnaire(data)

    def test_lab2_training_and_questionnaire_predictors_rejected(self):
        frame = pd.DataFrame([{'session': 'Lab2', 'outcome': 0}])
        with self.assertRaises(ValueError):
            benchmark.fit_classifier(frame, 'legacy60', 'logit1')
        self.assertNotIn(benchmark.TARGET, benchmark.FEATURES)
        self.assertFalse(set(benchmark.META) & set(benchmark.FEATURES))

    def test_high_ordinary_accuracy_does_not_hide_constant_behavior(self):
        frame = pd.DataFrame([{'participant': 'a', 'unit_id': str(i), 'outcome': int(i == 9), 'score': 0.}
                              for i in range(10)])
        result = benchmark.independent_metrics(frame, 'score')
        self.assertAlmostEqual(result['accuracy'], .9)
        self.assertAlmostEqual(result['balanced_accuracy'], .5)
        self.assertEqual(result['high_recall'], 0.)
        only_low = benchmark.independent_metrics(frame.iloc[:9], 'score')
        self.assertIsNone(only_low['balanced_accuracy'])
        self.assertIsNone(only_low['within_person_balanced_accuracy'])


if __name__ == '__main__':
    unittest.main()
