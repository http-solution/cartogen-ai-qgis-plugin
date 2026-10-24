"""PLAN-010 live checks (real QGIS, run by the qgis-live-tests CI job; written without a QGIS install, so CI's first run is its first execution).
1. obfuscate_sensitive_points admin_unit_snap with the points and the admin polygons in different CRSs.
2. _replace_named_layer keeps the earlier result when adding the replacement fails."""
import unittest
from unittest.mock import patch

try:
    from qgis.core import QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsFeature, QgsGeometry, QgsProject, QgsVectorLayer
    LIVE = True
except ImportError:
    LIVE = False


def _layer(uri, name, wkt_rows):
    layer = QgsVectorLayer(uri, name, "memory")
    feats = []
    for i, wkt in enumerate(wkt_rows):
        f = QgsFeature(layer.fields())
        f.setGeometry(QgsGeometry.fromWkt(wkt))
        f.setAttributes([i])
        feats.append(f)
    layer.dataProvider().addFeatures(feats)
    layer.updateExtents()
    return layer


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestObfuscateAdminSnapAcrossCrs(unittest.TestCase):
    def setUp(self):
        from tests.test_network_units_live import _boot
        why = _boot()
        if why:
            self.skipTest(why)
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)

    def test_points_in_4326_snap_to_the_centroid_of_a_polygon_in_utm(self):
        wgs, utm = QgsCoordinateReferenceSystem("EPSG:4326"), QgsCoordinateReferenceSystem("EPSG:32638")
        xf = QgsCoordinateTransform(wgs, utm, QgsProject.instance())
        corner = xf.transform(44.0, 15.0)
        poly = (f"POLYGON(({corner.x() - 5000} {corner.y() - 5000},{corner.x() + 5000} {corner.y() - 5000},"
                f"{corner.x() + 5000} {corner.y() + 5000},{corner.x() - 5000} {corner.y() + 5000},{corner.x() - 5000} {corner.y() - 5000}))")
        points = _layer("Point?crs=EPSG:4326&field=id:integer", "sens_pts", ["POINT(44.0005 15.0005)", "POINT(60 -10)"])
        admin = _layer("Polygon?crs=EPSG:32638&field=id:integer", "admin_utm", [poly])
        QgsProject.instance().addMapLayer(points)
        QgsProject.instance().addMapLayer(admin)
        from cartogen_ai.core.agent.tools.vector_tools import obfuscate_sensitive_points
        res = obfuscate_sensitive_points("sens_pts", "admin_unit_snap", admin_layer_name="admin_utm", output_layer_name="sens_out")
        self.assertTrue(res.get("success"), res)
        self.assertEqual(res["feature_count"], 1, res)                    # the point inside matches, the one far away does not
        self.assertEqual(res.get("unmatched_points_skipped"), 1, res)
        out = QgsProject.instance().mapLayersByName("sens_out")[0]
        self.assertEqual(out.crs().authid(), "EPSG:4326")
        p = next(out.getFeatures()).geometry().asPoint()
        # the centroid of the polygon is the UTM corner, which is (44.0, 15.0) in the output layer's own CRS (degrees, not metres)
        self.assertAlmostEqual(p.x(), 44.0, delta=0.001)
        self.assertAlmostEqual(p.y(), 15.0, delta=0.001)


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestReplaceKeepsOldResultWhenAddFails(unittest.TestCase):
    def setUp(self):
        from tests.test_network_units_live import _boot
        why = _boot()
        if why:
            self.skipTest(why)
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)

    def test_add_failure_leaves_the_previous_result(self):
        from cartogen_ai.core.agent.tools.logistics_tools import _replace_named_layer
        _replace_named_layer("plan010_result", _layer("Point?crs=EPSG:4326&field=id:integer", "first", ["POINT(1 1)"]))
        old_id = QgsProject.instance().mapLayersByName("plan010_result")[0].id()
        project = QgsProject.instance()
        real_add = type(project).addMapLayer

        def failing_add(self_, layer, *a, **k):
            raise RuntimeError("project is closing")

        with patch.object(type(project), "addMapLayer", failing_add), self.assertRaises(RuntimeError):
            _replace_named_layer("plan010_result", _layer("Point?crs=EPSG:4326&field=id:integer", "second", ["POINT(2 2)"]))
        self.assertIsNotNone(project.mapLayer(old_id), "the earlier result was removed although the replacement was never added")
        self.assertIs(type(project).addMapLayer, real_add)


if __name__ == "__main__":
    unittest.main()
