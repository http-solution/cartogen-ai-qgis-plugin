"""PLAN-012 live check (real QGIS, run by the qgis-live-tests CI job; written without a QGIS install, so CI's first run is its first execution).

Item 1: obfuscate_sensitive_points on a MultiPoint layer. Hypothesis from reading the code: `geom.asPoint()` returns an empty point for a
MultiPoint, so every output lands near (0, 0). This file is first pushed WITHOUT the fix to show the hypothesis on a real QGIS; a pass on
that first run would withdraw the item."""
import unittest

try:
    from qgis.core import QgsFeature, QgsGeometry, QgsProject, QgsVectorLayer
    LIVE = True
except ImportError:
    LIVE = False


def _multipoint_layer():
    layer = QgsVectorLayer("MultiPoint?crs=EPSG:32638&field=id:integer", "mp_sensitive", "memory")
    rows = [("MULTIPOINT((500000 1650000),(500400 1650300))", 1), ("MULTIPOINT((501000 1651000))", 2)]
    features = []
    for wkt, ident in rows:
        f = QgsFeature(layer.fields())
        f.setGeometry(QgsGeometry.fromWkt(wkt))
        f.setAttributes([ident])
        features.append(f)
    layer.dataProvider().addFeatures(features)
    layer.updateExtents()
    return layer


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestObfuscateMultiPoint(unittest.TestCase):
    def setUp(self):
        from tests.test_network_units_live import _boot
        why = _boot()
        if why:
            self.skipTest(why)
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        QgsProject.instance().addMapLayer(_multipoint_layer())

    def _out_points(self, method, **kw):
        from cartogen_ai.core.agent.tools.vector_tools import obfuscate_sensitive_points
        res = obfuscate_sensitive_points("mp_sensitive", method, output_layer_name="mp_out", seed=1, **kw)
        self.assertTrue(res.get("success"), res)
        out = QgsProject.instance().mapLayersByName("mp_out")[0]
        return res, [(f.geometry().asPoint().x(), f.geometry().asPoint().y(), f["id"]) for f in out.getFeatures()]

    def test_jitter_keeps_every_part_near_where_it_was(self):
        res, points = self._out_points("jitter", radius=100)
        print(f"PLAN012 multipoint jitter -> {points}")
        self.assertEqual(res["feature_count"], 3, res)                      # one output point per part (owner decision)
        for x, y, _ident in points:
            self.assertGreater(x, 499000, points)                           # not collapsed to (0, 0)
            self.assertGreater(y, 1649000, points)

    def test_grid_snap_keeps_every_part_near_where_it_was(self):
        res, points = self._out_points("grid_snap", cell_size=1000)
        self.assertEqual(res["feature_count"], 3, res)
        for x, _y, _ident in points:
            self.assertGreater(x, 499000, points)

    def test_attributes_follow_each_part(self):
        _res, points = self._out_points("jitter", radius=10)
        self.assertEqual(sorted(i for _x, _y, i in points), [1, 1, 2])


if __name__ == "__main__":
    unittest.main()
