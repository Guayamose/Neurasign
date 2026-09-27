"""Feature contracts and training boundaries for the duration comparison."""
import sys
from pathlib import Path
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from neurasign_engine.short_window import feature_columns, fit, predict


def examples():
    rows = []
    for person in ('p1', 'p2'):
        for task in range(4):
            for window in range(3):
                outcome = task % 2
                rows.append({'participant': person, 'session': 'Lab1', 'unit_id': f'{person}/{task}',
                             'source_end': task*100+window, 'window_end': 60+window,
                             'row_id': len(rows), 'outcome': outcome,
                             **{key: outcome+.01*window for key in feature_columns('short1')}})
    return pd.DataFrame(rows)


class ShortWindowTrainingTests(unittest.TestCase):
    def test_matched_profiles_have_same_raw_only_features(self):
        self.assertEqual(feature_columns('short1'), feature_columns('short60'))
        self.assertEqual(len(feature_columns('short1')), 23)
        self.assertFalse(any('heart_rate' in key or 'pulse_interval' in key or '__delta' in key
                             for key in feature_columns('short1')))
        self.assertEqual(len(feature_columns('legacy60')), 28)
        with self.assertRaises(ValueError):
            feature_columns('unknown')

    def test_training_cannot_use_lab2(self):
        data = examples();data.loc[0, 'session'] = 'Lab2'
        with self.assertRaises(ValueError):
            fit(data, 'short1', 'logit1')

    def test_prediction_ignores_labels_and_identity(self):
        data = examples();artifact = fit(data, 'short1', 'logit1')
        before = predict(artifact, data)
        changed = data.copy();changed['outcome'] = 1-changed.outcome
        changed['participant'] = 'different';changed['unit_id'] = 'different'
        changed['mental_demand'] = 999;changed['source_end'] = -123
        np.testing.assert_array_equal(before, predict(artifact, changed))
        self.assertEqual(artifact['evidence_seconds'], 1)
        self.assertFalse(artifact['production_enabled'])
        self.assertEqual(set(artifact['fitting_row_ids']), set(data.row_id))

    def test_single_class_is_explicit_constant(self):
        data = examples();data = data[data.outcome == 1]
        artifact = fit(data, 'short60', 'cat4')
        self.assertEqual(artifact['constant'], 1)
        self.assertNotIn('model', artifact)
        np.testing.assert_array_equal(predict(artifact, data), np.ones(len(data)))


if __name__ == '__main__':
    unittest.main()
