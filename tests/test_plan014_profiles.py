"""PLAN-014 phase 2b, no QGIS needed: profile validation, lookup, the file name pattern, and the shipped example."""
import datetime
import json
import os
import tempfile
import unittest

from cartogen_ai.core.agent.tools.layout_export_checks import ELEMENT_LABELS, missing_elements
from cartogen_ai.core.agent.tools.layout_options import export_file_name, resolve_export_target
from cartogen_ai.core.agent.tools.map_profiles import (
    available_profiles, example_profile, load_profile, parse_profile_text, safe_profile_name, validate_profile,
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestValidate(unittest.TestCase):
    def test_the_example_is_valid_and_the_shipped_file_matches_it(self):
        clean, problems = validate_profile(example_profile())
        self.assertEqual(problems, [])
        self.assertEqual(clean["page_size"], "A3")
        with open(os.path.join(ROOT, "docs", "examples", "map_profile_example.json"), encoding="utf-8") as handle:
            self.assertEqual(json.load(handle), example_profile())

    def test_the_example_carries_no_organisations_name_or_mark(self):
        text = json.dumps(example_profile()).lower()
        for word in ("ocha", "united nations", "unocha", "logo"):
            self.assertNotIn(word, text)

    def test_an_empty_profile_is_valid_and_changes_nothing(self):
        self.assertEqual(validate_profile({}), ({"profile_version": 1}, []))

    def test_unknown_fields_are_refused_by_name(self):
        _, problems = validate_profile({"logo": "x.png", "colours": ["#fff"]})
        self.assertEqual(len(problems), 2)
        self.assertTrue(any("'logo'" in p for p in problems) and any("'colours'" in p for p in problems))

    def test_every_bad_value_is_reported_together(self):
        _, problems = validate_profile({"page_size": "A5", "orientation": "sideways", "export_preset": "poster",
                                        "file_name_pattern": "{title}_{author}", "required_elements": ["LOGO"], "profile_version": 2})
        self.assertEqual(len(problems), 6, problems)

    def test_values_are_normalised(self):
        clean, _ = validate_profile({"page_size": " a2 ", "orientation": "PORTRAIT", "export_preset": "Web", "required_elements": ["TITLE", "TITLE", "LEGEND"]})
        self.assertEqual((clean["page_size"], clean["orientation"], clean["export_preset"], clean["required_elements"]),
                         ("A2", "Portrait", "web", ["TITLE", "LEGEND"]))

    def test_pattern_rules(self):
        for good in ("{title}", "{date}_{layout}", "weekly_{title}_{date}"):
            self.assertEqual(validate_profile({"file_name_pattern": good})[1], [], good)
        for bad in ("", "   ", "{title", "title}", "{nope}", "x" * 101, 5):
            self.assertNotEqual(validate_profile({"file_name_pattern": bad})[1], [], repr(bad))

    def test_not_json_and_not_an_object(self):
        self.assertIn("not valid JSON", parse_profile_text("{nope")[1][0])
        self.assertIn("JSON object", parse_profile_text("[1, 2]")[1][0])
        self.assertIn("larger than", parse_profile_text(" " * 30000)[1][0])


class TestLookup(unittest.TestCase):
    def test_names_with_paths_are_refused(self):
        for bad in ("../secret", "a/b", "a\\b", "", ".hidden", "x" * 80):
            self.assertIsNone(safe_profile_name(bad), bad)
        self.assertEqual(safe_profile_name("weekly sitrep-2"), "weekly sitrep-2")

    def test_the_first_folder_wins_and_a_missing_name_lists_what_exists(self):
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            for folder, size in ((first, "A3"), (second, "A1")):
                with open(os.path.join(folder, "weekly.json"), "w", encoding="utf-8") as handle:
                    json.dump({"page_size": size}, handle)
            with open(os.path.join(second, "other.json"), "w", encoding="utf-8") as handle:
                json.dump({}, handle)
            self.assertEqual(load_profile("weekly", [first, second])[0]["page_size"], "A3")
            profile, message = load_profile("missing", [first, second])
            self.assertIsNone(profile)
            self.assertIn("Available: other, weekly", message)
            self.assertEqual(available_profiles([first, second]), ["other", "weekly"])

    def test_an_invalid_file_says_which_file_and_why(self):
        with tempfile.TemporaryDirectory() as folder:
            with open(os.path.join(folder, "bad.json"), "w", encoding="utf-8") as handle:
                json.dump({"page_size": "A5", "logo": "x"}, handle)
            profile, message = load_profile("bad", [folder])
            self.assertIsNone(profile)
            self.assertIn("bad.json", message)
            self.assertIn("page_size must be one of", message)
            self.assertIn("'logo'", message)

    def test_no_folders_and_no_profile_is_a_clear_message(self):
        self.assertIn("No profile named 'x'", load_profile("x", [])[1])


class TestPatternAndRequirements(unittest.TestCase):
    def test_pattern_placeholders_are_filled_and_made_safe(self):
        day = datetime.date(2026, 10, 24)
        self.assertEqual(export_file_name("Flood: Marib", "pdf", day, "weekly_{title}_{date}"), "weekly_Flood_ Marib_2026-10-24.pdf")
        self.assertEqual(export_file_name("T", "png", day, "{layout}-{date}", layout="Layout A/B"), "Layout A_B-2026-10-24.png")
        self.assertEqual(export_file_name("T", "pdf", day), "T_2026-10-24.pdf")

    def test_a_folder_uses_the_pattern_and_a_file_does_not(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(resolve_export_target(folder, "Map", "pdf", datetime.date(2026, 1, 2), "{date}_{title}"),
                             os.path.join(folder, "2026-01-02_Map.pdf"))
            fixed = os.path.join(folder, "mine.pdf")
            self.assertEqual(resolve_export_target(fixed, "Map", "pdf", pattern="{title}"), fixed)

    def test_required_elements_come_from_the_profile_else_the_five_defaults(self):
        self.assertEqual(missing_elements(["TITLE"], ["TITLE", "BODY_TEXT", "FOOTER"]), [ELEMENT_LABELS["BODY_TEXT"], ELEMENT_LABELS["FOOTER"]])
        self.assertEqual(len(missing_elements([])), 5)
        self.assertEqual(missing_elements(["MAP_MAIN", "TITLE", "LEGEND", "SCALEBAR", "NORTH_ARROW"]), [])


if __name__ == "__main__":
    unittest.main()
