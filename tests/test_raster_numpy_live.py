# -*- coding: utf-8 -*-
"""Live-QGIS tests for the numpy replacements of ids the 4.2.2 registry lacks (#162 step 2). Written without a QGIS install: CI's first run is their first execution."""
import os
import tempfile
import unittest

try:
    from qgis.core import QgsApplication, QgsProject, QgsRasterLayer
    from osgeo import gdal
    import numpy
    LIVE = True
except ImportError:
    LIVE = False


def _boot():
    from tests.test_chat_widget_live import _boot_qgis
    _boot_qgis()
    try:
        from processing.core.Processing import Processing
        Processing.initialize()
    except Exception:
        pass


def _tif(path, array, nodata=None):
    rows, cols = array.shape[:2]
    bands = 1 if array.ndim == 2 else array.shape[2]
    ds = gdal.GetDriverByName("GTiff").Create(path, cols, rows, bands, gdal.GDT_Float32)
    ds.SetGeoTransform((44.0, 0.001, 0, 15.0, 0, -0.001))
    from osgeo import osr
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(4326)
    ds.SetProjection(srs.ExportToWkt())
    for b in range(bands):
        band = ds.GetRasterBand(b + 1)
        band.WriteArray((array if array.ndim == 2 else array[..., b]).astype("float32"))
        if nodata is not None:
            band.SetNoDataValue(nodata)
    ds.FlushCache()
    ds = None
    return path


@unittest.skipUnless(LIVE, "requires real QGIS + gdal + numpy")
class TestNumpyRasterTools(unittest.TestCase):
    def setUp(self):
        _boot()
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        self.tmp = tempfile.mkdtemp(prefix="cartogen_np_")

    def _add(self, name, array, nodata=None):
        layer = QgsRasterLayer(_tif(os.path.join(self.tmp, name + ".tif"), array, nodata), name)
        self.assertTrue(layer.isValid())
        QgsProject.instance().addMapLayer(layer)
        return layer

    def test_histogram_equalization_writes_an_8_bit_layer(self):
        from cartogen_ai.core.agent.tools.raster_tools import histogram_equalization
        data = numpy.array([[1, 1, 1, 2], [2, 2, 3, 100], [1, 2, 3, 4], [1, 1, 2, 5]], dtype="float32")
        self._add("dim", data)
        res = histogram_equalization("dim")
        self.assertTrue(res.get("success"), res)
        out = QgsProject.instance().mapLayersByName("dim_equalized")[0]
        stats = out.dataProvider().bandStatistics(1)
        self.assertEqual(stats.maximumValue, 255)

    def test_unsupervised_classification_finds_two_clusters(self):
        from cartogen_ai.core.agent.tools.raster_tools import unsupervised_classification
        data = numpy.zeros((10, 10, 2), dtype="float32")
        data[:, 5:, :] = 100.0
        self._add("two", data)
        res = unsupervised_classification("two", 2, seed=1)
        self.assertTrue(res.get("success"), res)
        out = QgsProject.instance().mapLayersByName("two_classified")[0]
        block = out.dataProvider().block(1, out.extent(), 10, 10)
        classes = {int(block.value(r, c)) for r in range(10) for c in range(10)}
        self.assertEqual(classes, {1, 2})

    def test_pansharp_algorithm_exists_with_the_parameter_names_the_tool_uses(self):
        alg = QgsApplication.processingRegistry().algorithmById("gdal:pansharp")
        self.assertIsNotNone(alg)
        names = {p.name() for p in alg.parameterDefinitions()}
        for needed in ("SPECTRAL", "PANCHROMATIC", "OUTPUT"):
            self.assertIn(needed, names)

    def test_supervised_classification_reports_missing_saga(self):
        from cartogen_ai.core.agent.tools.raster_tools import supervised_classification
        self._add("img", numpy.ones((4, 4), dtype="float32"))
        from qgis.core import QgsVectorLayer
        QgsProject.instance().addMapLayer(QgsVectorLayer("Polygon?crs=EPSG:4326", "training", "memory"))
        if QgsApplication.processingRegistry().algorithmById("saga:supervisedclassificationforgrids") is None:
            self.assertIn("SAGA", supervised_classification("img", "training")["error"])


if __name__ == "__main__":
    unittest.main()
