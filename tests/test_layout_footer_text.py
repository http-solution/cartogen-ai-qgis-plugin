"""PLAN-011 phase C, no QGIS needed: the sources line, the disclaimer choice and the footer growth rule."""
import unittest

from cartogen_ai.core.agent.tools.layout_style import (
    footer_height_mm,
    DEFAULT_DISCLAIMER, NOT_RECORDED, disclaimer_text, footer_block, plan_footer_growth, source_entry, sources_line,
)


class TestDisclaimer(unittest.TestCase):
    def test_default_is_the_neutral_sentence(self):
        self.assertEqual(disclaimer_text(True, ""), DEFAULT_DISCLAIMER)
        self.assertEqual(disclaimer_text(True, "   "), DEFAULT_DISCLAIMER)

    def test_the_organisations_wording_wins(self):
        self.assertEqual(disclaimer_text(True, " Our wording. "), "Our wording.")

    def test_switched_off_is_empty_even_with_wording(self):
        self.assertEqual(disclaimer_text(False, "Our wording."), "")


class TestSources(unittest.TestCase):
    def test_nothing_recorded_says_so_instead_of_guessing(self):
        self.assertEqual(source_entry("roads"), f"roads ({NOT_RECORDED})")

    def test_metadata_wins_over_the_file_name(self):
        self.assertEqual(source_entry("roads", "OCHA", "2024-05-01", "roads.gpkg"), "roads (OCHA; 2024-05-01)")

    def test_file_name_is_used_when_metadata_is_empty(self):
        self.assertEqual(source_entry("roads", "", "", "roads.gpkg"), "roads (file roads.gpkg)")

    def test_a_short_list_is_joined_whole(self):
        self.assertEqual(sources_line(["a (x)", "b (y)"]), "Sources: a (x); b (y)")

    def test_no_layers_gives_no_line(self):
        self.assertEqual(sources_line([]), "")

    def test_a_long_list_is_cut_and_counts_what_it_left_out(self):
        entries = [f"layer_number_{i} (publisher {i}; 2024-01-0{i % 9 + 1})" for i in range(12)]
        line = sources_line(entries, budget=150)
        self.assertLessEqual(len(line), 150)
        self.assertRegex(line, r"\+\d+ more$")
        left = int(line.rsplit("+", 1)[1].split()[0])
        self.assertEqual(line.count("layer_number_") + left, 12)

    def test_one_huge_entry_is_shortened_not_dropped(self):
        line = sources_line(["x" * 400, "y"], budget=100)
        self.assertTrue(line.startswith("Sources: xxxx"))
        self.assertLessEqual(len(line), 100)


class TestFooterBlock(unittest.TestCase):
    def test_parts_in_order_and_empty_parts_left_out(self):
        self.assertEqual(footer_block("AI note", ["SENSITIVE"], "Sources: a (x)", "Disclaimer."),
                         "CLASSIFICATION: SENSITIVE -- AI note\nSources: a (x)\nDisclaimer.")
        self.assertEqual(footer_block("AI note", [], "", ""), "AI note")


class TestGrowth(unittest.TestCase):
    def test_fits_means_unchanged(self):
        self.assertEqual(plan_footer_growth(8, 8, 190, 210, 5), (190, 8, True))

    def test_grows_into_the_bottom_margin_first(self):
        # page 210, footer 190..198: 11 mm free below (minus 1 mm gap) = 11; needs 4 more -> all below, y unchanged
        self.assertEqual(plan_footer_growth(12, 8, 190, 210, 5), (190, 12, True))

    def test_then_upward_into_free_space(self):
        # footer 198..206 of 210: 3 mm below; needs 6 more -> 3 down, 3 up
        self.assertEqual(plan_footer_growth(14, 8, 198, 210, 10), (195, 14, True))

    def test_reports_when_it_cannot_fit(self):
        y, h, fits = plan_footer_growth(30, 8, 198, 210, 2)
        self.assertFalse(fits)
        self.assertEqual(h, 8 + 3 + 2)
        self.assertEqual(y, 196)


class TestFooterHeight(unittest.TestCase):
    def test_a_three_line_footer_fits_the_landscape_space_that_a_four_line_one_just_fits(self):
        # A4 landscape: the footer box is 8 mm, 3 mm of page margin below it and 0.5 mm of gap above it = 11.5 mm available
        three = "AI note\nSources: a (b)\nBoundaries, names and designations shown do not imply official endorsement or acceptance."
        self.assertLessEqual(footer_height_mm(three, 275, 7.0), 11.5)
        self.assertLessEqual(footer_height_mm(three + "\nCredits: Basemap: OpenStreetMap contributors (ODbL)", 275, 7.0), 14.0)

    def test_a_long_line_wraps_into_more_lines(self):
        self.assertGreater(footer_height_mm("x" * 600, 275, 7.0), footer_height_mm("x" * 60, 275, 7.0))

    def test_empty_text_still_gets_a_line(self):
        self.assertGreater(footer_height_mm("", 275, 7.0), 1.0)


if __name__ == "__main__":
    unittest.main()
