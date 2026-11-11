"""PLAN-023 R11-2: the pure request check and result summary of run_processing_batch. No QGIS and no numpy needed."""
import unittest

from cartogen_ai.core.agent.tools import batch_ops as bo


class TestCheck(unittest.TestCase):
    def test_valid_requests(self):
        self.assertIsNone(bo.check_request("native:buffer", ["a", "b", "c"], {"DISTANCE": 5}))
        self.assertIsNone(bo.check_request("native:buffer", [f"l{i}" for i in range(20)]))
        self.assertIsNone(bo.check_request("gdal:slope", ["dem"], None, "INPUT"))

    def test_twenty_one_layers_empty_and_repeated_names_are_refused(self):
        self.assertIn("1 to 20", bo.check_request("native:buffer", [f"l{i}" for i in range(21)]))
        self.assertIn("1 to 20", bo.check_request("native:buffer", []))
        self.assertIn("more than once", bo.check_request("native:buffer", ["a", "b", "a"]))
        self.assertIn("more than once", bo.check_request("native:buffer", ["a", " a "]))

    def test_bad_algorithm_layer_and_parameter_requests(self):
        cases = [("buffer", ["a"]), (None, ["a"]), ("native:buffer", "a"), ("native:buffer", [""]), ("native:buffer", [5]), ("native:buffer", ["a"], [1]),
                 ("native:buffer", ["a"], {"INPUT": "x"}), ("native:buffer", ["a"], {"OUTPUT": "x"}), ("native:buffer", ["a"], {"OUTPUT_LINES": "x"}),
                 ("native:buffer", ["a"], {"X": {"nested": 1}}), ("native:buffer", ["a"], None, "bad name")]
        for args in cases:
            self.assertIsNotNone(bo.check_request(*args), args)

    def test_a_different_input_parameter_name_is_protected_too(self):
        self.assertIn("SOURCE", bo.check_request("native:x", ["a"], {"SOURCE": "y"}, "SOURCE"))


class TestSummary(unittest.TestCase):
    def test_three_successes_and_one_failure_are_partial_and_name_the_failure(self):
        rows = [("a", True, "a_buffer", False), ("b", True, "b_buffer", False), ("dem", False, "needs a vector layer", False), ("c", True, "c_buffer", False)]
        out = bo.summarise(rows)
        self.assertEqual((out["ran"], out["succeeded"], out["partial"], out["stopped_after"]), (4, 3, True, None))
        self.assertEqual(out["failed"], [{"layer": "dem", "error": "needs a vector layer"}])

    def test_all_good_all_bad_and_stopped(self):
        self.assertFalse(bo.summarise([("a", True, "x", False)])["partial"])
        self.assertFalse(bo.summarise([("a", False, "e", False)])["partial"])
        stopped = bo.summarise([("a", True, "x", False), ("b", False, "stopped", True)])
        self.assertEqual(stopped["stopped_after"], 1)

    def test_short_name(self):
        self.assertEqual(bo.short_name("native:buffer"), "buffer")
        self.assertEqual(bo.short_name("gdal:slope"), "slope")


if __name__ == "__main__":
    unittest.main()
