# -*- coding: utf-8 -*-
"""Pure halves of output_style.py and layout_style.py (the QGIS halves are in tests/test_output_style_live.py)."""
import datetime
import unittest
import unittest.mock

from cartogen_ai.core.agent.tools import layout_style as ls
from cartogen_ai.core.agent.tools import output_style as os_


class TestRampStops(unittest.TestCase):
    def test_population_starts_transparent_at_zero_and_ends_opaque_at_the_maximum(self):
        stops = os_.ramp_stops("population", 800)
        self.assertEqual(stops[0][0], 0.0)
        self.assertEqual(stops[0][1][3], 0)
        self.assertEqual(stops[-1][0], 800.0)
        self.assertEqual(stops[-1][1][3], 255)

    def test_values_are_strictly_ascending(self):
        for kind in os_.RASTER_RAMPS:
            values = [v for v, _, _ in os_.ramp_stops(kind, 1000, 10)]
            self.assertEqual(values, sorted(set(values)), kind)

    def test_a_surface_ramp_spans_the_given_minimum_and_maximum(self):
        stops = os_.ramp_stops("surface", 50, -10)
        self.assertEqual(stops[0][0], -10.0)
        self.assertEqual(stops[-1][0], 50.0)

    def test_density_and_population_ignore_a_negative_minimum(self):
        self.assertEqual(os_.ramp_stops("population", 10, -5)[0][0], 0.0)

    def test_a_flat_raster_still_gets_a_range(self):
        stops = os_.ramp_stops("surface", 5, 5)
        self.assertGreater(stops[-1][0], stops[0][0])

    def test_garbage_range_does_not_crash(self):
        self.assertTrue(os_.ramp_stops("population", None))
        self.assertTrue(os_.ramp_stops("nonsense", 10))

    def test_the_low_end_is_dense_for_heavy_tailed_data(self):
        stops = os_.ramp_stops("population", 1000)
        self.assertLess(stops[1][0], 10)          # the second stop is within the first 1% of the range

    def test_labels_are_readable_numbers(self):
        self.assertEqual(os_._label(1234.4), "1,234")
        self.assertEqual(os_._label(2.25), "2.2")


class TestAlgorithmMapping(unittest.TestCase):
    def test_short_names_and_roles(self):
        self.assertEqual(os_.algorithm_short_name("native:buffer"), "buffer")
        self.assertEqual(os_.vector_role_for("native:buffer"), "proximity_buffer")
        self.assertEqual(os_.vector_role_for("native:intersection"), "selection_overlay")
        self.assertEqual(os_.vector_role_for("native:shortestpathpointtopoint"), "route_line")
        self.assertIsNone(os_.vector_role_for("native:centroids"))

    def test_raster_kinds(self):
        self.assertEqual(os_.raster_kind_for("native:slope"), "surface")
        self.assertEqual(os_.raster_kind_for("qgis:heatmapkerneldensityestimation"), "density")
        self.assertIsNone(os_.raster_kind_for("native:hillshade"))   # hillshade keeps its grey ramp

    def test_every_mapped_role_exists_in_the_style_profiles(self):
        from cartogen_ai.core.agent.map_intelligence import STYLE_PROFILES
        for role in set(os_.ALGORITHM_VECTOR_ROLES.values()):
            self.assertIn(role, STYLE_PROFILES)

    def test_no_qgis_means_no_styling(self):
        if os_.QGIS_AVAILABLE:
            self.skipTest("QGIS present")
        self.assertFalse(os_.style_continuous_raster(object()))
        self.assertIsNone(os_.style_algorithm_output(object(), "native:buffer"))


class TestAllowlistExtensions(unittest.TestCase):
    def test_extensions_are_allowed_and_expression_algorithms_are_not(self):
        from cartogen_ai.core.agent.tools._processing_allowlist import ALLOWED_ALGORITHM_IDS, ANALYSIS_EXTENSIONS
        self.assertTrue(ANALYSIS_EXTENSIONS <= ALLOWED_ALGORITHM_IDS)
        for risky in ("native:extractbyexpression", "native:aggregate", "native:refactorfields", "native:fieldcalculator"):
            self.assertNotIn(risky, ALLOWED_ALGORITHM_IDS)

    def test_raster_output_algorithms_are_a_subset_of_the_allowlist(self):
        from cartogen_ai.core.agent.tools._processing_allowlist import ALLOWED_ALGORITHM_IDS, RASTER_OUTPUT_ALGORITHM_IDS
        self.assertTrue(RASTER_OUTPUT_ALGORITHM_IDS <= ALLOWED_ALGORITHM_IDS)

    def test_raster_algorithms_get_a_temporary_file_not_memory(self):
        from cartogen_ai.core.agent.tools import processing_allowlist_tools as pt
        with unittest.mock.patch.object(pt, "_find_layer_by_name", return_value=None):
            raster = pt._resolve_params({"INPUT": "dem"}, raster_output=True)
            vector = pt._resolve_params({"INPUT": "roads"}, raster_output=False)
        self.assertEqual(raster["OUTPUT"], "TEMPORARY_OUTPUT")
        self.assertEqual(vector["OUTPUT"], "memory:")

    def test_a_caller_supplied_output_is_still_overridden(self):
        from cartogen_ai.core.agent.tools import processing_allowlist_tools as pt
        with unittest.mock.patch.object(pt, "_find_layer_by_name", return_value=None):
            out = pt._resolve_params({"INPUT": "dem", "OUTPUT": "/etc/passwd"}, raster_output=True)
        self.assertEqual(out["OUTPUT"], "TEMPORARY_OUTPUT")


class TestLayoutLegendSelection(unittest.TestCase):
    ENTRIES = [
        {"id": "a", "name": "Clinics", "visible": True, "provider": "memory"},
        {"id": "b", "name": "Roads", "visible": False, "provider": "ogr"},
        {"id": "c", "name": "OSM Standard", "visible": True, "provider": "wms"},
        {"id": "d", "name": "Origin_service_area_lines_0", "visible": True, "provider": "memory"},
        {"id": "e", "name": "Origin_roads_by_cost_0", "visible": True, "provider": "memory"},
        {"id": "f", "name": "Population", "visible": True, "provider": "gdal"},
    ]

    def test_only_visible_thematic_layers_in_tree_order(self):
        self.assertEqual(ls.legend_layer_ids(self.ENTRIES), ["a", "e", "f"])

    def test_empty_input(self):
        self.assertEqual(ls.legend_layer_ids([]), [])


class TestClassificationAndStamps(unittest.TestCase):
    def test_the_most_restrictive_protected_level_wins(self):
        self.assertEqual(ls.highest_protected_level(["PUBLIC", "RESTRICTED", "SENSITIVE"]), "SENSITIVE")
        self.assertEqual(ls.highest_protected_level(["INTERNAL", "RESTRICTED"]), "RESTRICTED")

    def test_open_or_untagged_layers_add_no_prefix(self):
        self.assertIsNone(ls.highest_protected_level(["PUBLIC", "INTERNAL", None]))
        self.assertEqual(ls.classification_prefix([None, "PUBLIC"]), "")

    def test_footer_and_info_text(self):
        self.assertEqual(ls.footer_text("AI-generated.", ["SENSITIVE"]), "CLASSIFICATION: SENSITIVE -- AI-generated.")
        self.assertEqual(ls.footer_text("AI-generated.", []), "AI-generated.")
        self.assertEqual(ls.info_text("EPSG:4326   |   Scale 1:50,000", datetime.date(2026, 10, 1)),
                         "EPSG:4326   |   Scale 1:50,000   |   Prepared 2026-10-01")

    def test_the_type_scale_is_ordered(self):
        t = ls.TYPE_SCALE
        self.assertGreater(t["title"], t["legend_title"])
        self.assertGreater(t["legend_title"], t["panel"])
        self.assertGreater(t["panel"], t["footer"])

    def test_no_qgis_apply_reports_it(self):
        if ls.QGIS_AVAILABLE:
            self.skipTest("QGIS present")
        self.assertIn("QGIS not available", ls.apply_layout_style(object(), None)["warnings"][0])


if __name__ == "__main__":
    import unittest.mock  # noqa: F401
    unittest.main()


class TestUnitsAndAutoLabels(unittest.TestCase):
    def test_legend_spec_comes_from_the_algorithm_first_then_the_kind(self):
        self.assertEqual(os_.legend_spec_for("surface", "native:slope"), {"suffix": " \u00b0"})
        self.assertEqual(os_.legend_spec_for("population"), {"suffix": " people/cell"})
        self.assertEqual(os_.legend_spec_for("nonsense")["max"], "high")

    def test_label_field_prefers_a_readable_name_and_ignores_codes(self):
        self.assertEqual(os_.choose_label_field(["ID", "ADM1_PCODE", "Name", "name_en"]), "Name")
        self.assertEqual(os_.choose_label_field(["fid", "admin1Name_en", "admin1Pcode"]), "admin1Name_en")
        self.assertIsNone(os_.choose_label_field(["fid", "pcode", "value"]))
        # rc11 smoke test S5: OCHA COD-AB layers from HDX
        self.assertEqual(os_.choose_label_field(["adm1_name", "adm1_pcode", "adm0_name"]), "adm1_name")
        self.assertIsNone(os_.choose_label_field([]))

    def test_only_small_named_layers_are_labelled(self):
        self.assertEqual(os_.should_auto_label(12, ["name"]), (True, "name"))
        self.assertEqual(os_.should_auto_label(os_.AUTO_LABEL_MAX_FEATURES, ["name"])[0], True)
        self.assertEqual(os_.should_auto_label(os_.AUTO_LABEL_MAX_FEATURES + 1, ["name"]), (False, None))
        self.assertEqual(os_.should_auto_label(5, ["value"]), (False, None))
        self.assertEqual(os_.should_auto_label(0, ["name"]), (False, None))
        self.assertEqual(os_.should_auto_label("x", ["name"]), (False, None))


class TestAccessMapTemplate(unittest.TestCase):
    NAMES = {"a": "Clinics_roads_by_cost_0", "b": "Clinics_access_30", "c": "Districts", "d": "Clinics_reachable_area"}

    def test_ranking_puts_the_reach_polygon_first_and_other_layers_last(self):
        self.assertEqual(ls.order_for_access_map(["a", "b", "c", "d"], self.NAMES), ["d", "b", "a", "c"])

    def test_a_road_route_draws_above_the_plain_network_but_below_access_layers(self):
        # rc11 smoke test C1: the route line was drawn under 'OSM Roads (Yemen)'.
        self.assertLess(ls.arrange_rank("Route_Points_road_route"), ls.arrange_rank("OSM Roads (Yemen)"))
        self.assertGreater(ls.arrange_rank("Route_Points_road_route"), ls.arrange_rank("Clinics_roads_by_cost_0"))
        self.assertEqual(ls.arrange_rank("OSM Roads (Yemen)"), 9)

    def test_ranking_is_stable_for_layers_of_equal_rank(self):
        self.assertEqual(ls.order_for_access_map(["c", "x"], {"c": "A", "x": "B"}), ["c", "x"])

    def test_reading_guide_colours_come_from_the_access_styles(self):
        # audit F29 (#165): the guide said "green" while the map drew within-reach facilities blue.
        from cartogen_ai.core.agent.tools.routing_style import ACCESS_STYLES
        guide = ls.access_reading_guide(["Clinics_access_30"])
        self.assertIn(f"{ACCESS_STYLES['within']['label']} (blue)", guide)
        self.assertNotIn("green", guide)

    def test_reading_guide_describes_only_the_layers_present(self):
        guide = ls.access_reading_guide(["Clinics_access_30", "Districts"])
        self.assertIn("red", guide)
        self.assertNotIn("Road colour", guide)
        self.assertEqual(ls.access_reading_guide(["Districts"]), "")

    def test_zoom_layer_is_the_best_ranked_access_layer(self):
        self.assertEqual(ls.access_zoom_layer_name(["Districts", "Clinics_access_30", "Clinics_reachable_area"]),
                         "Clinics_reachable_area")
        self.assertIsNone(ls.access_zoom_layer_name(["Districts"]))


class TestMastheadColour(unittest.TestCase):
    def test_default_for_empty_or_invalid(self):
        for bad in ("", None, "red", "#12345", "#gggggg"):
            self.assertEqual(ls.resolve_masthead(bad), (ls.PALETTE["masthead_bg"], ls.PALETTE["masthead_fg"]), bad)

    def test_a_dark_colour_gets_white_text_and_a_light_one_dark_text(self):
        self.assertEqual(ls.resolve_masthead("#003366"), ("#003366", "#ffffff"))
        self.assertEqual(ls.resolve_masthead("#FFEEAA"), ("#ffeeaa", "#1f2d3a"))


class TestRc12AuditFixes(unittest.TestCase):
    """GitHub #120 (placeholder labels), #129 (body panel size, reading guide for the service-area polygon)."""

    def test_placeholder_names_are_not_labels(self):
        for value in (None, "", "Point", "Origin Point", "Origin Location", "Point (4902068.0, 1799912.0)", "Origin 2"):
            self.assertTrue(os_.is_generic_label_value(value), value)
        for value in ("Sana'a Hospital", "Health Centre 3", "Al Thawra Hospital"):
            self.assertFalse(os_.is_generic_label_value(value), value)

    def test_body_panel_is_sized_to_its_text(self):
        short = ls.body_text_height_mm("one line", 80, 9)
        longer = ls.body_text_height_mm("word " * 200, 80, 9)
        self.assertGreaterEqual(short, 8.0)
        self.assertLess(short, 20.0)
        self.assertGreater(longer, short * 2)

    def test_blank_lines_count_and_empty_text_keeps_the_minimum(self):
        self.assertGreaterEqual(ls.body_text_height_mm("", 80, 9), 8.0)
        self.assertGreater(ls.body_text_height_mm("a\n\n\nb", 80, 9), ls.body_text_height_mm("a\nb", 80, 9))

    def test_reading_guide_explains_the_service_area_polygon(self):
        guide = ls.access_reading_guide(["Origin_service_area_0", "Origin_roads_by_cost_0"])
        self.assertIn("Shaded area", guide)
        self.assertEqual(guide.count("Shaded area"), 1)
        both = ls.access_reading_guide(["Origin_service_area_0", "F_reachable_area"])
        self.assertEqual(both.count("Shaded area"), 1)
