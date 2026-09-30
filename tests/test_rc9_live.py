# -*- coding: utf-8 -*-
"""Live-QGIS tests for the rc8-audit fixes (runs only where qgis.core exists: the CI `qgis-live-tests` job).

Written WITHOUT a QGIS install: the first CI run is their first execution. Each class names the finding it guards."""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from qgis.core import QgsFeature, QgsGeometry, QgsProject, QgsVectorLayer
    QGIS_LIVE_AVAILABLE = True
except ImportError:
    QGIS_LIVE_AVAILABLE = False


def _boot_qgis():
    from tests.test_chat_widget_live import _boot_qgis as _shared_boot
    return _shared_boot()


def _layer(kind, name, wkts, crs="EPSG:4326"):
    layer = QgsVectorLayer(f"{kind}?crs={crs}", name, "memory")
    feats = []
    for wkt in wkts:
        f = QgsFeature()
        f.setGeometry(QgsGeometry.fromWkt(wkt))
        feats.append(f)
    layer.dataProvider().addFeatures(feats)
    layer.updateExtents()
    return layer


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "requires real QGIS")
class TestConcaveReachPolygon(unittest.TestCase):
    """F09: the concave hull of reached roads must follow an L-shaped network more tightly than the convex hull."""

    def setUp(self):
        _boot_qgis()
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)

    def test_concave_is_smaller_than_convex_and_still_covers_the_roads(self):
        from cartogen_ai.core.agent.tools.logistics_tools import _concave_reach_polygon
        # an L: a long horizontal road and a long vertical road meeting at the corner, plus a dense grid of vertices
        lines = []
        for i in range(0, 11):
            lines.append(f"LINESTRING({i * 0.1} 0, {i * 0.1 + 0.1} 0)")
            lines.append(f"LINESTRING(0 {i * 0.1}, 0 {i * 0.1 + 0.1})")
        roads = _layer("LineString", "roads", lines)
        poly = _concave_reach_polygon([roads], 0.3, "reach")
        self.assertTrue(poly.isValid())
        hull_geom = next(poly.getFeatures()).geometry()
        convex = QgsGeometry.unaryUnion([f.geometry() for f in roads.getFeatures()]).convexHull()
        self.assertLess(hull_geom.area(), convex.area())
        self.assertGreater(hull_geom.area(), 0)

    def test_a_layer_with_no_geometry_is_an_error_not_a_crash(self):
        from cartogen_ai.core.agent.tools.logistics_tools import _concave_reach_polygon
        empty = _layer("LineString", "empty", [])
        with self.assertRaises(RuntimeError):
            _concave_reach_polygon([empty], 0.85, "reach")


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "requires real QGIS")
class TestDashboardBackdrop(unittest.TestCase):
    """F12: a dashboard with no tile server draws the project's own polygon boundary under the data."""

    def setUp(self):
        _boot_qgis()
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        try:
            import folium  # noqa: F401
        except ImportError:
            self.skipTest("folium not installed")

    def _project(self):
        pts = _layer("Point", "Clinics", [f"POINT({44 + i * 0.01} {15.9 + i * 0.01})" for i in range(5)])
        area = _layer("Polygon", "Yemen", ["POLYGON((41 12, 54 12, 54 19, 41 19, 41 12))"])
        roads = _layer("LineString", "Roads", ["LINESTRING(44 15.9, 44.1 16)"])
        for layer in (pts, area, roads):
            QgsProject.instance().addMapLayer(layer)

    def test_the_backdrop_is_in_the_page_and_no_tiles_are_requested(self):
        from cartogen_ai.core.agent.tools.export_tools import generate_html_dashboard
        import tempfile
        self._project()
        out = os.path.join(tempfile.mkdtemp(), "d.html")
        res = generate_html_dashboard([{"layer_name": "Clinics"}], output_path=out, basemap="none", backdrop_layer="Yemen")
        self.assertNotIn("error", res, res)
        html = open(out, encoding="utf-8").read()
        self.assertIn("#eeeae0", html)
        self.assertNotIn("tile_layer", html)

    def test_a_non_polygon_backdrop_is_refused_with_a_reason(self):
        from cartogen_ai.core.agent.tools.export_tools import generate_html_dashboard
        self._project()
        res = generate_html_dashboard([{"layer_name": "Clinics"}], backdrop_layer="Roads")
        self.assertIn("not a polygon", res.get("error", ""))

    def test_a_missing_backdrop_is_refused_with_a_reason(self):
        from cartogen_ai.core.agent.tools.export_tools import generate_html_dashboard
        self._project()
        res = generate_html_dashboard([{"layer_name": "Clinics"}], backdrop_layer="Nope")
        self.assertIn("not found", res.get("error", ""))


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "requires real QGIS")
class TestModelViewInRealQgis(unittest.TestCase):
    """F21: get_layers and the map-context summary withhold field names of a protected layer under an enforcing gate
    with a cloud provider, and show them for an open layer or a local provider."""

    def setUp(self):
        _boot_qgis()
        QgsProject.instance().clear()
        from cartogen_ai.core.models import model_view
        self.addCleanup(model_view.set_policy_provider, None)
        self.addCleanup(QgsProject.instance().clear)
        layer = QgsVectorLayer("Point?crs=EPSG:4326&field=osm_id:integer&field=name:string", "Health", "memory")
        QgsProject.instance().addMapLayer(layer)
        from cartogen_ai.core.models import sensitivity
        sensitivity.set_layer_sensitivity(layer, "SENSITIVE", "test")
        self.layer = layer

    def test_get_layers_withholds_the_fields_of_a_protected_layer(self):
        from cartogen_ai.core.agent.tools.vector_tools import get_layers
        from cartogen_ai.core.models import model_view
        model_view.set_policy_provider(lambda: ("enforce", False, False))
        entry = next(e for e in get_layers() if e["name"] == "Health")
        self.assertEqual(entry["fields"], [])
        self.assertTrue(entry["schema_hidden"])
        self.assertIn("feature_count", entry)

    def test_get_layers_shows_fields_to_a_local_provider(self):
        from cartogen_ai.core.agent.tools.vector_tools import get_layers
        from cartogen_ai.core.models import model_view
        model_view.set_policy_provider(lambda: ("enforce", True, False))
        entry = next(e for e in get_layers() if e["name"] == "Health")
        self.assertEqual(entry["fields"], ["osm_id", "name"])

    def test_the_map_context_summary_is_masked_the_same_way(self):
        from cartogen_ai.core.agent.map_context import get_map_context_summary
        from cartogen_ai.core.models import model_view
        model_view.set_policy_provider(lambda: ("enforce", False, False))
        ctx = get_map_context_summary()
        entry = next(e for e in ctx["layers"] if e["name"] == "Health")
        self.assertEqual(entry["fields"], [])
        self.assertTrue(entry["schema_hidden"])
