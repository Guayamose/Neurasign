"""Experiment 022: safe source parsing, causality and participant split guards."""
import io
import pickle
import unittest

import numpy as np
import pandas as pd

from neurasign_engine import wesad_stress_022 as benchmark


class WesadStressTests(unittest.TestCase):
    def test_untrusted_globals_and_persistent_references_rejected(self):
        for data in [b'cos\nsystem\n.', b'cbuiltins\neval\n.', b'Pexternal\n.']:
            with self.assertRaises(pickle.UnpicklingError):
                benchmark.NumericOnlyUnpickler(io.BytesIO(data)).load()

    def test_numeric_arrays_allowed_but_object_dtype_rejected(self):
        expected = np.arange(12, dtype=np.float32).reshape(4, 3)
        for protocol in [2, 3, 4]:
            actual = benchmark.NumericOnlyUnpickler(io.BytesIO(pickle.dumps(expected, protocol=protocol)), encoding='latin1').load()
            np.testing.assert_array_equal(expected, actual)
        with self.assertRaises(pickle.UnpicklingError):
            benchmark.inert_dtype('O')
        with self.assertRaises(ValueError):
            benchmark.validate_numeric_tree({'array': np.array([None], dtype=object)})
        with self.assertRaises(ValueError):
            benchmark.validate_numeric_tree({'unexpected': object()})

    def test_predictors_exclude_subject_condition_chest_and_time(self):
        columns = benchmark.PROFILES['wrist_all']
        self.assertEqual(len(columns), len(set(columns)))
        for forbidden in ['participant', 'outcome', 'start_seconds', 'end_seconds', 'condition', 'ECG', 'RESP', 'subject']:
            self.assertNotIn(forbidden, columns)
        self.assertEqual(len(benchmark.candidates()), 32)

    def test_feature_window_has_no_future_dependency(self):
        signals = {channel: np.zeros((120 * rate, 3 if channel == 'ACC' else 1)) for channel, rate in benchmark.RATE.items()}
        signals['BVP'][:, 0] = np.sin(np.arange(len(signals['BVP'])) / 64 * 2 * np.pi)
        signals['TEMP'][:] = 32; signals['EDA'][:] = 1
        before = benchmark.features(signals, 0, 60)
        for channel, rate in benchmark.RATE.items():
            signals[channel][60 * rate:] = 10000
        after = benchmark.features(signals, 0, 60)
        for key in before:
            np.testing.assert_allclose(before[key], after[key], atol=0, equal_nan=True)

    def test_balanced_accuracy_exposes_constant_predictions(self):
        frame = pd.DataFrame({'participant': ['one'] * 10, 'outcome': [0] * 9 + [1], 'score': [0] * 10})
        result = benchmark.metrics(frame, 'score')
        self.assertEqual(result['accuracy'], .9)
        self.assertEqual(result['balanced_accuracy'], .5)
        self.assertEqual(result['stress_condition_recall'], 0.)

    def test_incomplete_or_nonfinite_raw_windows_rejected(self):
        signals = {channel: np.zeros((60 * rate, 3 if channel == 'ACC' else 1)) for channel, rate in benchmark.RATE.items()}
        signals['EDA'][0] = np.nan
        with self.assertRaises(ValueError):
            benchmark.features(signals, 0, 60)
        signals['EDA'][0] = 1
        signals['BVP'] = signals['BVP'][:-1]
        with self.assertRaises(ValueError):
            benchmark.features(signals, 0, 60)

    def test_each_person_and_condition_has_equal_training_weight(self):
        frame = pd.DataFrame({'participant': ['a', 'a', 'a', 'b', 'b'], 'outcome': [0, 0, 1, 0, 1], 'row_id': list('abcde')})
        frame['weight'] = benchmark.training_weights(frame)
        sums = frame.groupby(['participant', 'outcome']).weight.sum().to_numpy()
        np.testing.assert_allclose(sums, sums[0])

    def test_flat_bvp_has_no_fabricated_pulse_frequency(self):
        signals = {channel: np.zeros((60 * rate, 3 if channel == 'ACC' else 1)) for channel, rate in benchmark.RATE.items()}
        result = benchmark.features(signals, 0, 60)
        for key in ['bvp_peak_hr', 'bvp_rmssd', 'bvp_sdnn', 'bvp_dominant_hz', 'bvp_spectral_concentration']:
            self.assertTrue(np.isnan(result[key]))


if __name__ == '__main__':
    unittest.main()
