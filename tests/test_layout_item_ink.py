"""PLAN-021 #379, no QGIS needed: the verdict a chart or profile tool gives about what its item drew."""
import unittest

from cartogen_ai.core.agent.tools.layout_chart_profile_tools import MIN_COLOUR_SPREAD, MIN_INK_PIXELS, ink_verdict, is_data_ink


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


class TestIsDataInk(unittest.TestCase):
    """DEF-38: the colours are the ones measured in the pictures of CI run 42558613090 (main at 59e3b76)."""

    def test_the_muted_green_profile_curve_that_a_fixed_threshold_of_40_missed_is_ink(self):
        self.assertTrue(is_data_ink(121, 146, 108))      # spread 38, saturation 66
        self.assertTrue(is_data_ink(172, 196, 157))      # the pale line chart: spread 39, saturation 51 (the old tool check said empty)

    def test_a_vivid_curve_is_ink(self):
        self.assertTrue(is_data_ink(170, 5, 145))

    def test_white_black_and_neutral_greys_are_not_ink(self):
        for rgb in ((255, 255, 255), (0, 0, 0), (128, 128, 128), (200, 200, 205), (90, 92, 95), (230, 230, 230)):
            self.assertFalse(is_data_ink(*rgb), rgb)

    def test_the_boundary_is_the_documented_spread(self):
        self.assertFalse(is_data_ink(100, 100, 100 + MIN_COLOUR_SPREAD - 1))
        self.assertTrue(is_data_ink(100, 100, 100 + MIN_COLOUR_SPREAD))

    def test_it_does_not_depend_on_which_channel_is_largest(self):
        self.assertEqual(is_data_ink(150, 120, 100), is_data_ink(100, 150, 120))
        self.assertEqual(is_data_ink(150, 120, 100), is_data_ink(120, 100, 150))


if __name__ == "__main__":
    unittest.main()
