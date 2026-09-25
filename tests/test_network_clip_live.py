# -*- coding: utf-8 -*-
"""Clipping the road network to what a service area can reach is EXACT (real QGIS).

BUG-2026-09-25-2: routing builds a graph from every road in the layer (about 0.6-1 ms per road; 331 s
for a one-hour service area on the 161,041 roads of Jordan). Nothing reachable within cost R is farther
than R in a straight line from the start, so calculate_service_area routes only over the roads that can
matter. A clip that changed the answer would be worse than being slow, so every case here compares the
clipped result with the full-network result geometry for geometry, across network CRSs, strategies,
speed fields, multi-band and multi-facility requests, and the cases where the clip must step aside
(no road in reach, reach larger than the network, unknown maximum speed).

Needs real qgis.core + the Processing plugin (skipped otherwise)."""
import unittest
from unittest.mock import patch

from tests.test_network_units_live import QGIS_LIVE_AVAILABLE, _boot

if QGIS_LIVE_AVAILABLE:
    from qgis.core import (
        QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsFeature, QgsField, QgsGeometry, QgsPointXY,
        QgsProject, QgsVectorLayer,
    )
    from qgis.PyQt.QtCore import QMetaType

WGS_ID = "EPSG:4326"
LAT, LON0 = 31.95, 35.85
SPAN = 0.2


def _xf(crs_id):
    return QgsCoordinateTransform(QgsCoordinateReferenceSystem(WGS_ID), QgsCoordinateReferenceSystem(crs_id),
                                  QgsProject.instance())


def _grid(crs_id, n, only_rows=None, name="roads"):
    """n horizontal + n vertical lines over a 0.2 degree (~20 km) square with a vertex at EVERY
    crossing, so every crossing is a real junction of the routing graph (the graph connects lines only
    at shared vertices: with sparser vertices the "network" degenerates into a few long roads, and a
    wrong clip can't be told from a right one). Each line has a `speed` attribute (30..90 km/h).
    `only_rows` keeps just the first rows/columns: a network covering only one corner."""
    xf = _xf(crs_id)
    lyr = QgsVectorLayer("LineString?crs=%s" % crs_id, name, "memory")
    lyr.dataProvider().addAttributes([QgsField("speed", QMetaType.Type.Double)])
    lyr.updateFields()
    step = SPAN / n
    feats, k = [], 0
    rows = range(n + 1) if only_rows is None else range(only_rows)
    for i in rows:
        for horizontal in (True, False):
            pts = [xf.transform(QgsPointXY(LON0 + j * step, LAT + i * step)) if horizontal else
                   xf.transform(QgsPointXY(LON0 + i * step, LAT + j * step)) for j in range(n + 1)]
            f = QgsFeature(lyr.fields())
            f.setGeometry(QgsGeometry.fromPolylineXY(pts))
            f.setAttributes([30.0 + (k * 7) % 61])
            feats.append(f)
            k += 1
    lyr.dataProvider().addFeatures(feats)
    QgsProject.instance().addMapLayer(lyr)
    return lyr


def _origins(crs_id, lonlats, name="origin"):
    xf = _xf(crs_id)
    lyr = QgsVectorLayer("Point?crs=%s&field=id:int" % crs_id, name, "memory")
    feats = []
    for lon, lat in lonlats:
        f = QgsFeature(lyr.fields())
        f.setGeometry(QgsGeometry.fromPointXY(xf.transform(QgsPointXY(lon, lat))))
        feats.append(f)
    lyr.dataProvider().addFeatures(feats)
    QgsProject.instance().addMapLayer(lyr)
    return lyr


CENTRE = (LON0 + SPAN / 2, LAT + SPAN / 2)


def _no_clip(network, centre, reach):
    return network, {"applied": False}


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "needs real qgis.core bindings -- run from an OSGeo4W/QGIS Python")
class TestClippingIsExact(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        why = _boot()
        if why:
            raise unittest.SkipTest(why)
        from cartogen_ai.core.agent.tools import logistics_tools as lt
        cls.lt = lt

    def setUp(self):
        QgsProject.instance().clear()
        QgsProject.instance().setCrs(QgsCoordinateReferenceSystem("EPSG:3857"))
        QgsProject.instance().setEllipsoid("NONE")
        self.addCleanup(QgsProject.instance().clear)

    def outcome(self, result):
        """The service-area lines as a sorted list of rounded WKT: identical means identical geometry."""
        self.assertTrue(result.get("success"), result)
        lines = [QgsProject.instance().mapLayersByName(n)[0] for n in result["layers_created"] if "_lines_" in n]
        wkts = sorted(f.geometry().asWkt(6) for lyr in lines for f in lyr.getFeatures())
        return wkts

    def run_both(self, **kw):
        """(clipped result, full-network result) for the same request. BACKGROUND_MIN_FEATURES is lowered
        so these small grids are eligible for clipping at all (the production threshold is 2,000 roads)."""
        with patch.object(self.lt, "BACKGROUND_MIN_FEATURES", 1):
            clipped = self.lt.calculate_service_area("origin", "roads", **kw)
            clipped_out = self.outcome(clipped)
            QgsProject.instance().removeMapLayers([lyr.id() for lyr in QgsProject.instance().mapLayers().values()
                                                   if "service_area" in lyr.name()])
            with patch.object(self.lt, "_clip_network_to_reach", side_effect=_no_clip):
                full = self.lt.calculate_service_area("origin", "roads", **kw)
            full_out = self.outcome(full)
        return clipped, clipped_out, full, full_out

    # ------------------------------------------------------------------------------------------------

    def test_same_geometry_as_the_full_network_in_every_network_crs(self):
        for crs in ("EPSG:4326", "EPSG:3857", "EPSG:32636"):
            for reach in (300, 900):
                with self.subTest(network=crs, reach_m=reach):
                    QgsProject.instance().clear()
                    _grid(crs, 100)
                    _origins(crs, [CENTRE])
                    clipped, a, _, b = self.run_both(travel_cost=reach)
                    self.assertTrue(a, "empty service area")
                    self.assertEqual(a, b)
                    info = clipped.get("network_clipping")
                    self.assertIsNotNone(info, "the clip should have applied on a 20 km network with a %d m reach" % reach)
                    self.assertLess(info["roads_routed_max"], info["roads_full"])

    def test_origin_layer_in_another_crs_than_the_network(self):
        _grid("EPSG:4326", 100)
        _origins("EPSG:3857", [CENTRE])
        clipped, a, _, b = self.run_both(travel_cost=600)
        self.assertEqual(a, b)
        self.assertTrue(clipped.get("network_clipping"))

    def test_fastest_with_a_speed_field_uses_the_networks_top_speed_for_the_reach(self):
        _grid("EPSG:4326", 100)
        _origins("EPSG:4326", [CENTRE])
        # 0.02 h at up to 90 km/h is up to 1.8 km: the clip must be sized by the FASTEST road, not 50 km/h
        clipped, a, _, b = self.run_both(travel_cost=0.02, strategy="fastest", speed_field="speed", default_speed=50)
        self.assertEqual(a, b)
        self.assertTrue(clipped.get("network_clipping"))
        self.assertGreater(len(a), 0)

    def test_fastest_default_speed_only(self):
        _grid("EPSG:3857", 100)
        _origins("EPSG:3857", [CENTRE])
        clipped, a, _, b = self.run_both(travel_cost=0.015, strategy="fastest", default_speed=40)
        self.assertEqual(a, b)
        self.assertTrue(clipped.get("network_clipping"))

    def test_several_facilities_and_several_bands(self):
        _grid("EPSG:4326", 100)
        _origins("EPSG:4326", [CENTRE, (LON0 + 0.05, LAT + 0.05), (LON0 + 0.15, LAT + 0.12)])
        clipped, a, _, b = self.run_both(travel_cost=[300, 700])
        self.assertEqual(a, b)
        self.assertEqual(clipped["network_clipping"]["facilities_clipped"], 3)

    def test_a_start_off_the_road_snaps_the_same_way(self):
        # roads only in one corner of the square; the origin is ~9 km from them, farther than the reach:
        # QGIS snaps to the nearest road however far. Clipping must not change that.
        _grid("EPSG:4326", 100, only_rows=8)
        _origins("EPSG:4326", [(LON0 + 0.15, LAT + 0.15)])
        clipped, a, _, b = self.run_both(travel_cost=800)
        self.assertEqual(a, b)
        self.assertIsNone(clipped.get("network_clipping"), "no road within reach: the whole network must be used")

    def test_a_reach_larger_than_the_network_uses_the_whole_network(self):
        _grid("EPSG:4326", 100)
        _origins("EPSG:4326", [CENTRE])
        clipped, a, _, b = self.run_both(travel_cost=30000)
        self.assertEqual(a, b)
        self.assertIsNone(clipped.get("network_clipping"))

    def test_an_unreadable_top_speed_means_no_clip_not_a_guess(self):
        _grid("EPSG:4326", 100)
        _origins("EPSG:4326", [CENTRE])
        with patch.object(self.lt, "_max_speed_in_field", return_value=None):
            clipped, a, _, b = self.run_both(travel_cost=0.02, strategy="fastest", speed_field="speed")
        self.assertEqual(a, b)
        self.assertIsNone(clipped.get("network_clipping"))

    def test_small_networks_are_left_alone_at_the_production_threshold(self):
        _grid("EPSG:4326", 100)
        _origins("EPSG:4326", [CENTRE])
        res = self.lt.calculate_service_area("origin", "roads", 300)      # 200 roads < 2,000
        self.assertTrue(res.get("success"))
        self.assertIsNone(res.get("network_clipping"))


if __name__ == "__main__":
    unittest.main()

