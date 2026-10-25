"""PLAN-021 WP-B, no QGIS needed: the legend fit decision, the footer slack and the layout name rule."""
import unittest

from cartogen_ai.core.agent.tools._layout_names import layout_name_for, resolve_layout
from cartogen_ai.core.agent.tools.layout_style import (
    FOOTER_FIT_SLACK_MM, FOOTER_PAD_MM, LEGEND_SCALES, legend_title_with_note, pick_legend_scale, plan_footer_growth)


class _Named:
    def __init__(self, name):
        self._name = name

    def name(self):
        return self._name


class TestLegendFit(unittest.TestCase):
    def test_the_first_scale_that_fits_is_chosen(self):
        self.assertEqual(pick_legend_scale([(1.0, 60), (0.85, 50.3), (0.7, 42)], 50), 0.85)
        self.assertEqual(pick_legend_scale([(1.0, 40), (0.85, 34), (0.7, 28)], 50), 1.0)

    def test_nothing_fits_returns_none_so_entries_are_dropped(self):
        self.assertIsNone(pick_legend_scale([(1.0, 120), (0.85, 100), (0.7, 80)], 49.5))

    def test_a_tenth_of_a_millimetre_over_is_still_a_fit(self):
        self.assertEqual(pick_legend_scale([(1.0, 49.9)], 49.5), 1.0)

    def test_scales_shrink_in_order_and_never_below_seventy_percent(self):
        self.assertEqual(list(LEGEND_SCALES), sorted(LEGEND_SCALES, reverse=True))
        self.assertGreaterEqual(min(LEGEND_SCALES), 0.7)

    def test_the_title_names_how_many_layers_were_left_out(self):
        self.assertEqual(legend_title_with_note("Legend", 0), "Legend")
        self.assertEqual(legend_title_with_note("Legend", 1), "Legend (1 more layer not shown)")
        self.assertEqual(legend_title_with_note("Legend", 4), "Legend (4 more layers not shown)")


class TestFooterSlack(unittest.TestCase):
    def test_a_shortfall_within_the_padding_counts_as_fitting(self):
        # box 17.1 mm at y 192.4 on a 210 mm page: 0.5 mm below, no room above; the text needs 17.5 mm (0.4 mm more than the box)
        self.assertTrue(plan_footer_growth(17.5, 17.1, 192.4, 210, 0.0, slack_mm=FOOTER_FIT_SLACK_MM)[2])

    def test_the_same_shortfall_is_a_misfit_without_slack_and_a_real_one_still_is(self):
        self.assertFalse(plan_footer_growth(17.5, 17.1, 192.4, 210, 0.0)[2])
        self.assertFalse(plan_footer_growth(19.5, 17.1, 192.4, 210, 0.0, slack_mm=FOOTER_FIT_SLACK_MM)[2])

    def test_the_slack_is_the_padding_and_not_a_free_line(self):
        self.assertEqual(FOOTER_FIT_SLACK_MM, FOOTER_PAD_MM)
        self.assertLess(FOOTER_FIT_SLACK_MM, 1.0)


class TestLayoutName(unittest.TestCase):
    def test_the_requested_name_is_kept(self):
        self.assertEqual(layout_name_for("Big Map"), "Big Map")
        self.assertEqual(layout_name_for("  Big   Map "), "Big Map")

    def test_an_empty_title_still_gets_a_name(self):
        self.assertEqual(layout_name_for(""), "Layout")
        self.assertEqual(layout_name_for(None), "Layout")

    def test_either_spelling_finds_the_layout(self):
        layouts = [_Named("Big Map"), _Named("Other")]
        self.assertIs(resolve_layout(layouts, "Layout_Big_Map"), layouts[0])
        self.assertIs(resolve_layout(layouts, "Big Map"), layouts[0])
        old = [_Named("Layout_Test_Layout")]
        self.assertIs(resolve_layout(old, "Test Layout"), old[0])


if __name__ == "__main__":
    unittest.main()
