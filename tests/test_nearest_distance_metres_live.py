"""Live QGIS: find_nearest_features gives real metres for a latitude/longitude layer (self-audit round 2, 2026-10-26: native:joinbynearest
writes 'distance' in the layer's CRS units, so the tool's "distance in meters" was degrees on EPSG:4326). Written without a local QGIS:
CI's first run is its first execution."""
import unittest

try:
    from qgis.core import QgsFeature, QgsGeometry, QgsPointXY, QgsProject, QgsVectorLayer
    LIVE = True
except ImportError:
    LIVE = False


def _points(name, coords):
    layer = QgsVectorLayer(f"Point?crs={coords[0]}&field=n:integer", name, "memory")
    for i, (x, y) in enumerate(coords[1]):
        f = QgsFeature(layer.fields())
        f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(x, y)))
        f.setAttributes([i])
        layer.dataProvider().addFeatures([f])
    layer.updateExtents()
    QgsProject.instance().addMapLayer(layer)


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestNearestInMetres(unittest.TestCase):
    def setUp(self):
        from tests.test_network_units_live import _boot
        why = _boot()
        if why:
            self.skipTest(why)
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)

    def test_latlon_layers_get_distance_m_close_to_the_real_distance(self):
        from cartogen_ai.core.agent.tools.vector_tools import find_nearest_features
        _points("villages", ("EPSG:4326", [(45.0, 12.8)]))
        _points("clinics", ("EPSG:4326", [(45.0, 12.81), (46.0, 13.0)]))   # 0.01 degree of latitude is about 1,106 m
        res = find_nearest_features("villages", "clinics")
        self.assertTrue(res.get("success"), res)
        out = QgsProject.instance().mapLayersByName(res["layer_name"])[0]
        feat = next(iter(out.getFeatures()))
        self.assertAlmostEqual(feat["distance"], 0.01, places=4)       # degrees: the raw field
        self.assertAlmostEqual(feat["distance_m"], 1105.7, delta=15)   # metres
        self.assertIn("distance_note", res)

    def test_a_metre_crs_is_left_alone(self):
        from cartogen_ai.core.agent.tools.vector_tools import find_nearest_features
        _points("a", ("EPSG:32638", [(500000.0, 1400000.0)]))
        _points("b", ("EPSG:32638", [(500300.0, 1400400.0)]))
        res = find_nearest_features("a", "b")
        out = QgsProject.instance().mapLayersByName(res["layer_name"])[0]
        self.assertNotIn("distance_m", [f.name() for f in out.fields()])
        self.assertAlmostEqual(next(iter(out.getFeatures()))["distance"], 500.0, delta=1)


if __name__ == "__main__":
    unittest.main()
