# -*- coding: utf-8 -*-
"""The network tools (service area, travel-time matrix, delivery route) work in real metres, in real QGIS.

Live-reported 2026-09-24/25 ("Health facilities beyond one hour's travel", Amman) and measured
2026-09-25 on a road of known length: calculate_service_area built a bare QgsProcessingContext with
no ellipsoid, so travel_cost was in layer units -- on a lat/long layer a 1000 m service area covered
the whole 10 km network -- and on Web Mercator it was inflated (about 15% short at Amman, worse
further from the equator). The other tools used the project's ellipsoid and were right only if the
project happened to have one. Start points were also read in the NETWORK's CRS even when they came
from a layer in another one. See BUG-2026-09-24-5 in docs/BUG_TRACKER.md.

Needs real qgis.core + the Processing plugin (skipped otherwise). Ground truth for every distance
is measured on the WGS84 ellipsoid from the original lat/lon points, independent of the layer CRS."""
import math
import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    import qgis
    from qgis.core import (
        QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsDistanceArea, QgsFeature,
        QgsGeometry, QgsPointXY, QgsProject, QgsVectorLayer,
    )
    # `processing` lives in <qgis python dir>/plugins, which plain PyQGIS scripts don't put on the
    # path (QGIS itself does). Must happen before the plugin's tool modules are first imported,
    # because they decide QGIS_AVAILABLE once, at import time, by importing `processing`.
    _plugins = os.path.join(os.path.dirname(os.path.dirname(qgis.__file__)), "plugins")
    if os.path.isdir(_plugins) and _plugins not in sys.path:
        sys.path.append(_plugins)
    QGIS_LIVE_AVAILABLE = True
except ImportError:
    QGIS_LIVE_AVAILABLE = False

WGS = None
_DA = None
_PROCESSING_READY = None


def _boot():
    """One QgsApplication per process (test_chat_widget_live's, when both run in the same process)
    plus an initialised Processing framework. Returns None if ready, else why it isn't."""
    global WGS, _DA, _PROCESSING_READY
    if _PROCESSING_READY is not None:
        return _PROCESSING_READY
    from tests.test_chat_widget_live import _boot_qgis
    _boot_qgis()
    try:
        from processing.core.Processing import Processing
        Processing.initialize()
    except Exception as e:
        _PROCESSING_READY = "the Processing plugin isn't importable here (%s)" % e
        return _PROCESSING_READY
    from cartogen_ai.core.agent.tools import logistics_tools as lt
    if not lt.QGIS_AVAILABLE:
        _PROCESSING_READY = "logistics_tools was imported before `processing` was importable"
        return _PROCESSING_READY
    WGS = QgsCoordinateReferenceSystem("EPSG:4326")
    _DA = QgsDistanceArea()
    _DA.setSourceCrs(WGS, QgsProject.instance().transformContext())
    _DA.setEllipsoid("WGS84")
    _PROCESSING_READY = ""
    return _PROCESSING_READY


def metres_between(lon_a, lat_a, lon_b, lat_b):
    return _DA.measureLine(QgsPointXY(lon_a, lat_a), QgsPointXY(lon_b, lat_b))


def lon_offset(lat, metres):
    return metres / (111320.0 * math.cos(math.radians(lat)))


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "needs real qgis.core bindings -- run from an OSGeo4W/QGIS Python")
class _Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        why = _boot()
        if why:
            raise unittest.SkipTest(why)
        from cartogen_ai.core.agent.tools import logistics_tools as lt
        cls.lt = lt

    def setUp(self):
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)

    def layer(self, kind, crs_id, name, lonlat_pts, project_crs="EPSG:3857"):
        """A memory layer in crs_id built from lon/lat truth points (transformed into that CRS)."""
        crs = QgsCoordinateReferenceSystem(crs_id)
        xf = QgsCoordinateTransform(WGS, crs, QgsProject.instance())
        pts = [xf.transform(QgsPointXY(lon, lat)) for lon, lat in lonlat_pts]
        lyr = QgsVectorLayer("%s?crs=%s&field=name:string" % (kind, crs_id), name, "memory")
        f = QgsFeature(lyr.fields())
        if kind == "LineString":
            f.setGeometry(QgsGeometry.fromPolylineXY(pts))
            f.setAttributes(["road"])
            lyr.dataProvider().addFeatures([f])
        else:
            feats = []
            for i, p in enumerate(pts):
                g = QgsFeature(lyr.fields())
                g.setGeometry(QgsGeometry.fromPointXY(p))
                g.setAttributes(["p%d" % i])
                feats.append(g)
            lyr.dataProvider().addFeatures(feats)
        QgsProject.instance().addMapLayer(lyr)
        return lyr

    def set_project(self, crs="EPSG:3857", ellipsoid="NONE"):
        QgsProject.instance().setCrs(QgsCoordinateReferenceSystem(crs))
        QgsProject.instance().setEllipsoid(ellipsoid)

    @staticmethod
    def metres_of(layer):
        xf = QgsCoordinateTransform(layer.crs(), WGS, QgsProject.instance())
        total = 0.0
        for feat in layer.getFeatures():
            g = QgsGeometry(feat.geometry())
            g.transform(xf)
            total += _DA.measureLength(g)
        return total

    def first_cost(self, matrix_result):
        self.assertIn("matrix", matrix_result, matrix_result)
        return float(list(list(matrix_result["matrix"].values())[0].values())[0])


SITES = [("Amman 32N", 31.95, 35.85), ("Arctic 70N", 70.0, 25.0), ("Far north 80N", 80.0, 25.0)]


class TestCostsAreRealMetres(_Base):
    """A 10 km east-west road; origin in the middle; destination 4 km east of it."""

    def _scene(self, lat, lon0, network_crs, origin_crs=None):
        lon1 = lon0 + lon_offset(lat, 10000)
        mid = (lon0 + lon1) / 2
        dest = mid + lon_offset(lat, 4000)
        road = self.layer("LineString", network_crs, "roads", [(lon0, lat), (lon1, lat)])
        org = self.layer("Point", origin_crs or network_crs, "origin", [(mid, lat)])
        dst = self.layer("Point", origin_crs or network_crs, "dest", [(dest, lat)])
        return road, org, dst, metres_between(mid, lat, dest, lat)

    def test_shortest_costs_are_metres_in_every_crs_ellipsoid_setting_and_latitude(self):
        for label, lat, lon0 in SITES:
            for crs in ("EPSG:4326", "EPSG:3857", "EPSG:32636"):
                for ellipsoid in ("NONE", "EPSG:7030"):
                    with self.subTest(site=label, network=crs, project_ellipsoid=ellipsoid):
                        QgsProject.instance().clear()
                        self.set_project(ellipsoid=ellipsoid)
                        _, _, _, truth = self._scene(lat, lon0, crs)
                        sa = self.lt.calculate_service_area("origin", "roads", 1000)
                        self.assertTrue(sa.get("layers_created"), sa)
                        reached = self.metres_of(QgsProject.instance().mapLayersByName(sa["layers_created"][0])[0])
                        # 1000 m each way along the road = 2000 m of road reached
                        self.assertAlmostEqual(reached / 2000.0, 1.0, delta=0.01, msg="reached %.0f m" % reached)
                        tm = self.lt.travel_time_matrix("origin", "dest", "roads")
                        self.assertAlmostEqual(self.first_cost(tm) / truth, 1.0, delta=0.003)
                        # the units are also stated in the results, so the model can't misreport them
                        self.assertEqual(sa["travel_cost_unit"], "meters")
                        self.assertEqual(tm["cost_unit"], "meters")

    def test_fastest_costs_are_hours(self):
        for label, lat, lon0 in SITES[:2]:
            for crs in ("EPSG:4326", "EPSG:3857"):
                with self.subTest(site=label, network=crs):
                    QgsProject.instance().clear()
                    self.set_project()
                    _, _, _, truth = self._scene(lat, lon0, crs)
                    tm = self.lt.travel_time_matrix("origin", "dest", "roads", strategy="fastest", default_speed=50)
                    self.assertAlmostEqual(self.first_cost(tm), truth / 50000.0, delta=truth / 50000.0 * 0.005)
                    # 0.04 h at 50 km/h is 2 km, so it reaches 2 km each way = 4 km of road
                    sa = self.lt.calculate_service_area("origin", "roads", 0.04, strategy="fastest", default_speed=50)
                    reached = self.metres_of(QgsProject.instance().mapLayersByName(sa["layers_created"][0])[0])
                    self.assertAlmostEqual(reached / 4000.0, 1.0, delta=0.01, msg="reached %.0f m" % reached)
                    self.assertEqual(tm["cost_unit"], "hours")
                    self.assertEqual(sa["travel_cost_unit"], "hours")


class TestOriginInADifferentCrsThanTheNetwork(_Base):
    """The reported request typed the origin as Web Mercator metres (3999682,3756232) while the roads
    were downloaded as lat/long. A bare "x,y" start point is read in the NETWORK's CRS."""

    LAT, LON0 = 31.95, 35.85

    def _run(self, network_crs, point_crs):
        QgsProject.instance().clear()
        self.set_project()
        lon1 = self.LON0 + lon_offset(self.LAT, 10000)
        mid = (self.LON0 + lon1) / 2
        dest = mid + lon_offset(self.LAT, 4000)
        self.layer("LineString", network_crs, "roads", [(self.LON0, self.LAT), (lon1, self.LAT)])
        self.layer("Point", point_crs, "origin", [(mid, self.LAT)])
        self.layer("Point", point_crs, "dest", [(dest, self.LAT)])
        truth = metres_between(mid, self.LAT, dest, self.LAT)
        sa = self.lt.calculate_service_area("origin", "roads", 1000)
        tm = self.lt.travel_time_matrix("origin", "dest", "roads")
        return sa, tm, truth

    def test_origin_layer_crs_does_not_have_to_match_the_network(self):
        for network_crs, point_crs in (("EPSG:4326", "EPSG:3857"), ("EPSG:4326", "EPSG:32636"),
                                       ("EPSG:32636", "EPSG:4326"), ("EPSG:3857", "EPSG:4326")):
            with self.subTest(network=network_crs, points=point_crs):
                sa, tm, truth = self._run(network_crs, point_crs)
                self.assertTrue(sa.get("layers_created"), sa)
                reached = self.metres_of(QgsProject.instance().mapLayersByName(sa["layers_created"][0])[0])
                self.assertAlmostEqual(reached / 2000.0, 1.0, delta=0.01, msg="reached %.0f m" % reached)
                self.assertAlmostEqual(self.first_cost(tm) / truth, 1.0, delta=0.003)


class TestDeliveryRouteDistanceIsMetres(_Base):
    def test_network_aware_total_distance_is_metres_with_stops_in_another_crs(self):
        lat, lon0 = 31.95, 35.85
        lon1 = lon0 + lon_offset(lat, 10000)
        a, b = lon0 + lon_offset(lat, 2000), lon0 + lon_offset(lat, 7000)     # 5 km apart
        for network_crs, stops_crs in (("EPSG:4326", "EPSG:3857"), ("EPSG:32636", "EPSG:4326")):
            with self.subTest(network=network_crs, stops=stops_crs):
                QgsProject.instance().clear()
                self.set_project()
                self.layer("LineString", network_crs, "roads", [(lon0, lat), (lon1, lat)])
                self.layer("Point", stops_crs, "stops", [(a, lat), (b, lat)])
                res = self.lt.optimize_delivery_route("stops", road_network_layer="roads")
                self.assertTrue(res.get("success"), res)
                truth = metres_between(a, lat, b, lat)
                self.assertAlmostEqual(res["total_distance"] / truth, 1.0, delta=0.003)
                self.assertTrue(QgsProject.instance().mapLayersByName("stops_road_route"), "route layer built")
                self.assertEqual(res["distance_unit"], "meters")


class TestAntimeridian(_Base):
    """A road crossing 180 degrees, laid out in a Mercator centred on 150E so it is continuous there
    (in EPSG:4326 a line from 179.95 to -179.95 would be drawn the long way round the world)."""

    def test_distances_across_the_antimeridian(self):
        lat = 20.0
        road_lon0, road_lon1 = 179.95, -179.95            # ~10.5 km, crossing 180
        a, b = 179.99, -179.99                              # ~2.1 km apart, on either side
        truth = metres_between(a, lat, b, lat)
        self.assertLess(truth, 2500)                        # the short way, not ~40,000 km
        for point_crs in ("EPSG:3832", "EPSG:4326"):
            with self.subTest(points=point_crs):
                QgsProject.instance().clear()
                self.set_project(crs="EPSG:3832")
                self.layer("LineString", "EPSG:3832", "roads", [(road_lon0, lat), (road_lon1, lat)])
                self.layer("Point", point_crs, "origin", [(a, lat)])
                self.layer("Point", point_crs, "dest", [(b, lat)])
                tm = self.lt.travel_time_matrix("origin", "dest", "roads")
                self.assertAlmostEqual(self.first_cost(tm) / truth, 1.0, delta=0.01)
                sa = self.lt.calculate_service_area("origin", "roads", 1000)
                reached = self.metres_of(QgsProject.instance().mapLayersByName(sa["layers_created"][0])[0])
                self.assertAlmostEqual(reached / 2000.0, 1.0, delta=0.02, msg="reached %.0f m" % reached)


if __name__ == "__main__":
    unittest.main()
