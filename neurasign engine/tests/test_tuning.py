"""Regression checks for isolation and model-selection boundaries."""
from pathlib import Path
import sys
import unittest

import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from neurasign_engine.schema import FEATURES, TARGETS
from neurasign_engine.tuning import (
    PROFILES, candidate_search, candidates, development_only,
    fit_candidate, person_folds, predict_candidate, summarize_intervals,
)


def fixture():
    rows = []
    for person in range(6):
        for unit in range(3):
            for window in range(3):
                rows.append({**{name: person + unit + window for name in FEATURES},
                             **{name: 2.5 if name == "mental_effort" else 50. for name in TARGETS},
                             "participant": f"P{person}", "session": "Lab1",
                             "unit_id": f"P{person}U{unit}", "window_index": window})
    return pd.DataFrame(rows)


class TuningTests(unittest.TestCase):
    def test_test_people_never_enter_summaries_or_search(self):
        frame = fixture()
        split = {"development": [f"P{i}" for i in range(5)], "test": ["P5"]}
        reference = summarize_intervals(development_only(frame, split))
        frame.loc[frame.participant == "P5", [*FEATURES, *TARGETS]] = 1e9
        changed = summarize_intervals(development_only(frame, split))
        pd.testing.assert_frame_equal(reference, changed)
        self.assertNotIn("P5", reference.participant.tolist())

    def test_interval_features_are_independent_and_label_free(self):
        frame = fixture()
        first = summarize_intervals(frame)
        changed = frame.copy()
        changed.loc[:, list(TARGETS)] = 99.
        second = summarize_intervals(changed)
        pd.testing.assert_frame_equal(first[PROFILES["distribution"]], second[PROFILES["distribution"]])
        isolated = summarize_intervals(frame[frame.unit_id == "P0U0"])
        np.testing.assert_allclose(isolated[PROFILES["distribution"]], first.iloc[[0]][PROFILES["distribution"]])
        self.assertEqual(len(first), 18)
        self.assertEqual(first.iloc[0]["HRV_MeanNN__mean"], 1.)
        self.assertEqual(first.iloc[0]["HRV_MeanNN__median"], 1.)
        self.assertEqual(first.iloc[0]["HRV_MeanNN__q10"], .2)
        self.assertFalse(set(PROFILES["distribution"]) & set(TARGETS))
        frame.loc[0, "mental_demand"] = 99.
        with self.assertRaises(ValueError):
            summarize_intervals(frame)

    def test_nested_splits_exclude_outer_people_from_inner_search(self):
        people = [f"P{i}" for i in range(19)]
        covered = []
        for train, validation in person_folds(people, 5):
            covered.extend(validation)
            for inner_train, inner_validation in person_folds(train, 3):
                self.assertFalse(set(inner_train) & set(inner_validation))
                self.assertFalse(set(validation) & (set(inner_train) | set(inner_validation)))
                self.assertEqual(set(inner_train) | set(inner_validation), set(train))
        self.assertEqual(sorted(covered), sorted(people))

    def test_all_candidates_fit_and_constants_can_win(self):
        rows = summarize_intervals(fixture())
        with threadpool_limits(limits=2):
            for config in candidates():
                model = fit_candidate(config, rows, "mental_demand")
                prediction = predict_candidate(model, config, rows, "mental_demand")
                np.testing.assert_allclose(prediction, 50., atol=1e-8)
            chosen, _ = candidate_search(rows, "mental_demand", person_folds(rows.participant, 3), candidates()[:3])
        self.assertEqual(chosen["kind"], "constant")

    def test_preprocessing_uses_only_fitting_people(self):
        rows = summarize_intervals(fixture())
        rows.loc[:, "HRV_MeanNN__mean"] = np.nan
        rows.loc[rows.participant == "P5", "HRV_MeanNN__mean"] = 1e9
        config = next(config for config in candidates() if config["name"] == "means_ridge_1")
        train = rows[rows.participant != "P5"]
        model = fit_candidate(config, train, "mental_demand")
        self.assertEqual(model.named_steps["simpleimputer"].statistics_[0], 0.)
        self.assertEqual(model.named_steps["standardscaler"].mean_[0], 0.)


if __name__ == "__main__":
    unittest.main()
