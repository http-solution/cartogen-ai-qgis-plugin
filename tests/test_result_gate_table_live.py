"""Round-2 row E4 (2026-11-05): a table output must not get a geometry FAIL. Real QGIS (CI live job; written without a QGIS install, so CI's first run is its first execution)."""
import unittest

from tests.test_network_units_live import QGIS_LIVE_AVAILABLE, _boot

if QGIS_LIVE_AVAILABLE:
    from qgis.core import QgsFeature, QgsGeometry, QgsPointXY, QgsVectorLayer


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "needs real qgis.core bindings")
class TestTableOutputHasNoGeometryCheck(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        why = _boot()
        if why:
            raise unittest.SkipTest(why)

    def test_a_no_geometry_layer_has_no_geometry_summary(self):
        from cartogen_ai.core.agent import result_gate
        table = QgsVectorLayer("NoGeometry?field=count:integer", "stats", "memory")
        feat = QgsFeature(table.fields())
        feat.setAttributes([3])
        table.dataProvider().addFeatures([feat])
        summary, _sampled = result_gate.summarize_layer(table, ["count"])
        self.assertIsNone(summary["geometry"])
        self.assertEqual(summary["feature_count"], 1)

    def test_a_point_layer_is_still_counted(self):
        from cartogen_ai.core.agent import result_gate
        points = QgsVectorLayer("Point?crs=EPSG:4326&field=n:integer", "pts", "memory")
        feat = QgsFeature(points.fields())
        feat.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(44.0, 15.0)))
        feat.setAttributes([1])
        points.dataProvider().addFeatures([feat])
        summary, _sampled = result_gate.summarize_layer(points, ["n"])
        self.assertEqual(summary["geometry"], {"total": 1, "invalid": 0, "empty": 0})


if __name__ == "__main__":
    unittest.main()
