# -*- coding: utf-8 -*-
"""F12 (rc7 smoke test, 2026-09-30): a dashboard of ~2,500 facility points drew every marker; slow to
open and unreadable at country zoom. Point layers with >= CLUSTER_MIN_POINTS features are now drawn as
clustered markers. The HTML tests need folium (skipped without it, like the rest of the dashboard tests)."""
import unittest

from cartogen_ai.core.agent.tools import export_tools as et


def _points(n, extra=None):
    feats = [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [44.0 + i * 0.001, 15.9 + i * 0.001]},
              "properties": {"name": f"f{i}", "score": i}} for i in range(n)]
    return feats + (extra or [])


def _layer(name, feats, **kw):
    return {"name": name, "geojson": {"type": "FeatureCollection", "features": feats}, **kw}


def _polygon():
    ring = [[44.0, 15.9], [44.1, 15.9], [44.1, 16.0], [44.0, 15.9]]
    return {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [ring]}, "properties": {"name": "p"}}


class TestShouldCluster(unittest.TestCase):
    def test_threshold(self):
        self.assertFalse(et._should_cluster(_points(et.CLUSTER_MIN_POINTS - 1)))
        self.assertTrue(et._should_cluster(_points(et.CLUSTER_MIN_POINTS)))

    def test_polygons_and_lines_never_cluster(self):
        self.assertFalse(et._should_cluster([_polygon()] * 500))
        line = {"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 1]]}, "properties": {}}
        self.assertFalse(et._should_cluster([line] * 500))

    def test_a_mostly_polygon_layer_with_some_points_does_not(self):
        self.assertFalse(et._should_cluster(_points(120, [_polygon()] * 500)))

    def test_a_few_stray_non_points_do_not_prevent_clustering(self):
        self.assertTrue(et._should_cluster(_points(200, [_polygon()] * 5)))

    def test_multipoint_counts_and_empty_is_safe(self):
        mp = {"type": "Feature", "geometry": {"type": "MultiPoint", "coordinates": [[0, 0], [1, 1]]}, "properties": {}}
        self.assertTrue(et._should_cluster([mp] * et.CLUSTER_MIN_POINTS))
        self.assertFalse(et._should_cluster([]))
        self.assertFalse(et._should_cluster(None))


class TestDashboardHtml(unittest.TestCase):
    def setUp(self):
        try:
            import folium  # noqa: F401
        except ImportError:
            self.skipTest("folium not installed")

    def test_a_large_point_layer_is_clustered_and_says_so(self):
        res = et._build_dashboard_html([_layer("Health Facilities", _points(150))])
        self.assertNotIn("error", res, res)
        self.assertIn("markerClusterGroup", res["html"])
        self.assertTrue(any("150 points are drawn as clusters" in w for w in res["warnings"]), res["warnings"])

    def test_a_small_point_layer_keeps_plain_markers(self):
        res = et._build_dashboard_html([_layer("Few", _points(20))])
        self.assertNotIn("markerClusterGroup", res["html"])
        self.assertFalse(any("clusters" in w for w in res["warnings"]))

    def test_a_polygon_layer_is_not_clustered(self):
        res = et._build_dashboard_html([_layer("Districts", [_polygon()] * 200)])
        self.assertNotIn("markerClusterGroup", res["html"])

    def test_only_the_large_point_layer_in_a_mixed_dashboard_is_clustered(self):
        res = et._build_dashboard_html([_layer("Districts", [_polygon()]), _layer("Facilities", _points(150))])
        self.assertEqual(res["html"].count("L.markerClusterGroup"), 1)

    def test_color_field_on_a_clustered_layer_is_dropped_with_a_warning(self):
        res = et._build_dashboard_html([_layer("Facilities", _points(150), color_field="score")])
        self.assertNotIn("error", res, res)
        self.assertTrue(any("color_field is not applied" in w for w in res["warnings"]), res["warnings"])

    def test_color_field_on_a_small_layer_is_still_applied(self):
        res = et._build_dashboard_html([_layer("Few", _points(20), color_field="score")])
        self.assertFalse(any("color_field is not applied" in w for w in res["warnings"]))


if __name__ == "__main__":
    unittest.main()
