"""Causality, replay/stream equivalence and failure behavior on synthetic signals."""
from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from neurasign_engine.causal import CHANNELS, FEATURES, CausalStream, Trace, extract_window


def synthetic_traces(duration=120):
    result = {}
    for name, (rate, unit) in CHANNELS.items():
        times = np.arange(duration * rate) / rate
        values = {
            "bvp": lambda t: np.sin(2 * np.pi * 1.2 * t) + .1 * np.sin(2 * np.pi * 2.4 * t),
            "eda": lambda t: 1. + .001 * t,
            "temperature": lambda t: 32. + .001 * t,
            "acc_x": lambda t: .01 * np.sin(t), "acc_y": lambda t: .01 * np.cos(t),
            "acc_z": lambda t: np.ones(len(t)), "heart_rate": lambda t: np.full(len(t), 72.),
        }[name](times)
        result[name] = Trace(times, values, rate, unit)
    return result


def replay(traces, step=10, packet_seconds=10):
    stream, outputs = CausalStream(), []
    for end in range(step, 121, step):
        for start in np.arange(end - step, end, packet_seconds):
            for name, trace in traces.items():
                mask = (trace.times >= start) & (trace.times < min(start + packet_seconds, end))
                if mask.any():
                    stream.push(name, trace.times[mask], trace.values[mask], trace.rate, trace.unit)
        outputs.extend(stream.advance(float(end)))
    return outputs, stream


class CausalTests(unittest.TestCase):
    def assert_features_equal(self, first, second):
        np.testing.assert_allclose([first["features"][k] for k in FEATURES],
                                   [second["features"][k] for k in FEATURES], equal_nan=True)

    def test_future_samples_cannot_change_an_emitted_window(self):
        traces = synthetic_traces()
        reference = extract_window(traces, 60.)
        self.assertEqual(reference["status"], "features_ready")
        for trace in traces.values():
            trace.values[trace.times >= 60] = 1e8
        self.assert_features_equal(reference, extract_window(traces, 60.))
        self.assertNotEqual(extract_window(traces, 120.)["status"], "features_ready")

    def test_stream_matches_prefix_extraction_independent_of_packet_size(self):
        traces = synthetic_traces()
        large, stream = replay(traces, packet_seconds=10)
        small, _ = replay(traces, packet_seconds=1)
        self.assertEqual([x["window_end"] for x in large], list(range(60, 121, 10)))
        for left, right in zip(large, small):
            self.assert_features_equal(left, right)
            self.assert_features_equal(left, extract_window(traces, left["window_end"]))
        self.assertTrue(all(len(x.times) <= x.rate * 60 for x in stream.traces.values()))

    def test_pulse_recovery_and_acceleration_units(self):
        result = extract_window(synthetic_traces(), 60.)
        self.assertAlmostEqual(result["features"]["pulse_rate_bpm"], 72., delta=1.)
        self.assertAlmostEqual(result["features"]["motion_mean"], 1., delta=.001)
        self.assertAlmostEqual(result["features"]["eda_slope_per_second"], .001, places=6)
        self.assertIsNone(result["confidence"])

    def test_missing_stale_and_gapped_channels_abstain(self):
        traces = synthetic_traces()
        del traces["eda"]
        self.assertIn("missing_eda", extract_window(traces, 60.)["reasons"])
        traces = synthetic_traces()
        trace = traces["bvp"]
        keep = (trace.times < 30) | (trace.times >= 40)
        traces["bvp"] = Trace(trace.times[keep], trace.values[keep], trace.rate, trace.unit)
        self.assertIn("incomplete_bvp", extract_window(traces, 60.)["reasons"])
        self.assertEqual(extract_window(synthetic_traces(60), 120.)["status"], "insufficient_data")

    def test_motion_masks_pulse_variability_without_fabricating_it(self):
        traces = synthetic_traces()
        traces["acc_z"].values = 1. + .8 * np.sin(traces["acc_z"].times)
        result = extract_window(traces, 60.)
        self.assertIn("pulse_variability_masked_during_high_motion", result["quality_flags"])
        self.assertTrue(np.isnan(result["features"]["pulse_interval_rmssd_ms"]))
        self.assertGreater(result["features"]["motion_std"], .2)

    def test_bad_packets_late_samples_and_source_isolation(self):
        stream = CausalStream()
        with self.assertRaises(ValueError):
            stream.push("acc_x", [0, 1], [1, 2], 1., "counts")
        stream.push("eda", [0., .25], [1., 1.], 4., "uS")
        with self.assertRaises(ValueError):
            stream.push("eda", [.25], [2.], 4., "uS")
        stream.advance(10.)
        with self.assertRaises(ValueError):
            stream.push("eda", [9.], [1.], 4., "uS")
        with self.assertRaises(ValueError):
            stream.advance(5.)
        with self.assertRaises(ValueError):
            stream.push("eda", [11.], [np.nan], 4., "uS")
        self.assertFalse(CausalStream().traces)


if __name__ == "__main__":
    unittest.main()
