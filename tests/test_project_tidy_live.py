# -*- coding: utf-8 -*-
"""Live-QGIS tests for tidy_project_layers (GitHub #120 / #128). Written without a QGIS install: CI's first run is their first
execution."""
import os
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from qgis.core import QgsFeature, QgsGeometry, QgsProject, QgsRasterLayer, QgsVectorLayer
    QGIS_LIVE_AVAILABLE = True
except ImportError:
    QGIS_LIVE_AVAILABLE = False

try:
    import numpy as np
    from osgeo import gdal, osr
    GDAL_AVAILABLE = True
except ImportError:
    GDAL_AVAILABLE = False


def _boot_qgis():
    from tests.test_chat_widget_live import _boot_qgis as _shared_boot
    return _shared_boot()


def _points(name, wkts):
    layer = QgsVectorLayer("Point?crs=EPSG:4326", name, "memory")
    feats = []
    for wkt in wkts:
        f = QgsFeature()
        f.setGeometry(QgsGeometry.fromWkt(wkt))
        feats.append(f)
    layer.dataProvider().addFeatures(feats)
    layer.updateExtents()
    return layer


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "requires real QGIS")
class TestTidyProjectLayers(unittest.TestCase):
    def setUp(self):
        _boot_qgis()
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)

    def _tool(self, **kw):
        from cartogen_ai.core.agent.tools.project_tidy_tools import tidy_project_layers
        return tidy_project_layers(**kw)

    def test_identical_scratch_layers_are_duplicates_and_apply_hides_not_deletes(self):
        project = QgsProject.instance()
        a = _points("Origin", ["POINT(44 15.9)"])
        b = _points("Origin", ["POINT(44 15.9)"])
        other = _points("Origin", ["POINT(45 16)"])          # same name, different data: must NOT count
        for layer in (a, b, other):
            project.addMapLayer(layer)
        report = self._tool()
        self.assertFalse(report["applied"])
        self.assertEqual(report["duplicate_layers"], [{"name": "Origin", "copies": 2}])
        self.assertTrue(project.layerTreeRoot().findLayer(b.id()).isVisible())      # report-only changed nothing
        done = self._tool(apply=True)
        self.assertTrue(done["applied"])
        self.assertEqual(len(project.mapLayersByName("Origin")), 3)                 # nothing deleted
        hidden = [x for x in (a, b) if not project.layerTreeRoot().findLayer(x.id()).isVisible()]
        self.assertEqual(len(hidden), 1)
        self.assertTrue(project.layerTreeRoot().findLayer(other.id()).isVisible())

    def test_an_unsaved_project_reports_why_a_scratch_layer_was_not_saved(self):
        QgsProject.instance().addMapLayer(_points("Origin Point", ["POINT(44 15.9)"]))
        report = self._tool()
        self.assertEqual(report["scratch_layers"], [{"name": "Origin Point", "features": 1}])
        done = self._tool(apply=True)
        self.assertIn("not_saved", done)
        self.assertIn("saved", done["not_saved"][0])

    @unittest.skipUnless(GDAL_AVAILABLE, "requires GDAL + numpy")
    def test_a_black_population_raster_gets_the_ramp(self):
        path = os.path.join(tempfile.mkdtemp(), "yem_ppp_2020.tif")
        ds = gdal.GetDriverByName("GTiff").Create(path, 5, 5, 1, gdal.GDT_Float32)
        ds.SetGeoTransform((44.0, 0.01, 0, 16.0, 0, -0.01))
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(4326)
        ds.SetProjection(srs.ExportToWkt())
        band = ds.GetRasterBand(1)
        band.WriteArray(np.arange(25, dtype="float32").reshape(5, 5))
        band.SetNoDataValue(-9999)
        ds.FlushCache()
        ds = None
        raster = QgsRasterLayer(path, "yem_ppp_2020")
        self.assertTrue(raster.isValid())
        QgsProject.instance().addMapLayer(raster)
        self.assertNotEqual(raster.renderer().type(), "singlebandpseudocolor")
        self.assertEqual(self._tool()["population_rasters_without_ramp"], ["yem_ppp_2020"])
        self._tool(apply=True)
        self.assertEqual(raster.renderer().type(), "singlebandpseudocolor")
        self.assertEqual(self._tool()["population_rasters_without_ramp"], [])

    def test_a_clean_project_has_nothing_to_tidy(self):
        QgsProject.instance().addMapLayer(_points("Clinics", ["POINT(44 15.9)", "POINT(44.1 16)"]))   # a memory layer is reported as scratch, not as a duplicate
        report = self._tool()
        self.assertEqual(report["duplicate_layers"], [])
        self.assertEqual(report["population_rasters_without_ramp"], [])


if __name__ == "__main__":
    unittest.main()
