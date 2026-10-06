# -*- coding: utf-8 -*-
"""The travel-time matrix charges partial-edge costs on both sides of the single-tree threshold (audit F16, #152).

Acceptance from the issue: on a 1,000 m road, points at 490 m and 510 m cost about 490 m and 510 m, and the single-tree path
(above 200 destinations) agrees with the native point-to-layer tool (below it). Written without a QGIS install here: CI's
first run is its first execution."""
import unittest
from unittest.mock import patch

from tests.test_network_units_live import QGIS_LIVE_AVAILABLE, _Base, lon_offset

if QGIS_LIVE_AVAILABLE:
    from qgis.core import QgsFeature, QgsGeometry, QgsPointXY, QgsProject, QgsVectorLayer

LAT, LON0 = 15.0, 44.0
ROAD_M = 1000.0


def _x(metres):
    return LON0 + lon_offset(LAT, metres)


def _road(oneway=None):
    layer = QgsVectorLayer("LineString?crs=EPSG:4326&field=oneway:string", "roads", "memory")
    f = QgsFeature(layer.fields())
    f.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(_x(0), LAT), QgsPointXY(_x(ROAD_M), LAT)]))
    f.setAttributes([oneway])
    layer.dataProvider().addFeatures([f])
    QgsProject.instance().addMapLayer(layer)
    return layer


def _points(name, metres_list):
    layer = QgsVectorLayer("Point?crs=EPSG:4326&field=name:string", name, "memory")
    feats = []
    for i, m in enumerate(metres_list):
        f = QgsFeature(layer.fields())
        f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(_x(m), LAT)))
        f.setAttributes([f"p{i}"])
        feats.append(f)
    layer.dataProvider().addFeatures(feats)
    QgsProject.instance().addMapLayer(layer)
    return layer


class TestPartialEdgeCosts(_Base):
    def setUp(self):
        super().setUp()
        self.set_project("EPSG:3857", "WGS84")

    def _costs(self, origin_m, dest_m, single_tree, **kw):
        QgsProject.instance().clear()
        _road(kw.pop("oneway", None))
        _points("origin", [origin_m])
        _points("dest", dest_m)
        limit = 1 if single_tree else self.lt.MATRIX_LARGE_DESTINATIONS
        with patch.object(self.lt, "MATRIX_LARGE_DESTINATIONS", limit):
            res = self.lt.travel_time_matrix("origin", "dest", "roads", **kw)
        self.assertTrue(res.get("success"), res)
        self.assertEqual(res.get("method") == "single_shortest_path_tree", single_tree, res.get("method"))
        row = list(res["matrix"].values())[0]
        layer = QgsProject.instance().mapLayersByName("dest")[0]
        ids = {f["name"]: str(f.id()) for f in layer.getFeatures()}
        return [row.get(ids[f"p{i}"]) for i in range(len(dest_m))]

    def test_points_either_side_of_the_middle_cost_their_own_distance_on_both_paths(self):
        for single_tree in (False, True):
            with self.subTest(single_tree=single_tree):
                costs = self._costs(0.0, [490.0, 510.0, 1000.0], single_tree)
                for got, want in zip(costs, (490.0, 510.0, 1000.0)):
                    self.assertIsNotNone(got)
                    self.assertAlmostEqual(float(got), want, delta=8)

    def test_both_paths_use_feature_ids_as_keys(self):
        for single_tree in (False, True):
            with self.subTest(single_tree=single_tree):
                costs = self._costs(0.0, [250.0, 750.0], single_tree)
                self.assertNotIn(None, costs)

    def test_a_one_way_road_cannot_be_driven_backwards_on_either_path(self):
        # oneway 'F' = forward only (the digitised direction runs east): the point behind the origin is unreachable
        kw = dict(direction_field="oneway", value_forward="F", value_backward="T", value_both="B", oneway="F")
        for single_tree in (False, True):
            with self.subTest(single_tree=single_tree):
                ahead, behind = self._costs(300.0, [600.0, 100.0], single_tree, **dict(kw))
                self.assertAlmostEqual(float(ahead), 300.0, delta=8)
                self.assertIsNone(behind)


class TestGeofabrikDirectionEncodingWithBlanks(_Base):
    """#132: F/T/B must be recognised when some segments have a NULL or empty direction (a real layer, real NULL values)."""

    def test_blank_directions_do_not_hide_the_geofabrik_encoding(self):
        from cartogen_ai.core.agent.tools.logistics_tools import _network_direction_speed_params
        layer = QgsVectorLayer("LineString?crs=EPSG:4326&field=oneway:string", "roads_blank", "memory")
        feats = []
        for i, value in enumerate(["F", "B", None, ""]):
            f = QgsFeature(layer.fields())
            f.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(44.0 + i, 15.0), QgsPointXY(44.5 + i, 15.0)]))
            f.setAttributes([value])
            feats.append(f)
        layer.dataProvider().addFeatures(feats)
        extra, error = _network_direction_speed_params(layer, direction_field="oneway")
        self.assertIsNone(error)
        self.assertEqual((extra["VALUE_FORWARD"], extra["VALUE_BACKWARD"], extra["VALUE_BOTH"]), ("F", "T", "B"))


if __name__ == "__main__":
    unittest.main()
