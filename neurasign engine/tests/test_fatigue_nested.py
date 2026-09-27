import sys
from pathlib import Path
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from neurasign_engine import fatigue_nested as fn
from neurasign_engine.fatigue_nested_verify import calculate


class FatigueNestedTests(unittest.TestCase):
    def sensor_frame(self):
        values = {}
        for signal in fn.SIGNALS:
            for stat in ('mean', 'std', 'p10', 'p50', 'p90'):
                for window in ('day', 'last60'):
                    values[f'{window}__{signal}__{stat}'] = [10., 20., np.nan]
                values[f'day__{signal}__{stat}__past7_delta'] = [2., 5., np.nan]
        return pd.DataFrame(values)

    def test_labels_and_metadata_do_not_change_features(self):
        frame = self.sensor_frame()
        frame['rating'] = [0, 50, 100]
        frame['participant'] = ['A', 'B', 'C']
        x, p = fn.features(frame, ['day__hr_mean__mean'])
        frame.rating = [100, 0, 50]
        frame.participant = ['X', 'Y', 'Z']
        frame['date'] = ['tomorrow']*3
        altered, q = fn.features(frame, ['day__hr_mean__mean'])
        pd.testing.assert_frame_equal(x, altered)
        self.assertEqual(p, q)
        self.assertTrue(all(not {'rating', 'participant', 'date'}.intersection(c) for c in p.values()))

    def test_history_transform_uses_only_provided_past_delta(self):
        frame = self.sensor_frame()
        transformed, _ = fn.features(frame, ['day__hr_mean__mean'])
        self.assertAlmostEqual(transformed.loc[0, 'change__hr_mean__mean__history'], 2/8)
        self.assertAlmostEqual(transformed.loc[0, 'change__eda_mean__mean__history'], np.log(11)-np.log(9))
        self.assertTrue(np.isnan(transformed.loc[2, 'change__hr_mean__mean__history']))
        frame.loc[1, :] = 999
        changed, _ = fn.features(frame, ['day__hr_mean__mean'])
        pd.testing.assert_series_equal(transformed.iloc[0], changed.iloc[0])

    def test_grouped_folds_never_split_a_person(self):
        frame = pd.DataFrame({'participant': np.repeat(list('ABCDEFGH'), [2, 3, 4, 5, 6, 7, 8, 9])})
        outer = fn.grouped_folds(frame, 4)
        validated = []
        for fold in outer:
            self.assertFalse(set(fold['training_people']) & set(fold['validation_people']))
            validated += fold['validation_people']
            inner = fn.grouped_folds(frame[frame.participant.isin(fold['training_people'])], 3)
            for f in inner:
                self.assertFalse((set(f['training_people']) | set(f['validation_people'])) & set(fold['validation_people']))
        self.assertEqual(sorted(validated), list('ABCDEFGH'))

    def test_threshold_search_uses_weighted_sensitivity_not_accuracy(self):
        frame = pd.DataFrame({'participant': ['A']*8+['B']*2, 'target': [0]*8+[1]*2})
        threshold, scores = fn.choose_threshold(frame, np.array([.1]*8+[.4]*2))
        self.assertEqual(threshold, .4)
        self.assertEqual(scores['balanced_accuracy'], 1.)
        self.assertEqual(scores['high_recall'], 1.)

    def test_independent_metrics_respect_equal_person_mass(self):
        frame = pd.DataFrame({'participant': ['A']*8+['B']*2, 'target': [0]*8+[1]*2})
        independent = calculate(frame, np.zeros(10), True)
        self.assertAlmostEqual(independent['person_weighted_accuracy'], .5)
        self.assertAlmostEqual(independent['unweighted_accuracy'], .8)
        actual = fn.classification_metrics(frame, np.zeros(10))
        for key in actual:
            np.testing.assert_allclose(actual[key], independent[key]) if actual[key] is not None else self.assertIsNone(independent[key])
        regression = frame.copy(); regression.target *= 100
        scores = calculate(regression, np.zeros(10), False)
        self.assertEqual(scores['mae'], 50.)

    def test_imputation_is_training_only_and_handles_missing_channels(self):
        training = pd.DataFrame({'participant': ['A', 'A', 'B', 'B'], 'target': [0, 1, 0, 1],
                                 'signal': [0., 1., 2., np.nan], 'absent': [np.nan]*4})
        model = fn.fit(training, ['signal', 'absent'], 'classification', 'linear_strong')
        self.assertEqual(model.steps[0][1].statistics_[0], 1.)
        unseen = training.copy(); unseen.signal = [10000, np.nan, -10000, 10]
        p = fn.predict(model, unseen, ['signal', 'absent'], 'classification')
        self.assertTrue(np.isfinite(p).all())
        self.assertEqual(model.steps[0][1].statistics_[0], 1.)


if __name__ == '__main__':
    unittest.main()
