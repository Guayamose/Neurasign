"""Evidence boundaries and unsupported information in experiment 011."""
from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/"src"))

from neurasign_engine.causal import CHANNELS, Trace
from neurasign_engine.short_window_features import SHORT_FEATURES, extract_short_window


def traces(duration=61):
    result = {}
    for name, (rate, unit) in CHANNELS.items():
        times = np.arange(duration*rate)/rate
        values = {"bvp": lambda t: np.sin(2*np.pi*1.2*t), "eda": lambda t: 1+.01*t,
                  "temperature": lambda t: 32+.01*t, "acc_x": lambda t: .01*np.sin(t),
                  "acc_y": lambda t: .01*np.cos(t), "acc_z": lambda t: np.ones(len(t)),
                  "heart_rate": lambda t: np.full(len(t), 72.)}[name](times)
        result[name] = Trace(times, values, rate, unit)
    return result


class ShortWindowFeatureTests(unittest.TestCase):
    def assert_features_equal(self, first, second):
        np.testing.assert_allclose([first["features"][name] for name in SHORT_FEATURES],
                                   [second["features"][name] for name in SHORT_FEATURES], equal_nan=True)

    def test_only_one_second_contributes_and_boundaries_are_half_open(self):
        source = traces()
        original = extract_short_window(source, 60, 1)
        for trace in source.values():
            trace.values[(trace.times < 59) | (trace.times >= 60)] = 1e9
        self.assert_features_equal(original, extract_short_window(source, 60, 1))
        sliced = {name: Trace(trace.times[(trace.times >= 59) & (trace.times < 60)],
                             trace.values[(trace.times >= 59) & (trace.times < 60)], trace.rate, trace.unit)
                  for name, trace in source.items()}
        self.assert_features_equal(original, extract_short_window(sliced, 60, 1))
        self.assertEqual(original["window_start"], 59)
        self.assertEqual(original["channel_quality"]["bvp"]["samples"], 64)
        changed = extract_short_window(source, 60, 60)
        self.assertNotEqual(original["features"]["bvp_mean"], changed["features"]["bvp_mean"])

    def test_no_heart_rate_beats_hrv_or_spectral_inputs(self):
        self.assertEqual(len(SHORT_FEATURES), 23)
        self.assertFalse(any(any(word in name for word in ("heart_rate", "pulse", "spectral", "periodicity", "interval"))
                             for name in SHORT_FEATURES))
        source = traces(); original = extract_short_window(source, 60, 1)
        source["heart_rate"].values[:] = np.nan
        self.assert_features_equal(original, extract_short_window(source, 60, 1))
        del source["heart_rate"]
        self.assert_features_equal(original, extract_short_window(source, 60, 1))

    def test_one_hz_channel_supports_mean_without_inventing_variability(self):
        source = traces()
        source["temperature"] = Trace(np.array([59.]), np.array([32.5]), 1., "degC")
        result = extract_short_window(source, 60, 1)
        self.assertEqual(result["status"], "features_ready")
        self.assertEqual(result["features"]["temperature_mean"], 32.5)
        self.assertIsNone(result["channel_quality"]["temperature"]["cadence_relative_error"])
        self.assertTrue(all(np.isnan(value) for name, value in result["features"].items()
                            if name.startswith("temperature_") and name != "temperature_mean"))

    def test_misaligned_axes_mask_motion_without_interpolating(self):
        source = traces()
        source["acc_y"].times += .001
        result = extract_short_window(source, 60, 1)
        self.assertIn("misaligned_acceleration_axes", result["reasons"])
        self.assertTrue(all(np.isnan(value) for name, value in result["features"].items()
                            if name.startswith("motion_") or name == "acc_clipped_fraction"))
        self.assertTrue(np.isfinite(result["features"]["bvp_std"]))

    def test_missing_empty_and_low_coverage_channels_stay_nan(self):
        empty = extract_short_window({}, 60, 1)
        self.assertEqual(empty["status"], "insufficient_data")
        self.assertTrue(all(np.isnan(value) for value in empty["features"].values()))
        source = traces()
        source["eda"] = Trace(np.array([59., 59.25, 59.5]), np.ones(3), 4., "uS")
        source["temperature"] = Trace(np.array([]), np.array([]), 4., "degC")
        result = extract_short_window(source, 60, 1)
        self.assertEqual(result["channel_quality"]["eda"]["coverage"], .75)
        self.assertIn("incomplete_eda", result["reasons"])
        self.assertIn("incomplete_temperature", result["reasons"])
        self.assertTrue(np.isnan(result["features"]["eda_mean"]))

    def test_width_and_end_validation(self):
        for width in (0, -1, np.nan, np.inf, True, "1"):
            with self.subTest(width=width), self.assertRaises(ValueError):
                extract_short_window({}, 60, width)
        for end in (np.inf, np.nan, True, "60"):
            with self.subTest(end=end), self.assertRaises(ValueError):
                extract_short_window({}, end, 1)

    def test_same_statistics_have_different_one_and_sixty_second_evidence(self):
        source = traces()
        short = extract_short_window(source, 60, 1)
        long = extract_short_window(source, 60, 60)
        self.assertEqual(short["status"], long["status"])
        self.assertAlmostEqual(short["features"]["eda_mean"], 1+.01*59.375)
        self.assertAlmostEqual(long["features"]["eda_mean"], 1+.01*29.875)
        self.assertAlmostEqual(short["features"]["eda_slope_per_second"], .01)
        self.assertAlmostEqual(long["features"]["eda_slope_per_second"], .01)
        self.assertAlmostEqual(short["features"]["eda_last_third_minus_first_third"], .00625)
        self.assertAlmostEqual(long["features"]["eda_last_third_minus_first_third"], .4)

    def test_first_second_needs_no_warmup_or_history(self):
        result = extract_short_window(traces(duration=1), 1, 1)
        self.assertEqual(result["status"], "features_ready")
        self.assertTrue(all(np.isfinite(value) for value in result["features"].values()))


if __name__ == "__main__":
    unittest.main()
