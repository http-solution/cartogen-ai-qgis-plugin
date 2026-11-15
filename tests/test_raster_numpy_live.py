"""Live-QGIS tests for the numpy replacements of ids the 4.2.2 registry lacks (#162 step 2). Written without a QGIS install: CI's first run is their first execution."""
import contextlib
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
    with contextlib.suppress(Exception):
        from processing.core.Processing import Processing
        Processing.initialize()


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

    def test_classification_in_several_blocks_matches_the_cluster_layout(self):
        # #222: a tiny block size forces the row-block path through real GDAL reads and writes (4 rows per block here).
        from unittest.mock import patch
        from cartogen_ai.core.agent.tools import raster_numpy
        from cartogen_ai.core.agent.tools.raster_tools import unsupervised_classification
        data = numpy.zeros((30, 10, 2), dtype="float32")
        data[15:, :, :] = 100.0
        self._add("blocks", data)
        with patch.object(raster_numpy, "BLOCK_VALUES", 80):
            res = unsupervised_classification("blocks", 2, seed=1)
        self.assertTrue(res.get("success"), res)
        out = QgsProject.instance().mapLayersByName("blocks_classified")[0]
        block = out.dataProvider().block(1, out.extent(), 10, 30)
        top = {int(block.value(r, c)) for r in range(15) for c in range(10)}
        bottom = {int(block.value(r, c)) for r in range(15, 30) for c in range(10)}
        self.assertEqual((len(top), len(bottom)), (1, 1))
        self.assertNotEqual(top, bottom)

    def test_a_large_raster_goes_through_the_background_runner_and_gives_the_same_clusters(self):
        # Master list AR-4 (audit A14): 600 x 600 = 360,000 cells is above the 250,000 where the tool uses run_callable. Real GDAL, real QgsRasterLayer; whether the
        # worker thread is actually used here depends on can_run_in_background() in this process, which is printed. Written without a QGIS install.
        from unittest.mock import patch
        from cartogen_ai.core import _background_processing as bg
        from cartogen_ai.core.agent.tools.raster_tools import unsupervised_classification
        data = numpy.zeros((600, 600, 2), dtype="float32")
        data[:, 300:, :] = 100.0
        self._add("big", data)
        seen = {}
        real = bg.run_callable

        def spy(fn, **kwargs):
            seen["use_background"] = kwargs.get("use_background")
            seen["label"] = kwargs.get("label")
            return real(fn, **kwargs)

        print(f"AR4 can_run_in_background={bg.can_run_in_background()}")
        with patch.object(bg, "run_callable", spy):
            res = unsupervised_classification("big", 2, seed=1)
        self.assertTrue(res.get("success"), res)
        self.assertTrue(seen.get("use_background"), seen)
        out = QgsProject.instance().mapLayersByName("big_classified")[0]
        block = out.dataProvider().block(1, out.extent(), 600, 600)
        left = {int(block.value(r, c)) for r in range(0, 600, 50) for c in range(0, 290, 50)}
        right = {int(block.value(r, c)) for r in range(0, 600, 50) for c in range(310, 600, 50)}
        self.assertEqual((len(left), len(right)), (1, 1))
        self.assertNotEqual(left, right)

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
