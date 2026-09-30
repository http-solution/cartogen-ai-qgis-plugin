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


class TestTemporalDashboardClustering(unittest.TestCase):
    """generate_temporal_dashboard's slider hides a feature by zeroing its opacity, which a cluster
    would still count, so a clustered temporal layer is rebuilt from the ACTIVE markers every frame."""

    def setUp(self):
        try:
            import folium  # noqa: F401
        except ImportError:
            self.skipTest("folium not installed")

    @staticmethod
    def _timed_points(n):
        feats = _points(n)
        for i, f in enumerate(feats):
            f["properties"]["start"] = f"2020-{1 + i % 12:02d}-01"
            f["properties"]["group"] = "A" if i % 2 else "B"
        return feats

    def _build(self, feats, **layer_kw):
        layer = _layer("Incidents", feats, start_field="start", category_field="group", **layer_kw)
        return et._build_temporal_dashboard_html([layer])

    def test_a_large_temporal_point_layer_is_clustered_and_says_so(self):
        res = self._build(self._timed_points(150))
        self.assertNotIn("error", res, res)
        self.assertEqual(res["html"].count("L.markerClusterGroup"), 1)
        self.assertTrue(any("150 points are drawn as clusters" in w for w in res["warnings"]), res["warnings"])

    def test_the_frame_update_rebuilds_the_cluster_from_active_markers_only(self):
        html = self._build(self._timed_points(150))["html"]
        self.assertIn("cluster.clearLayers();", html)
        self.assertIn("cluster.addLayers(activeSubs);", html)
        self.assertIn("__cartogenIsActive(props, ms)", html)

    def test_the_cluster_is_wired_to_its_geojson_layer_by_position(self):
        import re
        html = self._build(self._timed_points(150))["html"]
        layers = re.search(r"function __cartogenLayers\(\) \{ return \[(geo_json_[0-9a-f]+)\]; \}", html)
        clusters = re.search(r"function __cartogenClusters\(\) \{ return \[(marker_cluster_[0-9a-f]+)\]; \}", html)
        self.assertIsNotNone(layers, "layer list not found")
        self.assertIsNotNone(clusters, "cluster list not found")

    def test_layer_variables_are_not_referenced_when_the_script_loads(self):
        """folium 0.20 emits the map script after this block, so a top-level reference to geo_json_*
        is a ReferenceError that kills the slider (found by rendering the page in Chromium)."""
        import re
        html = self._build(self._timed_points(20))["html"]
        script = html[html.index("function __cartogenLayers()"):]
        top_level = re.search(r"^\s*var __cartogen\w+ = [^;]*geo_json_", script, flags=re.M)
        self.assertIsNone(top_level)

    def test_a_small_temporal_layer_keeps_the_opacity_toggle_and_no_cluster(self):
        html = self._build(self._timed_points(20))["html"]
        self.assertNotIn("L.markerClusterGroup", html)
        self.assertIn("function __cartogenClusters() { return [null]; }", html)
        self.assertIn("sub.setStyle({opacity: active ? 1 : 0", html)

    def test_a_temporal_polygon_layer_is_not_clustered(self):
        feats = [_polygon() for _ in range(150)]
        for f in feats:
            f["properties"].update({"start": "2020-01-01", "group": "A"})
        res = self._build(feats)
        self.assertNotIn("L.markerClusterGroup", res["html"])

    def test_a_static_layer_beside_a_clustered_temporal_one_still_renders(self):
        static = _layer("Outline", [_polygon()])
        temporal = _layer("Incidents", self._timed_points(150), start_field="start", category_field="group")
        res = et._build_temporal_dashboard_html([static, temporal])
        self.assertNotIn("error", res, res)
        self.assertEqual(res["html"].count("L.markerClusterGroup"), 1)


class TestPinnedClusterLibraryAndSliderEnd(unittest.TestCase):
    """F12 follow-ups from the rc8 audit: the page must load the markercluster version that was tested
    (folium 0.20 defaults to 1.1.0), and the temporal slider must be able to reach the last date."""

    def setUp(self):
        try:
            import folium  # noqa: F401
        except ImportError:
            self.skipTest("folium not installed")

    def test_static_dashboard_loads_the_pinned_version_only(self):
        html = et._build_dashboard_html([_layer("Health Facilities", _points(150))])["html"]
        self.assertIn("leaflet.markercluster/%s/leaflet.markercluster.js" % et.MARKERCLUSTER_VERSION, html)
        self.assertNotIn("leaflet.markercluster/1.1.0", html)

    def test_temporal_dashboard_loads_the_pinned_version_only(self):
        feats = _points(150)
        for i, f in enumerate(feats):
            f["properties"]["start"] = f"2020-{1 + i % 12:02d}-01"
        html = et._build_temporal_dashboard_html([_layer("Incidents", feats, start_field="start")])["html"]
        self.assertIn("leaflet.markercluster/%s/" % et.MARKERCLUSTER_VERSION, html)
        self.assertNotIn("leaflet.markercluster/1.1.0", html)

    def test_slider_can_reach_the_last_date_when_the_span_is_not_a_multiple_of_the_step(self):
        import re
        feats = _points(5)
        for f, d in zip(feats, ["2020-01-01", "2020-01-10", "2020-01-20", "2020-01-25", "2020-02-01"]):
            f["properties"]["start"] = d
        html = et._build_temporal_dashboard_html([_layer("Incidents", feats, start_field="start")], step_days=30)["html"]
        m = re.search(r'id="cartogen-slider" type="range" min="(\d+)" max="(\d+)" step="(\d+)"', html)
        self.assertIsNotNone(m)
        lo, hi, step = map(int, m.groups())
        last_ms = 1580515200000  # 2020-02-01 00:00 UTC
        self.assertGreaterEqual(hi, last_ms)            # the last date is inside the slider range
        self.assertEqual((hi - lo) % step, 0)           # and the end is an actual step position
        self.assertLess(hi - last_ms, step)             # without extending by a whole extra step
