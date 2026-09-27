from pathlib import Path
import sys
import unittest

import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from neurasign_engine.causal import FEATURES, PIPELINE, CausalStream
from neurasign_engine.causal_training import CausalModel, fit_model, thin_training, window_metrics
from neurasign_engine.schema import TARGETS
from neurasign_engine.streaming import ObservationBridge, dispatch


class CausalTrainingTests(unittest.TestCase):
    def test_window_errors_cannot_cancel_before_scoring(self):
        frame = pd.DataFrame({"participant": ["A", "A"], "unit_id": ["u", "u"],
                              "session": ["Lab1", "Lab1"], "mental_demand": [50., 50.]})
        result = window_metrics(frame, "mental_demand", [0., 100.])
        self.assertEqual(result["participant_macro_mae"], 50.)
        self.assertEqual(result["secondary_interval_average_mae"], 0.)
        self.assertEqual(result["within_tolerance_fraction"], 0.)

    def test_training_subsampling_does_not_depend_on_labels(self):
        frame = pd.DataFrame({"unit_id": ["u"] * 100 + ["v"] * 5,
                              "window_end": list(range(100)) + list(range(5)), "effort": 10.})
        first = thin_training(frame)
        frame["effort"] = 90.
        second = thin_training(frame)
        self.assertEqual(first.index.tolist(), second.index.tolist())
        self.assertEqual(first.unit_id.value_counts().to_dict(), {"u": 20, "v": 5})

    def test_constant_selection_is_not_presented_as_signal_interpretation(self):
        rows = pd.DataFrame([{**{key: 1. for key in FEATURES}, "window_end": float(i),
                              "participant": "A", "unit_id": "u", **{key: 2. for key in TARGETS}}
                             for i in range(10)])
        heads, metadata = {}, {"targets": {}}
        config = {"kind": "constant", "strategy": "median"}
        with threadpool_limits(limits=2):
            for target in TARGETS:
                model, _ = fit_model(config, rows, target)
                heads[target] = {"config": config, "model": model}
                metadata["targets"][target] = {"selected": {"participant_macro_mae": 1.},
                                                "constant": {"participant_macro_mae": 1.}}
            engine = CausalModel(heads, metadata)
            window = {"pipeline_id": PIPELINE, "features": {key: 1. for key in FEATURES}, "status": "features_ready"}
            result = engine.predict(window)
        self.assertIsNone(result["confidence"])
        for item in result["estimates"].values():
            self.assertEqual(item["status"], "no_predictive_model_selected")
            self.assertNotIn("predicted_rating", item)
        window["status"] = "insufficient_data"
        self.assertFalse(engine.predict(window)["estimates"])

    def test_observation_bridge_source_units_and_idempotency(self):
        stream = CausalStream()
        bridge = ObservationBridge(stream, "source-a", {"electrodermal_conductance": 4.})
        observation = {"id": "one", "source_id": "source-a", "metric": "electrodermal_conductance",
                       "unit": "µS", "measured_at": "2026-01-01T00:00:00.750000Z",
                       "value": 1., "samples": [1., 1., 1., 1.], "sample_offsets_ms": [-750., -500., -250., 0.]}
        self.assertTrue(bridge.push(observation))
        self.assertFalse(bridge.push(observation))
        self.assertEqual(len(stream.traces["eda"].times), 4)
        persisted_stream = CausalStream()
        persisted = ObservationBridge(persisted_stream, "source-a", {"electrodermal_conductance": 4.})
        self.assertTrue(persisted.push({**observation, "measured_at": 1767225600.75, "measurement_kind": "sample"}))
        np.testing.assert_array_equal(stream.traces["eda"].times, persisted_stream.traces["eda"].times)
        for changed in ({"source_id": "source-b"}, {"unit": "S"}, {"interval_seconds": 60},
                        {"value": 2.}, {"measurement_kind": "summary"},
                        {"sample_offsets_ms": [-750., -500., 0., 0.]}):
            with self.assertRaises(ValueError):
                bridge.push({**observation, **changed})

    def test_clock_mismatch_cannot_expand_into_unbounded_empty_windows(self):
        stream = CausalStream()
        stream.push("eda", [0., .25], [1., 1.], 4., "uS")
        with self.assertRaises(ValueError):
            dispatch(stream, {"type": "watermark", "timestamp": 1700000000.})


if __name__ == "__main__":
    unittest.main()
