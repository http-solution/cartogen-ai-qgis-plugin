"""PLAN-014 phase 1, no QGIS needed: the credit line, the layout geometry rules, export presets and file names."""
import datetime
import os
import tempfile
import unittest

from cartogen_ai.core.agent.tools.layout_credits import NOT_RECORDED, basemap_credit, credit_entries, credits_line
from cartogen_ai.core.agent.tools.layout_geometry_checks import all_problems, off_page_problems, overflow_problems, overlap_problems, rects_overlap
from cartogen_ai.core.agent.tools.layout_options import EXPORT_PRESETS, export_dpi, export_file_name, resolve_export_target
from cartogen_ai.core.agent.tools.layout_style import footer_block

OSM = "type=xyz&url=https://tile.openstreetmap.org/%7Bz%7D/%7Bx%7D/%7By%7D.png&zmax=19&zmin=0"


class TestBasemapCredit(unittest.TestCase):
    def test_known_basemaps_use_the_vetted_attribution(self):
        self.assertEqual(basemap_credit(OSM), ("OpenStreetMap contributors (ODbL)", True))
        self.assertEqual(basemap_credit("type=xyz&url=https://basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png")[0], "CARTO, data OpenStreetMap contributors")

    def test_two_esri_basemaps_are_told_apart(self):
        imagery = basemap_credit("type=xyz&url=https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}")
        streets = basemap_credit("type=xyz&url=https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}")
        self.assertEqual((imagery[0], streets[0]), ("Esri World Imagery", "Esri World Street Map"))

    def test_an_unknown_web_layer_is_not_given_a_guessed_credit(self):
        credit, known = basemap_credit("type=xyz&url=https://example.org/tiles/{z}/{x}/{y}.png")
        self.assertEqual((credit, known), ("example.org", False))


class TestCreditEntries(unittest.TestCase):
    def _layer(self, **kw):
        return {"name": "x", "provider": "ogr", "source": "", "rights": [], "visible": True, **kw}

    def test_a_visible_known_basemap_gets_its_credit_once(self):
        layers = [self._layer(name="osm", provider="wms", source=OSM), self._layer(name="osm copy", provider="wms", source=OSM)]
        self.assertEqual(credit_entries(layers), ["Basemap: OpenStreetMap contributors (ODbL)"])

    def test_an_unknown_web_layer_says_credit_not_recorded(self):
        entries = credit_entries([self._layer(name="tiles", provider="wms", source="type=xyz&url=https://example.org/t/{z}/{x}/{y}.png")])
        self.assertEqual(entries, [f"Basemap tiles: {NOT_RECORDED} (example.org)"])

    def test_hidden_layers_and_plain_data_layers_add_nothing(self):
        self.assertEqual(credit_entries([self._layer(provider="wms", source=OSM, visible=False), self._layer()]), [])

    def test_a_layers_own_rights_text_is_used(self):
        self.assertEqual(credit_entries([self._layer(name="roads", rights=["CC BY 4.0 OCHA"])]), ["roads: CC BY 4.0 OCHA"])


class TestCreditsLine(unittest.TestCase):
    def test_none_gives_no_line(self):
        self.assertEqual(credits_line([]), "")

    def test_long_lists_are_counted_not_dropped(self):
        line = credits_line([f"Basemap {i}: credit text number {i}" for i in range(12)], budget=120)
        self.assertLessEqual(len(line), 120)
        self.assertRegex(line, r"\+\d+ more$")

    def test_the_footer_order_is_note_sources_credits_disclaimer(self):
        self.assertEqual(footer_block("AI", [], "Sources: a (x)", "Disclaimer.", "Credits: c"), "AI\nSources: a (x)\nCredits: c\nDisclaimer.")


class TestGeometryRules(unittest.TestCase):
    def test_touching_edges_are_not_an_overlap(self):
        self.assertFalse(rects_overlap((0, 0, 10, 10), (10, 0, 10, 10)))
        self.assertTrue(rects_overlap((0, 0, 10, 10), (9, 9, 10, 10)))

    def test_the_locator_map_inside_the_main_map_is_allowed_but_other_overlaps_are_not(self):
        items = {"MAP_MAIN": (10, 10, 100, 100), "INSET_MAP": (12, 12, 20, 20), "LEGEND": (90, 90, 40, 40)}
        self.assertEqual(overlap_problems(items), ["LEGEND overlaps MAP_MAIN"])        # the inset inside the map is allowed

    def test_off_page_items_are_named_with_the_edge(self):
        problems = off_page_problems({"A": (-5, 0, 10, 10), "B": (280, 200, 30, 20), "C": (10, 10, 10, 10)}, (297, 210))
        self.assertTrue(any("A extends 5 mm past the left" in p for p in problems))
        self.assertTrue(any("B extends 13 mm past the right" in p for p in problems))
        self.assertTrue(any("B extends 10 mm past the bottom" in p for p in problems))
        self.assertFalse(any(p.startswith("C ") for p in problems))

    def test_only_clear_text_overflow_is_reported(self):
        self.assertEqual(overflow_problems({"FOOTER": (14.0, 8.0), "TITLE": (10.2, 10.0)}), ["FOOTER text needs about 14 mm but its box is 8 mm tall"])

    def test_a_clean_layout_has_no_problems(self):
        self.assertEqual(all_problems({"MAP_MAIN": (10, 10, 100, 100), "TITLE": (10, 0, 100, 9)}, (297, 210), {"TITLE": (6.0, 9.0)}), [])


class TestPresetsAndNames(unittest.TestCase):
    def test_presets_map_to_dpi_and_an_explicit_dpi_wins(self):
        self.assertEqual({k: export_dpi(k, None, 150)[0] for k in EXPORT_PRESETS}, {"draft": 96, "web": 150, "print": 300})
        self.assertEqual(export_dpi("print", 200, 150), (200, None))
        self.assertEqual(export_dpi(None, None, 300), (300, None))

    def test_an_unknown_preset_is_refused_with_the_choices(self):
        dpi, message = export_dpi("poster", None, 150)
        self.assertIsNone(dpi)
        self.assertIn("draft (96 dpi)", message)

    def test_file_name_is_safe_and_dated(self):
        self.assertEqual(export_file_name("Access to care: Marib/Taiz", "pdf", datetime.date(2026, 10, 24)), "Access to care_ Marib_Taiz_2026-10-24.pdf")
        self.assertEqual(export_file_name("", ".PNG", datetime.date(2026, 10, 24)), "map_2026-10-24.png")

    def test_a_folder_gets_the_default_name_and_a_file_path_is_left_alone(self):
        with tempfile.TemporaryDirectory() as folder:
            target = resolve_export_target(folder, "Flood map", "pdf", datetime.date(2026, 10, 24))
            self.assertEqual(target, os.path.join(folder, "Flood map_2026-10-24.pdf"))
            self.assertEqual(resolve_export_target(os.path.join(folder, "mine.pdf"), "Flood map"), os.path.join(folder, "mine.pdf"))
        self.assertTrue(resolve_export_target("exports/", "T", "png", datetime.date(2026, 1, 2)).endswith("T_2026-01-02.png"))


if __name__ == "__main__":
    unittest.main()
