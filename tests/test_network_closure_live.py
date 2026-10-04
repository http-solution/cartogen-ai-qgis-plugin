# -*- coding: utf-8 -*-
"""Closed road segments are removed from the network, in real QGIS (audit F19, #155).

Written without a QGIS install here: CI's first run is its first execution. Ground truth for lengths is measured on the WGS84
ellipsoid, as in test_network_units_live."""
import unittest

from tests.test_network_units_live import QGIS_LIVE_AVAILABLE, _Base, lon_offset

if QGIS_LIVE_AVAILABLE:
    from qgis.core import QgsFeature, QgsGeometry, QgsPointXY, QgsProject, QgsVectorLayer

LAT, LON0 = 15.0, 44.0
SEGMENT_M = 1000.0


def _roads(speeds):
    """Three consecutive ~1 km segments heading east from (LON0, LAT), one feature each, with the given `speed` values."""
    layer = QgsVectorLayer("LineString?crs=EPSG:4326&field=speed:double", "roads", "memory")
    step = lon_offset(LAT, SEGMENT_M)
    feats = []
    for i, speed in enumerate(speeds):
        f = QgsFeature(layer.fields())
        f.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(LON0 + i * step, LAT), QgsPointXY(LON0 + (i + 1) * step, LAT)]))
        f.setAttributes([speed])
        feats.append(f)
    layer.dataProvider().addFeatures(feats)
    layer.updateExtents()
    QgsProject.instance().addMapLayer(layer)
    return layer


def _origin():
    layer = QgsVectorLayer("Point?crs=EPSG:4326&field=name:string", "origin", "memory")
    f = QgsFeature(layer.fields())
    f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(LON0, LAT)))
    f.setAttributes(["o"])
    layer.dataProvider().addFeatures([f])
    QgsProject.instance().addMapLayer(layer)
    return layer


class TestClosedSegmentsAreRemoved(_Base):
    def setUp(self):
        super().setUp()
        self.set_project("EPSG:3857", "WGS84")

    def _reach_m(self, result):
        self.assertTrue(result.get("success"), result)
        lines = [QgsProject.instance().mapLayersByName(n)[0] for n in result["layers_created"] if "_lines_" in n]
        return sum(self.metres_of(layer) for layer in lines)

    def test_a_closed_middle_segment_cuts_the_network_for_both_strategies(self):
        for strategy, cost in (("shortest", 5000), ("fastest", 1.0)):
            with self.subTest(strategy=strategy):
                QgsProject.instance().clear()
                _roads([50.0, -1.0, 50.0])
                _origin()
                res = self.lt.calculate_service_area("origin", "roads", cost, strategy=strategy, speed_field="speed")
                self.assertAlmostEqual(self._reach_m(res), SEGMENT_M, delta=60)     # only the first segment
                self.assertEqual(res.get("closed_segments_removed"), 1)

    def test_without_a_closure_the_whole_road_is_reached(self):
        _roads([50.0, 50.0, 50.0])
        _origin()
        res = self.lt.calculate_service_area("origin", "roads", 5000, speed_field="speed")
        self.assertAlmostEqual(self._reach_m(res), 3 * SEGMENT_M, delta=120)
        self.assertNotIn("closed_segments_removed", res)

    def test_zero_or_empty_speed_is_unknown_not_closed(self):
        # real OSM maxspeed is 0/NULL on almost every road; that must never delete the network.
        _roads([50.0, 0.0, None])
        _origin()
        res = self.lt.calculate_service_area("origin", "roads", 5000, speed_field="speed")
        self.assertNotIn("closed_segments_removed", res)

    def test_a_fully_closed_network_is_an_explicit_error(self):
        _roads([-1.0, -1.0, -1.0])
        _origin()
        res = self.lt.calculate_service_area("origin", "roads", 5000, speed_field="speed")
        self.assertIn("error", res)
        self.assertIn("closed", res["error"])

    def test_the_users_layer_is_never_edited(self):
        roads = _roads([50.0, -1.0, 50.0])
        _origin()
        self.lt.calculate_service_area("origin", "roads", 5000, speed_field="speed")
        self.assertEqual(roads.featureCount(), 3)
        self.assertEqual(sorted(f["speed"] for f in roads.getFeatures()), [-1.0, 50.0, 50.0])

    def test_matrix_cannot_cross_a_closed_segment(self):
        _roads([50.0, -1.0, 50.0])
        _origin()
        dest = QgsVectorLayer("Point?crs=EPSG:4326&field=name:string", "dest", "memory")
        f = QgsFeature(dest.fields())
        f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(LON0 + 3 * lon_offset(LAT, SEGMENT_M), LAT)))
        f.setAttributes(["far"])
        dest.dataProvider().addFeatures([f])
        QgsProject.instance().addMapLayer(dest)
        res = self.lt.travel_time_matrix("origin", "dest", "roads", speed_field="speed")
        self.assertIn("matrix", res, res)
        self.assertEqual(res.get("closed_segments_removed"), 1)
        self.assertEqual(res["unreachable_count"], 1)


if __name__ == "__main__":
    unittest.main()
