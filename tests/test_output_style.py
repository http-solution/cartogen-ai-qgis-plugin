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
