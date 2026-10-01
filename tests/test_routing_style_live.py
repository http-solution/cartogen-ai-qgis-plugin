# -*- coding: utf-8 -*-
"""Live-QGIS tests for the routing/reach styling (CI `qgis-live-tests`). Written without a QGIS install: the first CI run
is their first execution."""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from qgis.core import QgsFeature, QgsGeometry, QgsPointXY, QgsProject, QgsVectorLayer
    QGIS_LIVE_AVAILABLE = True
except ImportError:
    QGIS_LIVE_AVAILABLE = False


def _boot_qgis():
    from tests.test_chat_widget_live import _boot_qgis as _shared_boot
    return _shared_boot()


def _layer(kind, name, wkts, fields=""):
    layer = QgsVectorLayer(f"{kind}?crs=EPSG:4326{fields}", name, "memory")
    feats = []
    for wkt in wkts:
        f = QgsFeature(layer.fields())
        f.setGeometry(QgsGeometry.fromWkt(wkt))
        feats.append(f)
    layer.dataProvider().addFeatures(feats)
    layer.updateExtents()
    return layer


def _grid_roads(n=5, step=0.01):
    lines = []
    for i in range(n):
        for j in range(n - 1):
            lines.append(f"LINESTRING({i * step} {j * step}, {i * step} {(j + 1) * step})")
            lines.append(f"LINESTRING({j * step} {i * step}, {(j + 1) * step} {i * step})")
    return _layer("LineString", "grid", lines)


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "requires real QGIS")
class TestRendererBuilders(unittest.TestCase):
    def setUp(self):
        _boot_qgis()

    def test_roads_are_graded_in_labelled_cost_bands(self):
        from cartogen_ai.core.agent.tools import routing_style as rs
        layer = _layer("LineString", "r", ["LINESTRING(0 0, 1 1)"], "&field=travel_cost:double")
        edges = rs.cost_band_edges(5000, 5)
        self.assertTrue(rs.style_lines_by_cost(layer, "travel_cost", edges, "meters"))
        renderer = layer.renderer()
        self.assertEqual(renderer.type(), "graduatedSymbol")
        ranges = renderer.ranges()
        self.assertEqual(len(ranges), 5)
        self.assertEqual(ranges[0].label(), "0 m - 1 km")
        self.assertEqual(ranges[0].symbol().color().name(), rs.COST_RAMP[0])
        self.assertEqual(ranges[-1].symbol().color().name(), rs.COST_RAMP[-1])

    def test_reach_polygons_are_translucent_and_the_upper_bound_is_dashed(self):
        from cartogen_ai.core.agent.tools import routing_style as rs
        for method in rs.REACH_STYLES:
            layer = _layer("Polygon", method, ["POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))"])
            self.assertTrue(rs.style_reach_polygon(layer, method))
            symbol = layer.renderer().symbol()
            self.assertLess(symbol.color().alpha(), 128, method)
            sym_layer = symbol.symbolLayer(0)
            if method == "convex_hull":
                self.assertEqual(sym_layer.strokeStyle().name, "DashLine")
            else:
                self.assertEqual(sym_layer.strokeStyle().name, "SolidLine")

    def test_unreached_facilities_are_red_larger_and_drawn_on_top(self):
        from cartogen_ai.core.agent.tools import routing_style as rs
        layer = _layer("Point", "f", ["POINT(0 0)", "POINT(1 1)"], "&field=access_class:string")
        self.assertTrue(rs.style_access_points(layer, "access_class"))
        renderer = layer.renderer()
        self.assertEqual(renderer.type(), "categorizedSymbol")
        self.assertTrue(renderer.usingSymbolLevels())
        # renderer.categories() returns COPIES; keep the list alive while the symbols are read (a temporary list freed
        # its symbols under us and segfaulted the CI run).
        categories = renderer.categories()
        by_value = {c.value(): c for c in categories}
        beyond, within = by_value["beyond"].symbol(), by_value["within"].symbol()
        self.assertEqual(beyond.color().name(), "#d62828")
        self.assertGreater(beyond.size(), within.size())
        self.assertGreater(beyond.symbolLayer(0).renderingPass(), within.symbolLayer(0).renderingPass())


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "requires real QGIS")
class TestReachGroup(unittest.TestCase):
    def setUp(self):
        _boot_qgis()
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)

    def _three(self):
        project = QgsProject.instance()
        layers = {}
        for method in ("concave_hull", "road_buffer", "convex_hull"):
            lyr = _layer("Polygon", f"reach_{method}", ["POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))"])
            project.addMapLayer(lyr, False)          # no top-level node: the group adds one
            layers[method] = lyr
        return layers

    def test_one_group_headline_first_and_visible_the_others_hidden(self):
        from cartogen_ai.core.agent.tools import routing_style as rs
        layers = self._three()
        group = rs.group_reach_layers(layers, "concave_hull", "Clinics")
        root = QgsProject.instance().layerTreeRoot()
        self.assertIsNotNone(group)
        self.assertEqual(group.name(), "Reach figures: Clinics")
        ids = [child.layerId() for child in group.children()]
        self.assertEqual(ids[0], layers["concave_hull"].id())
        self.assertEqual(set(ids), {lyr.id() for lyr in layers.values()})
        self.assertTrue(group.findLayer(layers["concave_hull"].id()).itemVisibilityChecked())
        self.assertFalse(group.findLayer(layers["road_buffer"].id()).itemVisibilityChecked())
        self.assertFalse(group.findLayer(layers["convex_hull"].id()).itemVisibilityChecked())
        # one node per layer, none outside the group (the F07 duplicate must not come back)
        self.assertEqual(len(root.findLayers()), 3)
        self.assertEqual(len(QgsProject.instance().mapLayers()), 3)

    def test_calling_it_again_reuses_the_group(self):
        from cartogen_ai.core.agent.tools import routing_style as rs
        layers = self._three()
        rs.group_reach_layers(layers, "concave_hull", "Clinics")
        rs.group_reach_layers(layers, "road_buffer", "Clinics")
        root = QgsProject.instance().layerTreeRoot()
        groups = [c for c in root.children() if c.nodeType() == 0]   # QgsLayerTreeNode.NodeGroup
        self.assertEqual(len(groups), 1)
        self.assertEqual(len(root.findLayers()), 3)

    def test_a_layer_that_already_has_a_top_level_node_is_not_given_a_second_one(self):
        from cartogen_ai.core.agent.tools import routing_style as rs
        project = QgsProject.instance()
        layers = self._three()
        extra = _layer("Polygon", "already_in_tree", ["POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))"])
        project.addMapLayer(extra)                    # ordinary add: has a root node
        rs.group_reach_layers(layers, "concave_hull", "Clinics", extra_hidden=[extra])
        self.assertEqual(len(project.layerTreeRoot().findLayers()), 4)


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "requires real QGIS")
class TestCostGradedRoadsEndToEnd(unittest.TestCase):
    def setUp(self):
        _boot_qgis()
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        project = QgsProject.instance()
        project.addMapLayer(_grid_roads())
        project.addMapLayer(_layer("Point", "origin", ["POINT(0 0)"]))

    def test_costs_grow_with_distance_from_the_origin(self):
        from cartogen_ai.core.agent.tools import logistics_tools as lt
        network = QgsProject.instance().mapLayersByName("grid")[0]
        ellipsoid = lt._network_context().ellipsoid()
        layer, reason = lt._cost_graded_roads(network, QgsPointXY(0.0, 0.0), "shortest", 50, None, None, "yes", "-1", "no",
                                              ellipsoid, 3000.0, "graded")
        self.assertIsNotNone(layer, reason)
        costs = [f["travel_cost"] for f in layer.getFeatures()]
        self.assertTrue(costs)
        self.assertGreater(max(costs), 1000)            # a 0.01 deg grid step is ~1.1 km
        self.assertLessEqual(min(costs), 1500)
        self.assertGreater(max(costs), min(costs))

    def test_calculate_service_area_adds_a_graded_layer_and_hides_the_plain_lines(self):
        from cartogen_ai.core.agent.tools.logistics_tools import calculate_service_area
        res = calculate_service_area("origin", "grid", 2500)
        self.assertNotIn("error", res, res)
        self.assertEqual(res.get("styled_layers"), ["origin_roads_by_cost_0"])
        project = QgsProject.instance()
        graded = project.mapLayersByName("origin_roads_by_cost_0")[0]
        plain = project.mapLayersByName("origin_service_area_lines_0")[0]
        root = project.layerTreeRoot()
        self.assertEqual(graded.renderer().type(), "graduatedSymbol")
        self.assertTrue(root.findLayer(graded.id()).itemVisibilityChecked())
        self.assertFalse(root.findLayer(plain.id()).itemVisibilityChecked())
        self.assertIn("origin_service_area_lines_0", res["layers_created"])   # the analysis layer is still reported

    def test_style_by_cost_false_keeps_the_plain_lines_only(self):
        from cartogen_ai.core.agent.tools.logistics_tools import calculate_service_area
        res = calculate_service_area("origin", "grid", 2500, style_by_cost=False)
        self.assertNotIn("error", res, res)
        self.assertNotIn("styled_layers", res)
        self.assertEqual(QgsProject.instance().mapLayersByName("origin_roads_by_cost_0"), [])
        project = QgsProject.instance()
        plain = project.mapLayersByName("origin_service_area_lines_0")[0]
        self.assertTrue(project.layerTreeRoot().findLayer(plain.id()).itemVisibilityChecked())

    def test_one_node_per_layer_after_styling(self):
        from cartogen_ai.core.agent.tools.logistics_tools import calculate_service_area
        calculate_service_area("origin", "grid", 2500)
        project = QgsProject.instance()
        self.assertEqual(len(project.layerTreeRoot().findLayers()), len(project.mapLayers()))


if __name__ == "__main__":
    unittest.main()
