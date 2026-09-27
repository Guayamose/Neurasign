"""Guard against overlapping-duration inflation and invalid audit counterfactuals."""
from pathlib import Path
import sys
import unittest

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from neurasign_engine.causal import FEATURES, extract_window
from neurasign_engine.information_audit import PULSE, pulse_diagnostics, union_seconds, variant_data
from test_causal import synthetic_traces


class InformationAuditTests(unittest.TestCase):
    def test_union_counts_overlaps_and_duplicates_once(self):
        self.assertEqual(union_seconds([(0, 60), (10, 70), (10, 70), (90, 150)]), 130)
        self.assertEqual(union_seconds([]), 0)
        with self.assertRaises(ValueError):
            union_seconds([(60, 0)])

    def test_counterfactual_matches_original_when_quality_passes_and_is_causal(self):
        traces = synthetic_traces()
        expected = extract_window(traces, 60)["features"]
        first = pulse_diagnostics(traces["bvp"], 60, 72)
        np.testing.assert_allclose([first[k] for k in PULSE], [expected[k] for k in PULSE], equal_nan=True)
        traces["bvp"].values[traces["bvp"].times >= 60] = 1e9
        self.assertEqual(first, pulse_diagnostics(traces["bvp"], 60, 72))

    def test_relaxation_preserves_beat_checks_and_ablation_removes_shared_hr_feature(self):
        rows = pd.DataFrame([{k: np.nan if k in PULSE else 1. for k in FEATURES}] * 3)
        diagnostic = pd.DataFrame([{**{k: 72. for k in PULSE}, "basic_pulse_ok": basic,
                                    "periodicity_gate": periodicity}
                                   for basic, periodicity in [(True, False), (True, True), (False, False)]])
        motion, _ = variant_data(rows, diagnostic, "relax_motion")
        both, _ = variant_data(rows, diagnostic, "relax_motion_periodicity")
        self.assertEqual(motion.pulse_rate_bpm.notna().tolist(), [True, False, False])
        self.assertEqual(both.pulse_rate_bpm.notna().tolist(), [True, True, False])
        _, features = variant_data(rows, diagnostic, "without_device_hr")
        self.assertNotIn("pulse_rate_device_difference_bpm", features)
        self.assertFalse(any(k.startswith("heart_rate_") for k in features))
        self.assertTrue(rows.pulse_rate_bpm.isna().all())


if __name__ == "__main__":
    unittest.main()
