# -*- coding: utf-8 -*-
"""#161: points in one CRS are assigned to admin polygons in another. Written without a local QGIS: CI's first run is its first execution."""
import unittest

try:
    from qgis.core import (QgsCoordinateReferenceSystem, QgsFeature, QgsGeometry, QgsPointXY, QgsProject, QgsVectorLayer)
    QGIS_LIVE_AVAILABLE = True
except ImportError:
    QGIS_LIVE_AVAILABLE = False


def _boot_qgis():
    from tests.test_chat_widget_live import _boot_qgis as _shared_boot
    return _shared_boot()


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "requires real QGIS")
class TestPointsInAnotherCrs(unittest.TestCase):
    def setUp(self):
        _boot_qgis()
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        # Two UTM 36N squares side by side near Amman; points are given in WGS84.
        self.admin = QgsVectorLayer("Polygon?crs=EPSG:32636&field=name:string", "admin", "memory")
        feats = []
        for i, x0 in enumerate((775000.0, 777000.0)):
            f = QgsFeature(self.admin.fields())
            f.setGeometry(QgsGeometry.fromWkt(f"POLYGON(({x0} 3537000, {x0 + 1900} 3537000, {x0 + 1900} 3541000, {x0} 3541000, {x0} 3537000))"))
            f.setAttributes([f"D{i + 1}"])
            feats.append(f)
        self.admin.dataProvider().addFeatures(feats)
        QgsProject.instance().addMapLayer(self.admin)

    def _wgs84_point(self, easting, northing):
        from qgis.core import QgsCoordinateTransform
        xf = QgsCoordinateTransform(QgsCoordinateReferenceSystem("EPSG:32636"), QgsCoordinateReferenceSystem("EPSG:4326"), QgsProject.instance())
        p = xf.transform(QgsPointXY(easting, northing))
        return QgsGeometry.fromPointXY(p)

    def test_raw_wgs84_points_match_nothing_but_transformed_ones_do(self):
        from cartogen_ai.core.agent.tools import analysis_tools as at
        index, by_id = at._build_polygon_index(self.admin)
        pts = [self._wgs84_point(775500, 3539000), self._wgs84_point(777500, 3539000), self._wgs84_point(777600, 3539500)]
        _counts, raw = at._assign_points_to_polygons_indexed(index, by_id, list(pts))
        self.assertEqual(raw["matched"], 0, "degrees against metres can never intersect: this is the silent failure")
        moved = list(at._geometries_in_crs(iter(pts), QgsCoordinateReferenceSystem("EPSG:4326"), self.admin.crs()))
        counts, stats = at._assign_points_to_polygons_indexed(index, by_id, moved)
        self.assertEqual(stats["matched"], 3)
        self.assertEqual(sorted(counts.values()), [1, 2])

    def test_same_crs_and_unknown_crs_pass_through_untouched(self):
        from cartogen_ai.core.agent.tools import analysis_tools as at
        g = QgsGeometry.fromPointXY(QgsPointXY(1, 2))
        same = list(at._geometries_in_crs([g, None], self.admin.crs(), self.admin.crs()))
        self.assertIs(same[0], g)
        self.assertIsNone(same[1])
        unknown = list(at._geometries_in_crs([g], QgsCoordinateReferenceSystem(), self.admin.crs()))
        self.assertIs(unknown[0], g)

    def test_the_input_geometry_is_not_modified(self):
        from cartogen_ai.core.agent.tools import analysis_tools as at
        g = self._wgs84_point(775500, 3539000)
        before = g.asWkt()
        list(at._geometries_in_crs([g], QgsCoordinateReferenceSystem("EPSG:4326"), self.admin.crs()))
        self.assertEqual(g.asWkt(), before)


if __name__ == "__main__":
    unittest.main()
