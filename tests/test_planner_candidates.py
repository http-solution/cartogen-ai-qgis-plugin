"""Which candidates the representation planner offers for which layer (audit finding 6: plan_representations was split into one builder per
candidate). Old and new were compared on 40,000 random profiles with no difference; this pins the conditions."""
import unittest

from cartogen_ai.core.representation.models import FieldSemanticProfile as F
from cartogen_ai.core.representation.models import LayerSemanticProfile as L
from cartogen_ai.core.representation.planner import plan_representations


def layer(geometry, fields=None, density="medium", raster_type=None):
    return L("x", "raster" if geometry == "raster" else "vector", geometry, 10, "regional", density, 0.0, "EPSG:4326", True,
             {f.name: f for f in (fields or [])}, 0, raster_type)


def ids(profile, **kw):
    return [c.id for c in plan_representations(profile, **kw)]


class TestPointCandidates(unittest.TestCase):
    def test_bare_points_get_cluster_and_heatmap_only(self):
        self.assertEqual(sorted(ids(layer("point"))), ["point_cluster", "point_heatmap"])

    def test_a_numeric_quantity_field_adds_proportional_circles(self):
        got = ids(layer("point", [F("cases", "positive_quantity", 40, is_numeric=True)]))
        self.assertIn("point_proportional", got)
        self.assertNotIn("point_categorized", got)

    def test_a_category_field_with_2_to_12_values_adds_categorized_symbols(self):
        self.assertIn("point_categorized", ids(layer("point", [F("kind", "nominal", 5)])))
        self.assertNotIn("point_categorized", ids(layer("point", [F("kind", "nominal", 13)])))
        self.assertNotIn("point_categorized", ids(layer("point", [F("kind", "nominal", 1)])))

    def test_density_intent_puts_the_heatmap_first(self):
        self.assertEqual(ids(layer("point"), user_intent="show the hotspots")[0], "point_heatmap")


class TestPolygonCandidates(unittest.TestCase):
    def test_bare_polygons_get_overlay_and_hollow_outline(self):
        self.assertEqual(sorted(ids(layer("polygon"))), ["polygon_hollow_boundary", "polygon_translucent_overlay"])

    def test_a_rate_field_gets_a_choropleth_and_a_raw_count_gets_circles_not_a_choropleth_by_default(self):
        got = ids(layer("polygon", [F("poverty_rate", "rate_percentage", 30, is_numeric=True)]))
        self.assertIn("polygon_choropleth_rate", got)
        got = ids(layer("polygon", [F("affected", "positive_quantity", 30, is_numeric=True)]))
        self.assertIn("polygon_proportional_centroid", got)
        self.assertNotIn("polygon_choropleth_rate", got)

    def test_forcing_a_raw_count_into_a_choropleth_warns_and_scores_it_below_the_honest_option(self):
        profile = layer("polygon", [F("affected", "positive_quantity", 30, is_numeric=True)])
        cands = {c.id: c for c in plan_representations(profile, target_field="affected")}
        choropleth = cands["polygon_choropleth_rate"]
        self.assertTrue(choropleth.warnings)
        self.assertLess(choropleth.score.total_score, cands["polygon_proportional_centroid"].score.total_score)


class TestRasterAndOther(unittest.TestCase):
    def test_a_dem_gets_shaded_relief_and_other_rasters_get_pseudocolor(self):
        self.assertEqual(ids(layer("raster", raster_type="elevation_dem")), ["raster_shaded_relief"])
        self.assertEqual(ids(layer("raster", raster_type="index_ndvi")), ["raster_pseudocolor"])

    def test_lines_and_unknown_geometry_get_no_candidates(self):
        self.assertEqual(ids(layer("line")), [])
        self.assertEqual(ids(layer(None)), [])

    def test_results_are_sorted_best_first(self):
        scores = [c.score.total_score for c in plan_representations(layer("polygon", [F("r", "rate_percentage", 9, is_numeric=True)]))]
        self.assertEqual(scores, sorted(scores, reverse=True))


if __name__ == "__main__":
    unittest.main()
