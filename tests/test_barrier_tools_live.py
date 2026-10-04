# -*- coding: utf-8 -*-
"""Live-QGIS tests for H1 apply_network_barriers. Written without a QGIS install: CI's first run is their first execution."""
import unittest

try:
    from qgis.core import (QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsFeature, QgsGeometry, QgsPointXY,
                           QgsProject, QgsVectorLayer)
    QGIS_LIVE_AVAILABLE = True
except ImportError:
    QGIS_LIVE_AVAILABLE = False


def _boot_qgis():
    from tests.test_chat_widget_live import _boot_qgis as _shared_boot
    return _shared_boot()


def _roads():
    layer = QgsVectorLayer("LineString?crs=EPSG:4326&field=speed:double", "roads", "memory")
    rows = [("LINESTRING(44.000 15.000, 44.010 15.000)", 60.0),    # A: the barrier sits on it
            ("LINESTRING(44.000 15.010, 44.010 15.010)", 60.0),    # B: about 1.1 km north of A
            ("LINESTRING(44.000 15.020, 44.010 15.020)", None)]    # C: far, and no speed value
    feats = []
    for wkt, speed in rows:
        f = QgsFeature(layer.fields())
        f.setGeometry(QgsGeometry.fromWkt(wkt))
        f.setAttributes([speed])
        feats.append(f)
    layer.dataProvider().addFeatures(feats)
    layer.updateExtents()
    return layer


def _barrier_point(crs="EPSG:4326"):
    layer = QgsVectorLayer(f"Point?crs={crs}&field=name:string", "bridge", "memory")
    pt = QgsPointXY(44.005, 15.0)
    if crs != "EPSG:4326":
        pt = QgsCoordinateTransform(QgsCoordinateReferenceSystem("EPSG:4326"), QgsCoordinateReferenceSystem(crs),
                                    QgsProject.instance()).transform(pt)
    f = QgsFeature(layer.fields())
    f.setGeometry(QgsGeometry.fromPointXY(pt))
    layer.dataProvider().addFeatures([f])
    layer.updateExtents()
    return layer


def _speeds(layer, field):
    return [f[field] for f in sorted(layer.getFeatures(), key=lambda x: x.id())]


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "requires real QGIS")
class TestApplyNetworkBarriers(unittest.TestCase):
    def setUp(self):
        _boot_qgis()
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)

    def _run(self, barrier, **kw):
        from cartogen_ai.core.agent.tools.barrier_tools import apply_network_barriers
        roads = _roads()
        QgsProject.instance().addMapLayer(roads)
        QgsProject.instance().addMapLayer(barrier)
        return roads, apply_network_barriers("roads", barrier.name(), **kw)

    def test_block_only_touches_the_road_near_the_barrier(self):
        roads, res = self._run(_barrier_point(), buffer_m=50, speed_field="speed")
        self.assertTrue(res.get("success"), res)
        self.assertEqual(res["segments_affected"], 1)
        a, b, c = _speeds(roads, "barrier_speed")
        self.assertEqual(a, 0.1)
        self.assertEqual(b, 60.0)
        self.assertEqual(c, 30.0)          # no speed value -> the default
        self.assertIn("warning", res)

    def test_penalise_multiplies_the_base_speed(self):
        roads, res = self._run(_barrier_point(), buffer_m=50, mode="penalise", penalty_factor=0.5, speed_field="speed")
        self.assertTrue(res.get("success"), res)
        self.assertEqual(_speeds(roads, "barrier_speed")[0], 30.0)

    def test_a_barrier_in_another_crs_lands_in_the_same_place(self):
        roads, res = self._run(_barrier_point("EPSG:3857"), buffer_m=50, speed_field="speed")
        self.assertTrue(res.get("success"), res)
        self.assertEqual(res["segments_affected"], 1)

    def test_a_larger_buffer_reaches_the_next_road_and_a_tiny_one_misses(self):
        _roads_layer, res = self._run(_barrier_point(), buffer_m=1500, speed_field="speed")
        self.assertEqual(res["segments_affected"], 2)

    def test_a_polygon_barrier_blocks_the_roads_it_covers(self):
        poly = QgsVectorLayer("Polygon?crs=EPSG:4326&field=name:string", "flood", "memory")
        f = QgsFeature(poly.fields())
        f.setGeometry(QgsGeometry.fromWkt("POLYGON((43.999 14.999, 44.011 14.999, 44.011 15.011, 43.999 15.011, 43.999 14.999))"))
        poly.dataProvider().addFeatures([f])
        poly.updateExtents()
        _roads_layer, res = self._run(poly, buffer_m=0, speed_field="speed")
        self.assertEqual(res["segments_affected"], 2)    # A and B inside, C outside

    def test_the_original_speed_field_is_left_alone(self):
        roads, _res = self._run(_barrier_point(), buffer_m=50, speed_field="speed")
        self.assertEqual(_speeds(roads, "speed")[:2], [60.0, 60.0])

    def test_unknown_layer_and_bad_mode_are_errors_that_change_nothing(self):
        from cartogen_ai.core.agent.tools.barrier_tools import apply_network_barriers
        roads = _roads()
        QgsProject.instance().addMapLayer(roads)
        self.assertIn("error", apply_network_barriers("roads", "ghost"))
        QgsProject.instance().addMapLayer(_barrier_point())
        self.assertIn("error", apply_network_barriers("roads", "bridge", mode="close"))
        self.assertLess(roads.fields().indexOf("barrier_speed"), 0)


if __name__ == "__main__":
    unittest.main()
