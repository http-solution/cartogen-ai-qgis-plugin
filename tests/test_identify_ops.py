"""PLAN-023 R9-5: the pure helpers of identify_at_point, with the cap as the known answer. No QGIS and no numpy needed."""
import math
import unittest

from cartogen_ai.core.agent.tools import identify_ops as io


class TestCap(unittest.TestCase):
    def test_sixty_matches_across_two_layers_keep_fifty_and_say_so(self):
        kept, count, truncated = io.cap_features([("a", list(range(40))), ("b", list(range(20)))])
        self.assertEqual((count, truncated), (50, True))
        self.assertEqual([(n, len(r)) for n, r in kept], [("a", 40), ("b", 10)])

    def test_exactly_fifty_is_not_truncated_and_a_fully_cut_layer_is_dropped(self):
        self.assertEqual(io.cap_features([("a", list(range(50)))])[2], False)
        kept, count, truncated = io.cap_features([("a", list(range(50))), ("b", [1])])
        self.assertEqual(([n for n, _ in kept], count, truncated), (["a"], 50, True))

    def test_a_smaller_cap_and_empty_groups(self):
        self.assertEqual(io.cap_features([("a", [1, 2, 3]), ("e", [])], cap=2), ([("a", [1, 2])], 2, True))
        self.assertEqual(io.cap_features([]), ([], 0, False))


class TestPlainValue(unittest.TestCase):
    def test_values(self):
        self.assertEqual(io.plain_value(3), 3)
        self.assertEqual(io.plain_value("x"), "x")
        self.assertEqual(io.plain_value(2.5), 2.5)
        self.assertIsNone(io.plain_value(None))
        self.assertIsNone(io.plain_value(math.nan))
        self.assertIsNone(io.plain_value(math.inf))

        class Date:
            def __str__(self):
                return "2020-01-02"

        class Null:
            def __str__(self):
                return "NULL"

        self.assertEqual(io.plain_value(Date()), "2020-01-02")
        self.assertIsNone(io.plain_value(Null()))


class TestCheck(unittest.TestCase):
    def test_valid(self):
        self.assertIsNone(io.check_request(1, 2))
        self.assertIsNone(io.check_request(1.5, -2, 10, ["a"], 20))

    def test_invalid(self):
        for args in (("a", 2), (1, None), (1, 2, -1), (1, 2, "r"), (1, 2, 0, []), (1, 2, 0, ["a", ""]), (1, 2, 0, "a"), (1, 2, 0, None, 0), (1, 2, 0, None, 51),
                     (float("nan"), 1)):
            self.assertIsNotNone(io.check_request(*args), args)


if __name__ == "__main__":
    unittest.main()
