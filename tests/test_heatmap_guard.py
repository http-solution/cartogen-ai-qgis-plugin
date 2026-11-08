"""DEF-34 (round-3 smoke rows D2 and E5): the native kernel-density heatmap, run through the allowlist, must not bypass the guards that
hotspot_analysis applies -- a point layer only, and no radius or cell size of a degree or more on a latitude/longitude layer."""
import unittest
from types import SimpleNamespace

from cartogen_ai.core.agent.tools import processing_allowlist_tools as tools

HEATMAP = "native:heatmapkerneldensityestimation"


def layer(kind, geographic=True, name="smoke_points"):
    crs = SimpleNamespace(isValid=lambda: True, isGeographic=lambda: geographic, authid=lambda: "EPSG:4326" if geographic else "EPSG:32638")
    return SimpleNamespace(geometryType=lambda: kind, name=lambda: name, crs=lambda: crs)


class TestHeatmapViolation(unittest.TestCase):
    def test_polygon_layer_is_refused_and_nothing_runs(self):
        text = tools.heatmap_violation(HEATMAP, {"INPUT": layer(2, name="smoke_zones"), "RADIUS": 0.01})
        self.assertIn("needs a point layer", text)
        self.assertIn("smoke_zones", text)
        self.assertIn("Nothing was run", text)

    def test_line_layer_is_refused(self):
        self.assertIn("point layer", tools.heatmap_violation(HEATMAP, {"INPUT": layer(1), "RADIUS": 0.01}))

    def test_one_degree_radius_on_a_geographic_layer_is_refused_with_the_conversion(self):
        text = tools.heatmap_violation(HEATMAP, {"INPUT": layer(0), "RADIUS": 1, "PIXEL_SIZE": 0.01})
        self.assertIn("DEGREES", text)
        self.assertIn("the radius", text)
        self.assertIn("Nothing was run", text)

    def test_large_cell_size_in_degrees_is_refused(self):
        self.assertIn("the cell size", tools.heatmap_violation(HEATMAP, {"INPUT": layer(0), "RADIUS": 0.05, "PIXEL_SIZE": 2}))

    def test_a_sensible_degree_radius_and_a_projected_metre_radius_pass(self):
        self.assertIsNone(tools.heatmap_violation(HEATMAP, {"INPUT": layer(0), "RADIUS": 0.05, "PIXEL_SIZE": 0.005}))
        self.assertIsNone(tools.heatmap_violation(HEATMAP, {"INPUT": layer(0, geographic=False), "RADIUS": 5000, "PIXEL_SIZE": 100}))

    def test_the_qgis_id_is_guarded_too(self):
        self.assertIsNotNone(tools.heatmap_violation("qgis:heatmapkerneldensityestimation", {"INPUT": layer(2)}))

    def test_other_algorithms_and_unresolved_names_are_left_alone(self):
        self.assertIsNone(tools.heatmap_violation("native:buffer", {"INPUT": layer(2), "RADIUS": 5}))
        self.assertIsNone(tools.heatmap_violation(HEATMAP, {"INPUT": "smoke_zones", "RADIUS": 5}))

    def test_enum_style_geometry_type_is_read(self):
        point = SimpleNamespace(value=0)
        self.assertIsNone(tools.heatmap_violation(HEATMAP, {"INPUT": layer(point), "RADIUS": 0.05}))

    def test_the_check_runs_before_the_algorithm_through_the_shared_gate(self):
        with self.assertRaises(ValueError) as ctx:
            tools._check_raster_lists(HEATMAP, {"INPUT": layer(2)}, None)
        self.assertIn("point layer", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
