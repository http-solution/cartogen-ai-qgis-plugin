# -*- coding: utf-8 -*-
"""Live-QGIS checks for rc20 audit P2 fixes A11 (projected-foot DEM z-factor) and A12 (RFC 7946 GeoJSON export). Written without
hand-testing; the Docker QGIS run is the only execution evidence."""
import json
import os
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from qgis.core import QgsCoordinateReferenceSystem, QgsFeature, QgsGeometry, QgsPointXY, QgsProject, QgsVectorLayer
    QGIS_LIVE_AVAILABLE = True
except ImportError:
    QGIS_LIVE_AVAILABLE = False


def _boot_qgis():
    from tests.test_chat_widget_live import _boot_qgis as _shared_boot
    return _shared_boot()


class _Dem:
    def __init__(self, crs):
        self._crs = crs

    def crs(self):
        return self._crs


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "requires real QGIS")
class TestAuditP2Live(unittest.TestCase):
    def setUp(self):
        _boot_qgis()
        QgsProject.instance().clear()

    def test_z_factor_converts_metres_into_us_feet(self):
        from cartogen_ai.core.agent.tools.raster_tools import _geographic_z_factor
        feet = _geographic_z_factor(_Dem(QgsCoordinateReferenceSystem("EPSG:2263")))      # NY Long Island, US survey feet
        self.assertAlmostEqual(feet, 3.28083, delta=0.001)
        metres = _geographic_z_factor(_Dem(QgsCoordinateReferenceSystem("EPSG:32638")))
        self.assertAlmostEqual(metres, 1.0, places=6)

    def test_geojson_export_is_wgs84_rfc7946(self):
        from cartogen_ai.core.agent.tools.export_tools import export_layer
        layer = QgsVectorLayer("Point?crs=EPSG:32638&field=id:integer", "pts", "memory")
        feat = QgsFeature(layer.fields())
        feat.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(500000, 1700000)))      # central meridian 45E, ~15.4N
        layer.dataProvider().addFeatures([feat])
        QgsProject.instance().addMapLayer(layer)
        path = os.path.join(tempfile.mkdtemp(prefix="cartogen_gj_"), "pts.geojson")
        res = export_layer("pts", "geojson", output_path=path, confirmed=True)
        self.assertTrue(res.get("success"), res)
        with open(path) as handle:
            data = json.load(handle)
        lon, lat = data["features"][0]["geometry"]["coordinates"][:2]
        self.assertAlmostEqual(lon, 45.0, delta=0.01)
        self.assertAlmostEqual(lat, 15.37, delta=0.1)
        self.assertNotIn("crs", data)


if __name__ == "__main__":
    unittest.main()
