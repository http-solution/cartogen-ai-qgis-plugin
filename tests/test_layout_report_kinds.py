"""PLAN-023 R3-6: the text of the field_report and change_report layouts, and the pure class planning of apply_land_cover_look. Offline, no QGIS: the real layouts and renderers are read back in tests/test_layout_report_kinds_live.py and
tests/test_land_cover_look_live.py (CI's QGIS job)."""
import datetime
import unittest

from cartogen_ai.core.agent.tools import land_cover_look_tool as lc
from cartogen_ai.core.agent.tools import layout_style as ls

FIGURES = [{"label": "Mean NDVI", "value": "0.54", "source": "Sentinel-2, 2025-06-12"}]
TODAY = datetime.date(2026, 11, 11)


class TestReportKinds(unittest.TestCase):
    def test_the_four_templates_are_the_report_templates(self):
        self.assertEqual(ls.REPORT_TEMPLATES, ("sitrep", "field_report", "change_report", "epi_bulletin"))

    def test_sitrep_keeps_its_words_exactly(self):
        text = ls.sitrep_body("Floods in the south", FIGURES, ["OCHA"], "Guide", today=TODAY)
        self.assertEqual(text.split("\n\n")[0], "SITUATION\nFloods in the south")
        self.assertIn("KEY FIGURES\n- Mean NDVI: 0.54 (Sentinel-2, 2025-06-12)", text)
        self.assertIn("HOW TO READ THIS MAP\nGuide", text)
        self.assertIn("HANDLING\n" + ls.SITREP_HANDLING, text)
        self.assertEqual(text, ls.sitrep_body("Floods in the south", FIGURES, ["OCHA"], "Guide", today=TODAY, kind="sitrep"))

    def test_a_field_report_has_its_own_headings_guide_and_note(self):
        text = ls.sitrep_body("North field, wheat", FIGURES, ["Earth Search"], ls.FIELD_REPORT_GUIDE, today=TODAY, kind="field_report")
        self.assertTrue(text.startswith("FIELD\nNorth field, wheat"))
        for heading in ("INDEX READINGS\n- Mean NDVI: 0.54", "HOW TO READ THIS MAP\n" + ls.FIELD_REPORT_GUIDE, "SOURCES\nEarth Search", "NOTE\n" + ls.FIELD_REPORT_NOTE):
            self.assertIn(heading, text)
        for absent in ("SITUATION", "KEY FIGURES", "HANDLING"):
            self.assertNotIn(absent, text)
        self.assertTrue(text.endswith("Prepared 2026-11-11."))

    def test_a_change_report_has_its_own_headings_and_note(self):
        text = ls.sitrep_body("2019 to 2024", [{"label": "Net change", "value": "-12 ha"}], ["WorldCover 2020 and 2021"], ls.CHANGE_REPORT_GUIDE, today=TODAY, kind="change_report")
        self.assertTrue(text.startswith("CHANGE\n2019 to 2024"))
        self.assertIn("CHANGE FIGURES\n- Net change: -12 ha", text)
        self.assertIn("NOTE\n" + ls.CHANGE_REPORT_NOTE, text)
        self.assertNotIn("HANDLING", text)

    def test_an_epi_bulletin_has_its_own_headings_and_a_method_and_limits_box(self):
        text = ls.sitrep_body("Cases reported to 2026-11-08", [{"label": "Cases", "value": "412"}], ["District health office"], ls.EPI_BULLETIN_GUIDE, today=TODAY, kind="epi_bulletin")
        self.assertTrue(text.startswith("SUMMARY\nCases reported to 2026-11-08"))
        for heading in ("CASES AND RATES\n- Cases: 412", "HOW TO READ THIS MAP\n" + ls.EPI_BULLETIN_GUIDE, "SOURCES\nDistrict health office", "METHOD AND LIMITS\n" + ls.EPI_BULLETIN_NOTE):
            self.assertIn(heading, text)
        for absent in ("SITUATION", "KEY FIGURES", "HANDLING", "\nNOTE\n"):
            self.assertNotIn(absent, text)
        self.assertTrue(text.endswith("Prepared 2026-11-11."))

    def test_the_bulletin_note_names_every_limit_the_plan_requires(self):
        note = ls.EPI_BULLETIN_NOTE
        for phrase in ("crude", "not individuals", "fewer than 5 cases", "not a finding about cause", "reported by the date stated"):
            self.assertIn(phrase, note)

    def test_the_bulletin_guide_matches_the_look_it_describes(self):
        for phrase in ("blue", "hatched", "black and white", "legend"):
            self.assertIn(phrase, ls.EPI_BULLETIN_GUIDE)

    def test_the_notes_say_what_the_report_is_not(self):
        self.assertIn("not a yield forecast", ls.FIELD_REPORT_NOTE)
        self.assertIn("agronomic recommendation", ls.FIELD_REPORT_NOTE)
        self.assertIn("not a survey", ls.CHANGE_REPORT_NOTE)

    def test_the_guides_name_every_class_colour(self):
        for colour in ("Orange", "grey", "purple"):
            self.assertIn(colour, ls.CHANGE_REPORT_GUIDE)
        self.assertIn("legend", ls.FIELD_REPORT_GUIDE)

    def test_an_unknown_kind_reads_as_sitrep(self):
        self.assertEqual(ls.sitrep_body("x", None, None, "", today=TODAY, kind="nonsense"), ls.sitrep_body("x", None, None, "", today=TODAY))

    def test_a_long_summary_is_shortened_but_the_note_and_the_sources_survive_in_every_kind(self):
        for kind, note in (("field_report", ls.FIELD_REPORT_NOTE), ("change_report", ls.CHANGE_REPORT_NOTE), ("epi_bulletin", ls.EPI_BULLETIN_NOTE), ("sitrep", ls.SITREP_HANDLING)):
            text = ls.sitrep_body("A very long summary. " * 80, FIGURES * 4, ["Source one", "Source two"], "Guide " * 20, today=TODAY, max_chars=900, kind=kind)
            self.assertLessEqual(len(text), 900, kind)
            self.assertIn(note, text, kind)
            self.assertIn("SOURCES\nSource one; Source two", text, kind)

    def test_unverified_figures_are_marked_in_a_field_report_too(self):
        text = ls.sitrep_body("", [{"label": "Mean NDVI", "value": "0.54"}], None, "", today=TODAY, unverified_labels=["Mean NDVI"], kind="field_report")
        self.assertIn("- Mean NDVI: 0.54 " + ls.UNVERIFIED_FIGURE_MARK, text)


class TestPlanClasses(unittest.TestCase):
    def test_codes_names_and_text_codes_all_match_and_come_out_in_class_order(self):
        classes, unmatched = lc.plan_classes([40, "10", "Mangroves", 10, 20], "esa_worldcover")
        self.assertEqual([c["label"] for c in classes], ["Tree cover (10)", "Tree cover (10)", "Shrubland (20)", "Cropland (40)", "Mangroves (95)"])
        self.assertEqual(unmatched, [])
        self.assertTrue(all(c["matched"] for c in classes))

    def test_every_class_label_carries_name_and_code(self):
        classes, _ = lc.plan_classes([c["code"] for c in lc.style_looks.worldcover_entries()], "esa_worldcover")
        self.assertEqual(len(classes), 11)
        for c in classes:
            self.assertRegex(c["label"], r"^[A-Za-z /-]+ \(\d+\)$")

    def test_what_is_not_a_class_is_grey_named_and_listed_never_recoloured(self):
        classes, unmatched = lc.plan_classes([10, 11, "forest", None], "esa_worldcover")
        self.assertEqual(unmatched, ["11", "None", "forest"])
        grey = [c for c in classes if not c["matched"]]
        self.assertEqual({c["colour"] for c in grey}, {lc.UNMATCHED_COLOUR})
        self.assertEqual([c["label"] for c in grey], ["11 (not in the ESA WorldCover legend)", "no value (not in the ESA WorldCover legend)", "forest (not in the ESA WorldCover legend)"])
        self.assertEqual(classes[0]["label"], "Tree cover (10)")

    def test_a_whole_number_that_arrives_as_a_float_is_shown_without_the_point_zero(self):
        # QGIS returns raster cell values as floats: the CI live run showed '11.0 (not in ...)' before this was fixed
        classes, unmatched = lc.plan_classes([10.0, 11.0, 12.5], "esa_worldcover")
        self.assertEqual(unmatched, ["11", "12.5"])
        self.assertEqual([c["label"] for c in classes], ["Tree cover (10)", "11 (not in the ESA WorldCover legend)", "12.5 (not in the ESA WorldCover legend)"])
        self.assertEqual(classes[0]["value"], 10.0)

    def test_change_classes_in_order_loss_stable_gain(self):
        classes, unmatched = lc.plan_classes([1, "loss", 0, -1, 2], "change_classes")
        self.assertEqual([c["label"] for c in classes if c["matched"]], ["loss (-1)", "loss (-1)", "stable (0)", "gain (1)"])
        self.assertEqual(unmatched, ["2"])
        self.assertEqual(classes[0]["colour"], "#E66101")

    def test_the_tool_refuses_cleanly_without_qgis(self):
        self.assertEqual(lc.apply_land_cover_look("x", "esa_worldcover"), {"error": "QGIS not available"})

    def test_the_tool_is_registered_with_its_three_schemes(self):
        from cartogen_ai.core.agent.tools import TOOL_REGISTRY, TOOLS_SCHEMA
        self.assertIn("apply_land_cover_look", TOOL_REGISTRY)
        schema = next(t for t in TOOLS_SCHEMA if t["function"]["name"] == "apply_land_cover_look")
        self.assertEqual(schema["function"]["parameters"]["properties"]["scheme"]["enum"], ["esa_worldcover", "change_classes", "protected_area_hatch"])
        self.assertEqual(schema["function"]["parameters"]["required"], ["layer_name", "scheme"])


if __name__ == "__main__":
    unittest.main()
