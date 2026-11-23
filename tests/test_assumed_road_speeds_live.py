"""HU-3b option B in real QGIS (written without a QGIS install; CI's live job is its first execution): a 'fastest' run with no usable road speeds uses assumed speeds
by road class on an in-memory copy, says so in the result, and leaves the user's layer alone.

Scene (EPSG:4326, lat 31.95): an origin in the middle of a 20 km east-west road. West half is a motorway (assumed 100 km/h), east half is residential (assumed 40 km/h).
With a flat 50 km/h, 0.06 h reaches 3 km each way (6 km of road); with the class speeds it reaches 6 km of motorway and 2.4 km of residential (8.4 km); a 60 km/h speed field reaches 7.2 km."""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from qgis.core import (
        QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsFeature, QgsGeometry, QgsPointXY, QgsProject, QgsVectorLayer,
    )
    from tests.test_network_units_live import _STATE, _boot, lon_offset
    QGIS_LIVE_AVAILABLE = True
except ImportError:
    QGIS_LIVE_AVAILABLE = False

LAT, LON0 = 31.95, 35.85
HALF_M = 10000


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "needs real qgis.core bindings -- run from an OSGeo4W/QGIS Python")
class TestAssumedRoadSpeeds(unittest.TestCase):
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
        self.mid = LON0 + lon_offset(LAT, HALF_M)
        self.end = self.mid + lon_offset(LAT, HALF_M)

    def roads(self, class_field="fclass", extra_field=None, extra_value=None):
        fields = "field=name:string" + (f"&field={class_field}:string" if class_field else "") + (f"&field={extra_field}:double" if extra_field else "")
        lyr = QgsVectorLayer(f"LineString?crs=EPSG:4326&{fields}", "roads", "memory")
        feats = []
        for (a, b), road_class in (((LON0, self.mid), "motorway"), ((self.mid, self.end), "residential")):
            f = QgsFeature(lyr.fields())
            f.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(a, LAT), QgsPointXY(b, LAT)]))
            attrs = ["road"]
            if class_field:
                attrs.append(road_class)
            if extra_field:
                attrs.append(extra_value)
            f.setAttributes(attrs)
            feats.append(f)
        lyr.dataProvider().addFeatures(feats)
        QgsProject.instance().addMapLayer(lyr)
        return lyr

    def points(self, name, lons):
        lyr = QgsVectorLayer("Point?crs=EPSG:4326&field=name:string", name, "memory")
        feats = []
        for i, lon in enumerate(lons):
            f = QgsFeature(lyr.fields())
            f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(lon, LAT)))
            f.setAttributes([f"p{i}"])
            feats.append(f)
        lyr.dataProvider().addFeatures(feats)
        QgsProject.instance().addMapLayer(lyr)
        return lyr

    @staticmethod
    def metres_of(layer):
        xf = QgsCoordinateTransform(layer.crs(), _STATE["wgs"], QgsProject.instance())
        total = 0.0
        for feat in layer.getFeatures():
            g = QgsGeometry(feat.geometry())
            g.transform(xf)
            total += _STATE["da"].measureLength(g)
        return total

    def reached(self, sa):
        self.assertTrue(sa.get("layers_created"), sa)
        return self.metres_of(QgsProject.instance().mapLayersByName(sa["layers_created"][0])[0])

    def test_service_area_uses_class_speeds_says_so_and_leaves_the_layer_alone(self):
        roads = self.roads()
        fields_before = [f.name() for f in roads.fields()]
        self.points("origin", [self.mid])
        sa = self.lt.calculate_service_area("origin", "roads", 0.06, strategy="fastest", default_speed=50)
        self.assertAlmostEqual(self.reached(sa) / 8400.0, 1.0, delta=0.03)
        self.assertTrue(any("ASSUMED speeds by road class" in n for n in sa.get("notes", [])), sa.get("notes"))
        self.assertEqual([f.name() for f in roads.fields()], fields_before)         # the user's layer was not written to
        self.assertEqual(len(QgsProject.instance().mapLayersByName("roads")), 1)    # and no copy was added to the project

    def test_without_a_class_field_the_flat_default_is_unchanged(self):
        self.roads(class_field=None)
        self.points("origin", [self.mid])
        sa = self.lt.calculate_service_area("origin", "roads", 0.06, strategy="fastest", default_speed=50)
        self.assertAlmostEqual(self.reached(sa) / 6000.0, 1.0, delta=0.03)
        self.assertFalse(any("ASSUMED" in n for n in sa.get("notes", [])))

    def test_a_usable_speed_field_wins_over_the_class_speeds(self):
        self.roads(extra_field="kmh", extra_value=60.0)
        self.points("origin", [self.mid])
        sa = self.lt.calculate_service_area("origin", "roads", 0.06, strategy="fastest", default_speed=50, speed_field="kmh")
        self.assertAlmostEqual(self.reached(sa) / 7200.0, 1.0, delta=0.03)           # 60 km/h x 0.06 h = 3.6 km each way
        self.assertFalse(any("ASSUMED" in n for n in sa.get("notes", [])))

    def test_a_shortest_run_ignores_class_speeds(self):
        self.roads()
        self.points("origin", [self.mid])
        sa = self.lt.calculate_service_area("origin", "roads", 1000, strategy="shortest")
        self.assertAlmostEqual(self.reached(sa) / 2000.0, 1.0, delta=0.03)
        self.assertFalse(any("ASSUMED" in n for n in sa.get("notes", [])))

    def test_travel_time_matrix_uses_class_speeds_and_carries_the_assumption(self):
        self.roads()
        self.points("origin", [self.mid])
        self.points("dest", [self.mid + lon_offset(LAT, 8000)])
        tm = self.lt.travel_time_matrix("origin", "dest", "roads", strategy="fastest", default_speed=50)
        cost = float(next(iter(next(iter(tm["matrix"].values())).values())))
        self.assertAlmostEqual(cost, 8.0 / 40.0, delta=0.01)                         # 8 km of residential at 40 km/h, not 8 km at 50
        self.assertIn("ASSUMED speeds by road class", tm.get("speed_assumption", ""))

    def test_the_delivery_route_uses_class_speeds_and_carries_the_assumption(self):
        self.roads()
        self.points("stops", [self.mid, self.mid + lon_offset(LAT, 8000)])
        res = self.lt.optimize_delivery_route("stops", road_network_layer="roads", strategy="fastest", default_speed=50)
        self.assertTrue(res.get("success"), res)
        self.assertAlmostEqual(res["total_travel_time_hours"], 8.0 / 40.0, delta=0.01)
        self.assertIn("ASSUMED speeds by road class", res.get("speed_assumption", ""))


if __name__ == "__main__":
    unittest.main()
