from pathlib import Path
import sys
import unittest

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from neurasign_engine.swell import FEATURES, TARGETS, PROFILES, prepare_frame, metrics


def fixture():
    rows = []
    for person, heart in (("P1", 60.), ("P2", 90.)):
        for minute, condition in enumerate(["R", "R", "R", "N", "N", "R"]):
            rows.append({"PP": person, "Blok": "1", "Condition": condition,
                         "timestamp": f"20260926T120{minute}00000", "HR": heart if minute < 3 else 80.,
                         "RMSSD": .05, "SCL": 20., **{column: np.nan if condition == "R" else 5. for column in TARGETS.values()}})
    return pd.DataFrame(rows)


class SwellTests(unittest.TestCase):
    def test_reference_excludes_future_people_and_labels(self):
        source = fixture()
        data, _ = prepare_frame(source)
        self.assertEqual(data.HR_minus_prior_rest.tolist(), [20., 20., -10., -10.])
        source.loc[source.Condition == "R", list(TARGETS.values())] = 9.
        source.loc[source.timestamp.str.contains("120500"), FEATURES] = 9999.
        changed, _ = prepare_frame(source)
        np.testing.assert_allclose(data[PROFILES["prior_rest"]], changed[PROFILES["prior_rest"]], equal_nan=True)
        self.assertTrue(set(PROFILES["prior_rest"]).isdisjoint(set(TARGETS.values()) | {"PP", "Blok", "Condition", "timestamp"}))

    def test_missing_channels_are_not_fabricated_and_empty_minutes_are_excluded(self):
        source = fixture()
        source.loc[source.PP == "P1", "HR"] = np.nan
        source.loc[(source.PP == "P2") & (source.Condition == "N"), FEATURES] = np.nan
        data, audit = prepare_frame(source)
        self.assertEqual(len(data), 2)
        self.assertTrue(data.HR.isna().all() and data.HR_minus_prior_rest.isna().all())
        self.assertEqual(audit["all_physiology_missing_labeled_minutes"], 2)

    def test_repeated_labels_have_equal_block_and_person_weight_and_errors_do_not_cancel(self):
        rows = pd.DataFrame({"participant": ["A", "A", "B"], "unit_id": ["a", "a", "b"], "mental_demand": [5., 5., 5.]})
        result = metrics(rows, "mental_demand", [0., 10., 5.])
        self.assertEqual(result["participant_macro_mae"], 2.5)
        self.assertEqual(result["within_one_point_fraction"], .5)

    def test_duplicate_minutes_and_inconsistent_labels_are_rejected(self):
        source = fixture()
        with self.assertRaises(ValueError):
            prepare_frame(pd.concat([source, source.iloc[:1]], ignore_index=True))
        source.loc[(source.PP == "P1") & (source.timestamp.str.contains("120400")), "MentalDemand"] = 7.
        with self.assertRaises(ValueError):
            prepare_frame(source)


if __name__ == "__main__":
    unittest.main()
