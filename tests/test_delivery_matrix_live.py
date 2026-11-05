"""Master list HU-3, real QGIS (CI live job; written without a QGIS install, so CI's first run is its first execution): the delivery route's stop-to-stop matrix built from one
shortest-path tree per origin must equal the one built by the old native point-to-point calls, on a real road network, for both strategies and with one-way streets."""
import unittest
from unittest.mock import patch

from tests.test_network_units_live import QGIS_LIVE_AVAILABLE, _boot

if QGIS_LIVE_AVAILABLE:
    from qgis.core import QgsFeature, QgsGeometry, QgsProject, QgsVectorLayer

STOPS = ["POINT(0 0)", "POINT(0.02 0.03)", "POINT(0.04 0.04)", "POINT(0.04 0)", "POINT(0.01 0.01)"]      # all on grid vertices, where both methods place a point identically


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "needs real qgis.core bindings")
class TestDeliveryMatrixTreesMatchNative(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        why = _boot()
        if why:
            raise unittest.SkipTest(why)

    def setUp(self):
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        self.roads = QgsVectorLayer("LineString?crs=EPSG:4326&field=ow:string&field=maxspeed:double", "grid", "memory")
        feats = []
        for i in range(5):
            for j in range(4):
                for wkt in (f"LINESTRING({i * 0.01} {j * 0.01}, {i * 0.01} {(j + 1) * 0.01})", f"LINESTRING({j * 0.01} {i * 0.01}, {(j + 1) * 0.01} {i * 0.01})"):
                    f = QgsFeature(self.roads.fields())
                    f.setGeometry(QgsGeometry.fromWkt(wkt))
                    f.setAttributes(["no", 30.0 if (i + j) % 2 else 80.0])
                    feats.append(f)
        self.roads.dataProvider().addFeatures(feats)
        self.roads.updateExtents()
        self.stops = QgsVectorLayer("Point?crs=EPSG:4326&field=name:string", "stops", "memory")
        pts = []
        for n, wkt in enumerate(STOPS):
            f = QgsFeature(self.stops.fields())
            f.setGeometry(QgsGeometry.fromWkt(wkt))
            f.setAttributes([f"s{n}"])
            pts.append(f)
        self.stops.dataProvider().addFeatures(pts)
        QgsProject.instance().addMapLayer(self.roads)
        QgsProject.instance().addMapLayer(self.stops)
        from cartogen_ai.core.agent.tools import logistics_tools as lt
        self.lt = lt
        self.geoms = [f.geometry() for f in self.stops.getFeatures()]

    def _matrix(self, use_trees, fastest=False, extra=None):
        with patch.object(self.lt, "single_tree_costs_available", return_value=use_trees):
            return self.lt._build_network_distance_matrix(self.roads, self.geoms, extra or {}, source_crs=self.stops.crs(), fastest=fastest, default_speed=50)

    def _same(self, a, b, fastest):
        self.assertEqual(len(a), len(b))
        for row_a, row_b in zip(a, b, strict=True):
            for x, y in zip(row_a, row_b, strict=True):
                delta = max(1e-5, x * 0.001) if fastest else max(1.0, x * 0.001)
                self.assertAlmostEqual(x, y, delta=delta, msg=f"native {row_a} vs trees {row_b}")

    def test_shortest_distance_matrix_matches_the_native_calls(self):
        self._same(self._matrix(False), self._matrix(True), fastest=False)

    def test_fastest_matrix_with_a_speed_field_matches_the_native_calls(self):
        extra = {"SPEED_FIELD": "maxspeed"}
        self._same(self._matrix(False, True, extra), self._matrix(True, True, extra), fastest=True)

    def test_one_way_streets_give_the_same_asymmetric_matrix(self):
        self.roads.startEditing()
        for k, feature in enumerate(self.roads.getFeatures()):
            if k % 3 == 0:
                self.roads.changeAttributeValue(feature.id(), 0, "yes")
        self.assertTrue(self.roads.commitChanges())
        extra = {"DIRECTION_FIELD": "ow", "VALUE_FORWARD": "yes", "VALUE_BACKWARD": "-1", "VALUE_BOTH": "no", "DEFAULT_DIRECTION": 2}
        native, trees = self._matrix(False, extra=extra), self._matrix(True, extra=extra)
        self._same(native, trees, fastest=False)
        self.assertTrue(any(abs(native[i][j] - native[j][i]) > 1.0 for i in range(len(native)) for j in range(i)), "the network was meant to be one-way somewhere")

    def test_the_tool_visits_the_stops_in_the_same_order_either_way(self):
        from cartogen_ai.core.agent.tools.logistics_tools import optimize_delivery_route
        with patch.object(self.lt, "single_tree_costs_available", return_value=False):
            native = optimize_delivery_route("stops", road_network_layer="grid")
        QgsProject.instance().clear()
        self.setUp()
        trees = optimize_delivery_route("stops", road_network_layer="grid")
        self.assertTrue(native.get("success") and trees.get("success"), (native, trees))
        self.assertEqual(native["route_order"], trees["route_order"])


if __name__ == "__main__":
    unittest.main()
