"""PLAN-021 #379, no QGIS needed: the verdict a chart or profile tool gives about what its item drew."""
import unittest

from cartogen_ai.core.agent.tools.layout_chart_profile_tools import MIN_INK_PIXELS, ink_verdict


class TestInkVerdict(unittest.TestCase):
    def test_enough_coloured_pixels_is_a_drawn_item_with_no_warning(self):
        verdict = ink_verdict(2160)
        self.assertTrue(verdict["drew"])
        self.assertNotIn("warning", verdict)

    def test_a_thin_line_chart_of_a_few_hundred_pixels_still_counts(self):
        self.assertTrue(ink_verdict(240)["drew"])        # the line chart of the 1.18.0 CI run: 0.001 of 240,000 px

    def test_axes_only_is_reported_as_empty_with_what_to_check(self):
        verdict = ink_verdict(0)
        self.assertFalse(verdict["drew"])
        self.assertIn("drew no data", verdict["warning"])
        self.assertIn("elevation", verdict["warning"])

    def test_the_boundary_is_the_documented_minimum(self):
        self.assertFalse(ink_verdict(MIN_INK_PIXELS - 1)["drew"])
        self.assertTrue(ink_verdict(MIN_INK_PIXELS)["drew"])


if __name__ == "__main__":
    unittest.main()
