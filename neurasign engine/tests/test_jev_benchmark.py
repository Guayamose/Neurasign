import math
from pathlib import Path
import sys
import unittest

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from neurasign_engine.jev_benchmark import (
    FEATURES, MODEL, TARGETS, choose_examples, grid, metrics, parse_answer, payload)


class JevBenchmarkTests(unittest.TestCase):
    def test_test_labels_and_identifiers_cannot_enter_payload(self):
        row = {f: 2.1 for f in FEATURES}
        row.update({t: 99999 for t in TARGETS})
        row.update(participant="private-id", unit_id="private-task", session="private-session", window_end=99999)
        body = payload(row, "universe", [])
        self.assertEqual(set(body["state"]["current"]), set(FEATURES))
        self.assertNotIn("private", str(body))
        self.assertNotIn("99999", str(body))
        self.assertNotIn("ratings", body["state"]["current"])

    def test_example_selection_is_label_independent_and_person_disjoint(self):
        rows = pd.DataFrame([{"participant": f"p{i}", "unit_id": f"p{i}/u", "window_end": j,
                              **{t: i for t in TARGETS}} for i in range(12) for j in range(3)])
        a = choose_examples(rows, ["p0", "p1"])
        rows[list(TARGETS)] = -999
        b = choose_examples(rows, ["p0", "p1"])
        self.assertEqual([(x["participant"], x["window_end"]) for x in a],
                         [(x["participant"], x["window_end"]) for x in b])
        self.assertEqual(len({x["participant"] for x in a}), 8)
        self.assertFalse({x["participant"] for x in a} & {"p0", "p1"})

    def test_errors_precede_averaging_and_people_have_equal_weight(self):
        rows = pd.DataFrame({"participant": ["a", "a", "b"], "unit_id": ["a1", "a1", "b1"], "effort": [5, 5, 5]})
        result = metrics(rows, "effort", [0, 10, 5], "swell")
        self.assertEqual(result["mae"], 2.5)
        self.assertEqual(result["agreement_percent"], 50)

    def test_malformed_answers_do_not_become_predictions(self):
        probabilities = {f"rating_{x}": 0. for x in grid("universe", "mental_effort")}
        probabilities["rating_3"] = 1.
        answer = {"type": "choice", "choice": "rating_3", "confidence": .8, "probabilities": probabilities}
        response = {"model": MODEL, "answers": {"mental_effort": answer}}
        self.assertEqual(parse_answer(response, "universe", "mental_effort"), (3, .8))
        answer["confidence"] = math.nan
        with self.assertRaises(ValueError):
            parse_answer(response, "universe", "mental_effort")
        answer["confidence"] = .8
        answer["choice"] = "invented"
        with self.assertRaises(ValueError):
            parse_answer(response, "universe", "mental_effort")


if __name__ == "__main__":
    unittest.main()
