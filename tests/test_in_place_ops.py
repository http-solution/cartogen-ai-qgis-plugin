"""PLAN-023 R11-3: the pure request check and card text of run_algorithm_in_place. No QGIS needed."""
import unittest

from cartogen_ai.core.agent.tools import in_place_ops as ipo


class TestCheck(unittest.TestCase):
    def test_valid_requests(self):
        self.assertIsNone(ipo.check_request("native:smoothgeometry", "roads", True, {"ITERATIONS": 2}))
        self.assertIsNone(ipo.check_request("native:translategeometry", "pts", False, None))

    def test_bad_requests_are_refused(self):
        cases = [("smooth", "a", True, None), (None, "a", True, None), ("native:x", "", True, None), ("native:x", 5, True, None), ("native:x", "a", "yes", None),
                 ("native:x", "a", True, [1]), ("native:x", "a", True, {"INPUT": "b"}), ("native:x", "a", True, {"output": "b"}),
                 ("native:x", "a", True, {"OUTPUT_LINES": "b"}), ("native:x", "a", True, {"k": {"n": 1}}), ("native:x y", "a", True, None)]
        for args in cases:
            self.assertIsNotNone(ipo.check_request(*args), args)

    def test_the_card_text_counts_features(self):
        self.assertEqual(ipo.count_text(1), "1 feature")
        self.assertEqual(ipo.count_text(3), "3 features")
        text = ipo.describe("Smooth", "roads", 3, True)
        for word in ("IN PLACE", "the selected", "'roads'", "3 features", "undoable"):
            self.assertIn(word, text)
        self.assertIn("every feature", ipo.describe("Smooth", "roads", 1, False))


if __name__ == "__main__":
    unittest.main()
