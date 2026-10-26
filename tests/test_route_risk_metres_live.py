"""Live QGIS: score_route_incident_risk buffers a lat/lon route by real metres (1.18.2 hand test C9, 2026-10-26: 500 was applied as
500 degrees on EPSG:4326, so every incident counted as near). Written without a local QGIS: CI's first run is its first execution."""
import unittest

try:
    from qgis.core import QgsFeature, QgsGeometry, QgsPointXY, QgsProject, QgsVectorLayer
    LIVE = True
except ImportError:
    LIVE = False

LON, LAT = 45.0, 12.8


def _layer(kind, name, fields, geoms):
    layer = QgsVectorLayer(f"{kind}?crs=EPSG:4326&{fields}", name, "memory")
    for geom, attrs in geoms:
        f = QgsFeature(layer.fields())
        f.setGeometry(geom)
        f.setAttributes(attrs)
        layer.dataProvider().addFeatures([f])
    layer.updateExtents()
    QgsProject.instance().addMapLayer(layer)
    return layer


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestRouteRiskUsesMetres(unittest.TestCase):
    def setUp(self):
        from tests.test_network_units_live import _boot
        why = _boot()
        if why:
            self.skipTest(why)
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        line = QgsGeometry.fromPolylineXY([QgsPointXY(LON, LAT), QgsPointXY(LON + 0.1, LAT)])
        _layer("LineString", "route", "field=name:string", [(line, ["r"])])
        # ~100 m north of the route, ~2 km north, ~8 km north (0.001 deg of latitude is about 111 m)
        pts = [(QgsGeometry.fromPointXY(QgsPointXY(LON + 0.05, LAT + dy)), [i]) for i, dy in enumerate((0.0009, 0.018, 0.072))]
        _layer("Point", "incidents", "field=n:integer", pts)

    def test_500_m_catches_only_the_100_m_incident(self):
        from cartogen_ai.core.agent.tools.logistics_tools import score_route_incident_risk
        res = score_route_incident_risk("route", "incidents", 500)
        self.assertTrue(res.get("success"), res)
        self.assertEqual(res["incident_count"], 1)
        self.assertLess(res["incidents"][0]["distance_to_route_m"], 200)
        self.assertNotIn("DEGREES", str(res.get("warning", "")))

    def test_2500_m_catches_two(self):
        from cartogen_ai.core.agent.tools.logistics_tools import score_route_incident_risk
        res = score_route_incident_risk("route", "incidents", 2500)
        self.assertEqual(res["incident_count"], 2)
        self.assertTrue(QgsProject.instance().mapLayersByName("route_buffer_2500"))


if __name__ == "__main__":
    unittest.main()
