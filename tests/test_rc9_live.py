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


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "requires real QGIS")
class TestSingleTreeMatrixMatchesNative(unittest.TestCase):
    """F08: costs from ONE shortest-path tree must equal what native:shortestpathpointtolayer returns, for destinations
    that sit on road vertices (where both methods place them identically)."""

    def setUp(self):
        _boot_qgis()
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        lines = []
        for i in range(5):
            for j in range(4):
                lines.append(f"LINESTRING({i * 0.01} {j * 0.01}, {i * 0.01} {(j + 1) * 0.01})")
                lines.append(f"LINESTRING({j * 0.01} {i * 0.01}, {(j + 1) * 0.01} {i * 0.01})")
        self.roads = _layer("LineString", "grid", lines)
        self.origin = _layer("Point", "origin", ["POINT(0 0)"])
        self.dests = _layer("Point", "dests", ["POINT(0.04 0.04)", "POINT(0.02 0.03)", "POINT(0.04 0)", "POINT(0.01 0.01)"])
        for layer in (self.roads, self.origin, self.dests):
            QgsProject.instance().addMapLayer(layer)

    def _native(self, strategy):
        from cartogen_ai.core.agent.tools.logistics_tools import travel_time_matrix
        res = travel_time_matrix("origin", "dests", "grid", strategy=strategy)
        self.assertNotIn("error", res, res)
        self.assertNotEqual(res.get("method"), "single_shortest_path_tree")
        return sorted(float(v) for v in next(iter(res["matrix"].values())).values())

    def _single(self, strategy):
        from cartogen_ai.core.agent.tools import logistics_tools as lt
        feats = [f for f in self.origin.getFeatures()]
        out = lt._single_tree_matrix(self.origin, feats, self.dests, self.roads, strategy, 50, None, None, "yes", "-1", "no")
        self.assertNotIn("error", out, out)
        return sorted(float(v) for v in next(iter(out["matrix"].values())).values())

    def test_shortest_distance_costs_match(self):
        native, single = self._native("shortest"), self._single("shortest")
        self.assertEqual(len(native), len(single))
        for a, b in zip(native, single):
            self.assertAlmostEqual(a, b, delta=max(1.0, a * 0.001))

    def test_fastest_hours_match(self):
        native, single = self._native("fastest"), self._single("fastest")
        for a, b in zip(native, single):
            self.assertAlmostEqual(a, b, delta=max(1e-5, a * 0.001))

    def test_more_than_the_threshold_uses_the_single_tree_and_reports_unreachable(self):
        from cartogen_ai.core.agent.tools import logistics_tools as lt
        far = _layer("Point", "many", [f"POINT({0.04 * (i % 2)} {0.04 * ((i // 2) % 2)})" for i in range(lt.MATRIX_LARGE_DESTINATIONS + 5)]
                     + ["POINT(5 5)"])
        QgsProject.instance().addMapLayer(far)
        res = lt.travel_time_matrix("origin", "many", "grid")
        self.assertEqual(res.get("method"), "single_shortest_path_tree", res)
        self.assertGreaterEqual(res["unreachable_count"], 0)


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "requires real QGIS")
class TestHealLayerTree(unittest.TestCase):
    """F07: rc7 projects carry a duplicate node and an orphan node; healing removes them and keeps every layer."""

    def setUp(self):
        _boot_qgis()
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)

    def test_duplicates_and_orphans_are_removed_and_no_layer_is_lost(self):
        project = QgsProject.instance()
        a = _layer("Point", "A", ["POINT(0 0)"])
        b = _layer("Point", "B", ["POINT(1 1)"])
        project.addMapLayer(a)
        project.addMapLayer(b)
        root = project.layerTreeRoot()
        root.insertLayer(0, a)                      # a second node for A: the rc7 duplicate
        ghost = _layer("Point", "Ghost", ["POINT(2 2)"])
        project.addMapLayer(ghost, False)
        root.addLayer(ghost)
        project.removeMapLayer(ghost.id())          # leaves a node with layer() None only if the tree keeps it
        before_nodes = len(root.findLayers())
        from cartogen_ai.core.agent.map_intelligence import heal_layer_tree
        healed = heal_layer_tree(project)
        self.assertEqual(len(project.mapLayers()), 2, "healing must never remove a layer")
        self.assertEqual(len(root.findLayers()), 2)
        self.assertGreaterEqual(healed["duplicates_removed"], 1)
        self.assertLessEqual(len(root.findLayers()), before_nodes)

    def test_a_clean_tree_is_untouched(self):
        project = QgsProject.instance()
        project.addMapLayer(_layer("Point", "A", ["POINT(0 0)"]))
        from cartogen_ai.core.agent.map_intelligence import heal_layer_tree
        self.assertEqual(heal_layer_tree(project), {"orphans_removed": 0, "duplicates_removed": 0})
        self.assertEqual(len(project.layerTreeRoot().findLayers()), 1)


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "requires real QGIS")
class TestResultsStoreRoundTrip(unittest.TestCase):
    """F06: an analysis output survives Save + Reopen. The layer keeps its id, name and renderer; an unsaved project is told why."""

    def setUp(self):
        _boot_qgis()
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        import tempfile
        self.tmp = tempfile.mkdtemp()

    def _memory_layer(self):
        layer = _layer("LineString", "Origin_service_area_lines_0",
                       ["LINESTRING(0 0, 1 1)", "LINESTRING(1 1, 2 0)"])
        self.assertEqual(layer.providerType(), "memory")
        return layer

    def test_unsaved_project_is_not_written_and_says_why(self):
        from cartogen_ai.core.agent.results_store import persist_layer
        layer = self._memory_layer()
        QgsProject.instance().addMapLayer(layer)
        res = persist_layer(layer)
        self.assertFalse(res["persisted"])
        self.assertIn("not been saved", res["reason"])
        self.assertEqual(layer.providerType(), "memory")

    def test_saved_project_keeps_the_features_after_reopen(self):
        from cartogen_ai.core.agent.tools.logistics_tools import _replace_named_layer
        proj_path = os.path.join(self.tmp, "p.qgz")
        QgsProject.instance().write(proj_path)
        layer = self._memory_layer()
        layer_id = layer.id()
        renderer_class = type(layer.renderer()).__name__
        _replace_named_layer("Origin_service_area_lines_0", layer)
        self.assertEqual(layer.providerType(), "ogr")
        self.assertEqual(layer.id(), layer_id)
        self.assertEqual(type(layer.renderer()).__name__, renderer_class)
        self.assertEqual(layer.featureCount(), 2)
        self.assertTrue(os.path.exists(os.path.join(self.tmp, "data", "20_processed", "cartogen_results.gpkg")))
        self.assertIn("Cartogen AI", layer.metadata().abstract())
        QgsProject.instance().write(proj_path)
        reopened = QgsProject()
        self.assertTrue(reopened.read(proj_path))
        again = reopened.mapLayersByName("Origin_service_area_lines_0")[0]
        self.assertTrue(again.isValid())
        self.assertEqual(again.featureCount(), 2)

    def test_a_rerun_replaces_the_layer_and_never_locks_the_store(self):
        from cartogen_ai.core.agent.tools.logistics_tools import _replace_named_layer
        QgsProject.instance().write(os.path.join(self.tmp, "p.qgz"))
        for _ in range(2):
            _replace_named_layer("Origin_service_area_lines_0", self._memory_layer())
        layers = QgsProject.instance().mapLayersByName("Origin_service_area_lines_0")
        self.assertEqual(len(layers), 1)
        self.assertEqual(layers[0].featureCount(), 2)


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "requires real QGIS")
class TestSnapshotLeavesTheLiveProjectAlone(unittest.TestCase):
    """F01: writing the isolation snapshot must not rename the live project, clear its dirty flag, or touch its auxiliary
    storage (manually moved labels). The first CI run also answers the open question about auxiliary storage."""

    def setUp(self):
        _boot_qgis()
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        import tempfile
        self.tmp = tempfile.mkdtemp()

    def test_a_saved_project_keeps_its_name_and_dirty_flag(self):
        from cartogen_ai.core.agent.services.script_isolation import _write_snapshot_of_live_project
        project = QgsProject.instance()
        path = os.path.join(self.tmp, "mine.qgz")
        project.addMapLayer(_layer("Point", "A", ["POINT(0 0)"]))
        project.write(path)
        project.setDirty(True)
        home_before = project.homePath()
        snapshot = os.path.join(self.tmp, "snap", "live_snapshot.qgz")
        os.makedirs(os.path.dirname(snapshot))
        _write_snapshot_of_live_project(project, snapshot)
        self.assertTrue(os.path.exists(snapshot))
        self.assertEqual(os.path.normpath(project.fileName()), os.path.normpath(path))
        self.assertEqual(os.path.normpath(project.homePath()), os.path.normpath(home_before))
        self.assertTrue(project.isDirty())

    def test_an_unsaved_project_stays_unsaved(self):
        from cartogen_ai.core.agent.services.script_isolation import _write_snapshot_of_live_project
        project = QgsProject.instance()
        project.addMapLayer(_layer("Point", "A", ["POINT(0 0)"]))
        snapshot = os.path.join(self.tmp, "live_snapshot.qgz")
        _write_snapshot_of_live_project(project, snapshot)
        self.assertEqual(project.fileName(), "")

    def test_the_auxiliary_storage_is_not_re_pointed_at_the_snapshot(self):
        from cartogen_ai.core.agent.services.script_isolation import _write_snapshot_of_live_project
        project = QgsProject.instance()
        path = os.path.join(self.tmp, "aux.qgz")
        project.addMapLayer(_layer("Point", "A", ["POINT(0 0)"]))
        project.write(path)
        aux = project.auxiliaryStorage()
        if aux is None or not hasattr(aux, "fileName"):
            self.skipTest("this QGIS exposes no auxiliary-storage file name")
        before = aux.fileName()
        _write_snapshot_of_live_project(project, os.path.join(self.tmp, "live_snapshot.qgz"))
        after = project.auxiliaryStorage().fileName()
        self.assertEqual(before, after, "the snapshot write re-pointed the live project's auxiliary storage")


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "requires real QGIS")
class TestReachGuardsOnRealLayers(unittest.TestCase):
    """F05: the degenerate-network guard and the speed-field vetting behave on real QgsVectorLayers."""

    def setUp(self):
        _boot_qgis()

    def test_a_zero_length_line_is_degenerate_and_a_real_one_is_not(self):
        from cartogen_ai.core.agent.tools.logistics_tools import _reachable_network_is_degenerate
        self.assertTrue(_reachable_network_is_degenerate(_layer("LineString", "z", ["LINESTRING(44 15.9, 44 15.9)"])))
        self.assertTrue(_reachable_network_is_degenerate(_layer("LineString", "e", [])))
        self.assertFalse(_reachable_network_is_degenerate(_layer("LineString", "r", ["LINESTRING(44 15.9, 44.1 16)"])))

    def test_a_99_percent_empty_speed_field_is_dropped_with_a_note(self):
        from cartogen_ai.core.agent.tools.logistics_tools import _vet_speed_field
        layer = QgsVectorLayer("LineString?crs=EPSG:4326&field=maxspeed:integer", "roads", "memory")
        feats = []
        for i in range(200):
            f = QgsFeature(layer.fields())
            f.setGeometry(QgsGeometry.fromWkt(f"LINESTRING({i} 0, {i + 1} 0)"))
            f.setAttribute("maxspeed", 60 if i == 0 else 0)
            feats.append(f)
        layer.dataProvider().addFeatures(feats)
        used, note = _vet_speed_field(layer, "maxspeed", 50)
        self.assertIsNone(used)
        self.assertIn("ignored", note)

    def test_a_well_populated_speed_field_is_kept(self):
        from cartogen_ai.core.agent.tools.logistics_tools import _vet_speed_field
        layer = QgsVectorLayer("LineString?crs=EPSG:4326&field=maxspeed:integer", "roads", "memory")
        feats = []
        for i in range(20):
            f = QgsFeature(layer.fields())
            f.setGeometry(QgsGeometry.fromWkt(f"LINESTRING({i} 0, {i + 1} 0)"))
            f.setAttribute("maxspeed", 50)
            feats.append(f)
        layer.dataProvider().addFeatures(feats)
        self.assertEqual(_vet_speed_field(layer, "maxspeed", 50), ("maxspeed", None))


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "requires real QGIS")
class TestHighlightIsRemovedFromTheCanvasScene(unittest.TestCase):
    """F11: an expired highlight must leave no QgsHighlight item in the canvas scene."""

    def setUp(self):
        _boot_qgis()
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)

    def test_no_highlight_item_remains_after_the_timer_fires(self):
        from unittest.mock import MagicMock
        from qgis.gui import QgsHighlight, QgsMapCanvas
        from qgis.PyQt.QtCore import QCoreApplication, QEventLoop, QTimer
        from cartogen_ai.core.ui.canvas_highlight import flash_layer_extent
        layer = _layer("Polygon", "Area", ["POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))"])
        QgsProject.instance().addMapLayer(layer)
        canvas = QgsMapCanvas()
        canvas.setLayers([layer])
        canvas.setExtent(layer.extent())
        iface = MagicMock()
        iface.mapCanvas.return_value = canvas
        highlight = flash_layer_extent(iface, layer, duration_ms=50)
        self.assertIsNotNone(highlight)
        self.assertEqual(len([i for i in canvas.scene().items() if isinstance(i, QgsHighlight)]), 1)
        loop = QEventLoop()
        QTimer.singleShot(400, loop.quit)
        loop.exec()
        QCoreApplication.processEvents()
        self.assertEqual([i for i in canvas.scene().items() if isinstance(i, QgsHighlight)], [])
