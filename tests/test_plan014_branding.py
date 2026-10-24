"""PLAN-014 phase 3a, offline: logo, masthead colour and font fields of a map profile, and the pure masthead helpers."""
import unittest

from cartogen_ai.core.agent.tools.layout_style import contrast_ratio, masthead_split, resolve_masthead_colours
from cartogen_ai.core.agent.tools.map_profiles import logo_path_problem, validate_profile


class TestBrandingFields(unittest.TestCase):
    def test_valid_branding_is_kept_and_normalised(self):
        clean, problems = validate_profile({"logo_path": "assets/mark.PNG", "logo_position": "Right", "masthead_colour": "#2B5D8A",
                                            "masthead_text_colour": "#FFFFFF", "font_family": "Noto Sans"})
        self.assertEqual(problems, [])
        self.assertEqual((clean["logo_position"], clean["masthead_colour"], clean["font_family"]), ("right", "#2b5d8a", "Noto Sans"))

    def test_logo_paths_that_could_reach_outside_are_refused(self):
        for bad in ("http://x/a.png", "https://x/a.png", "file:///etc/a.png", "\\\\srv\\share\\a.png", "//srv/a.png", "a/../b.png", "logo.svg", "logo.gif", ""):
            self.assertIsNotNone(logo_path_problem(bad), bad)
        self.assertIsNone(logo_path_problem("logo.jpg"))

    def test_bad_values_are_each_named(self):
        _, problems = validate_profile({"logo_position": "top", "masthead_colour": "blue", "masthead_text_colour": "#fff", "font_family": "<b>"})
        self.assertEqual(len(problems), 4)
        for name in ("logo_position", "masthead_colour", "masthead_text_colour", "font_family"):
            self.assertTrue(any(name in p for p in problems), name)


class TestMastheadHelpers(unittest.TestCase):
    def test_contrast_ratio_extremes(self):
        self.assertAlmostEqual(contrast_ratio("#000000", "#ffffff"), 21.0, places=1)
        self.assertAlmostEqual(contrast_ratio("#777777", "#777777"), 1.0, places=2)

    def test_a_readable_text_colour_is_used(self):
        bg, fg, warning = resolve_masthead_colours("#2b5d8a", "#ffffff")
        self.assertEqual((bg, fg, warning), ("#2b5d8a", "#ffffff", None))

    def test_an_unreadable_text_colour_is_replaced_and_reported(self):
        _, fg, warning = resolve_masthead_colours("#2b5d8a", "#2f6a9a")
        self.assertEqual(fg, "#ffffff")
        self.assertIn("hard to read", warning)

    def test_no_text_colour_keeps_the_automatic_choice(self):
        self.assertEqual(resolve_masthead_colours("#ffffff")[1], "#1f2d3a")

    def test_logo_and_title_boxes_never_overlap_and_stay_inside(self):
        for position in ("left", "right"):
            (lx, ly, lw, lh), (tx, _, tw, _) = masthead_split(10, 10, 277, 14, position)
            self.assertTrue(lx + lw <= tx or tx + tw <= lx, position)
            for x, w in ((lx, lw), (tx, tw)):
                self.assertTrue(x >= 10 and x + w <= 287, position)
            self.assertTrue(ly >= 10 and ly + lh <= 24)


if __name__ == "__main__":
    unittest.main()
