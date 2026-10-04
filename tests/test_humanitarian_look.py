# -*- coding: utf-8 -*-
"""HX1 humanitarian map looks for analysis result fields: the pure class and palette rules, offline. The renderer needs QGIS
(tests/test_humanitarian_look_live.py)."""
import random
import unittest

from cartogen_ai.core.agent.tools import humanitarian_style as h
from cartogen_ai.core.agent.tools.analysis_tools import _severity_class


class TestSeverityRanges(unittest.TestCase):
    def test_five_classes_with_the_tools_own_boundaries(self):
        ranges = h.severity_ranges()
        self.assertEqual(len(ranges), 5)
        self.assertEqual([r[2] for r in ranges], h.SEVERITY_COLORS)

    def test_every_score_lands_in_the_class_calculate_severity_index_reports(self):
        # QGIS ranges include both ends; an exact 0.2 must be class 2 on the map as in the tool's own result
        ranges = h.severity_ranges()
        scores = [0, 0.2, 0.4, 0.6, 0.8, 1.0, 0.19999999999999998, 0.5999999999999999] + [random.random() for _ in range(3000)]
        for score in scores:
            classes = [i + 1 for i, (low, high, _c, _l) in enumerate(ranges) if low <= score <= high]
            self.assertEqual(classes[:1], [_severity_class(score)], score)


class TestCountRanges(unittest.TestCase):
    def test_heavy_tailed_counts_get_rounded_increasing_limits(self):
        ranges = h.count_ranges([0, 0, 120, 450, 980, 1500, 2300, 9000, 15000, 80000, None, "x"], h.PIN_COLORS)
        lows = [r[0] for r in ranges]
        self.assertEqual(lows, sorted(lows))
        self.assertEqual(ranges[0][3], "0")                       # a real zero has its own class
        self.assertTrue(all(r[1] >= r[0] for r in ranges))

    def test_a_single_value_is_one_class_and_nothing_numeric_is_none(self):
        self.assertEqual(len(h.count_ranges([5, 5, 5], h.PIN_COLORS)), 1)
        self.assertEqual(h.count_ranges([None, "n/a"], h.PIN_COLORS), [])
        self.assertEqual(h.count_ranges([], h.PIN_COLORS), [])

    def test_only_zeros(self):
        self.assertEqual([r[3] for r in h.count_ranges([0, 0], h.PIN_COLORS)], ["0"])

    def test_negative_values_are_ignored(self):
        self.assertEqual(h.count_ranges([-3, -1], h.PIN_COLORS), [])

    def test_colours_run_from_pale_to_dark(self):
        ranges = h.count_ranges(list(range(1, 200)), h.PIN_COLORS)
        self.assertEqual(ranges[0][2], h.PIN_COLORS[0])
        self.assertEqual(ranges[-1][2], h.PIN_COLORS[-1])


class TestRankAndGap(unittest.TestCase):
    def test_rank_bands_and_short_lists(self):
        self.assertEqual([r[3] for r in h.rank_ranges(30, 5)], ["Rank 1 to 5", "Rank 6 to 10", "Rank 11 and below"])
        self.assertEqual(len(h.rank_ranges(4, 5)), 1)
        # tied ranks sit at integers, boundaries at .5
        low, high = h.rank_ranges(30, 5)[0][:2]
        self.assertTrue(low < 1 and 5 < high < 6)

    def test_gap_categories_only_for_values_present(self):
        cats = h.presence_gap_categories(["gap", "covered", None])
        self.assertEqual([c[0] for c in cats], ["gap", "covered", ""])
        self.assertEqual(h.presence_gap_categories(["x"]), [])


class TestLookHint(unittest.TestCase):
    def test_hint_names_the_tool_and_arguments(self):
        hint = h.look_hint("Districts", "severity", "sev")
        self.assertEqual(hint["tool"], "apply_humanitarian_look")
        self.assertEqual(hint["args"], {"layer_name": "Districts", "look": "severity", "field": "sev"})
        self.assertIn("Offer", hint["note"])

    def test_extra_arguments_and_missing_field(self):
        self.assertEqual(h.look_hint("D", "rank", "r", top_k=5)["args"]["top_k"], 5)
        self.assertNotIn("top_k", h.look_hint("D", "rank", "r", top_k=None)["args"])
        self.assertIsNone(h.look_hint("D", "rank", None))


class TestToolIsWired(unittest.TestCase):
    def test_registered_classified_and_routed(self):
        from cartogen_ai.core.agent import tool_operations
        from cartogen_ai.core.agent.tools import TOOL_REGISTRY
        self.assertIn("apply_humanitarian_look", TOOL_REGISTRY)
        self.assertEqual(tool_operations.get_tool_operation_type("apply_humanitarian_look"), tool_operations.MODIFY)

    def test_without_qgis_it_says_so(self):
        from cartogen_ai.core.agent.tools import humanitarian_look_tools as t
        if t.QGIS_AVAILABLE:
            self.skipTest("QGIS present")
        self.assertIn("QGIS not available", t.apply_humanitarian_look("L", "severity", "f")["error"])


if __name__ == "__main__":
    unittest.main()


class TestCreatedLayerLooks(unittest.TestCase):
    """HX1b pure rules: road groups and detection bands."""

    def test_road_rules_cover_the_groups_in_order_of_weight(self):
        rules = h.road_rules()
        self.assertEqual([r[0] for r in rules], ["Major roads", "Secondary roads", "Local roads", "Tracks and paths"])
        widths = [r[3] for r in rules]
        self.assertEqual(widths, sorted(widths, reverse=True))
        self.assertIn("'primary'", rules[0][1])
        self.assertIn("'residential'", rules[2][1])
        self.assertTrue(all(r[1].startswith('"highway" IN (') for r in rules))

    def test_road_rules_use_the_given_field_name(self):
        self.assertTrue(h.road_rules("hwy")[0][1].startswith('"hwy" IN ('))

    def test_every_listed_highway_value_is_in_exactly_one_group(self):
        seen = {}
        for label, _c, _w, values in h.ROAD_GROUPS:
            for v in values:
                self.assertNotIn(v, seen, v)
                seen[v] = label

    def test_detection_bands_cover_zero_to_one_without_gaps(self):
        ranges = h.detection_ranges()
        self.assertEqual(len(ranges), 3)
        for score in (0.0, 0.4, 0.5999999, 0.6, 0.79, 0.8, 0.95, 1.0):
            hits = [r for r in ranges if r[0] <= score <= r[1]]
            self.assertEqual(len(hits), 1, score)
        self.assertTrue(all("onfidence" in r[3] for r in ranges))
        self.assertFalse(any("probab" in r[3].lower() for r in ranges))
