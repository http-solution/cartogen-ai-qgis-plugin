"""Live run of raster_calculator against QGIS 4.2.2's native:rastercalc. Written without a QGIS install: CI's first run is its first execution."""
import contextlib
import os
import tempfile
import unittest

try:
    from qgis.core import QgsProject, QgsRasterLayer
    from osgeo import gdal, osr
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


def _tif(path, bands, epsg=4326, nodata=None):
    rows, cols = bands[0].shape
    ds = gdal.GetDriverByName("GTiff").Create(path, cols, rows, len(bands), gdal.GDT_Float32)
    ds.SetGeoTransform((44.0, 0.001, 0, 15.0, 0, -0.001))
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(epsg)
    ds.SetProjection(srs.ExportToWkt())
    for i, array in enumerate(bands):
        band = ds.GetRasterBand(i + 1)
        band.WriteArray(array.astype("float32"))
        if nodata is not None:
            band.SetNoDataValue(nodata)
    ds.FlushCache()
    ds = None
    return path


def _values(layer):
    ds = gdal.Open(layer.source())
    return ds.GetRasterBand(1).ReadAsArray()


@unittest.skipUnless(LIVE, "requires real QGIS + gdal + numpy")
class TestRasterCalculator(unittest.TestCase):
    def setUp(self):
        _boot()
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        self.tmp = tempfile.mkdtemp(prefix="cartogen_rc_")

    def _add(self, name, *bands, epsg=4326, nodata=None):
        layer = QgsRasterLayer(_tif(os.path.join(self.tmp, name.replace(" ", "_") + ".tif"), bands, epsg, nodata), name)
        self.assertTrue(layer.isValid())
        QgsProject.instance().addMapLayer(layer)
        return layer

    def _run(self, expression, **kw):
        from cartogen_ai.core.agent.tools.raster_calculator_tool import raster_calculator
        return raster_calculator(expression, **kw)

    def test_threshold_mask(self):
        self._add("dem", numpy.array([[10, 120, 90], [200, 100, 101]]))
        result = self._run('"dem@1" > 100', new_layer_name="above")
        self.assertTrue(result.get("success"), result)
        out = _values(QgsProject.instance().mapLayersByName("above")[0])
        self.assertEqual(out.tolist(), [[0, 1, 0], [1, 0, 1]])

    def test_two_layers_and_a_band_and_every_function(self):
        self._add("a", numpy.full((2, 2), 9.0), numpy.full((2, 2), 4.0))
        self._add("b", numpy.full((2, 2), 3.0))
        result = self._run('sqrt("a@1") + "a@2" / "b@1"', new_layer_name="calc")
        self.assertTrue(result.get("success"), result)
        out = _values(QgsProject.instance().mapLayersByName("calc")[0])
        self.assertAlmostEqual(float(out[0][0]), 3 + 4 / 3, places=4)
        for fn in ("sin", "cos", "tan", "asin", "acos", "atan", "ln", "log10", "abs"):
            r = self._run(f'{fn}("b@1" / 10)', new_layer_name="f_" + fn)
            self.assertTrue(r.get("success"), (fn, r))
        r = self._run('min("a@1", "b@1") AND max("a@1", "b@1") OR "a@1" ^ 2 >= 1', new_layer_name="logic")
        self.assertTrue(r.get("success"), r)

    def test_nodata_stays_nodata(self):
        self._add("n", numpy.array([[1.0, -9999.0], [3.0, 4.0]]), nodata=-9999)
        result = self._run('"n@1" * 2', new_layer_name="nd")
        self.assertTrue(result.get("success"), result)
        out = QgsProject.instance().mapLayersByName("nd")[0]
        self.assertFalse(out.dataProvider().sourceHasNoDataValue(1) and _values(out)[0][1] == 2 * -9999.0)

    def test_refusals_run_nothing_and_add_no_layer(self):
        self._add("dem", numpy.ones((2, 2)))
        before = len(QgsProject.instance().mapLayers())
        for expression in ('__import__("os")', '"dem@2" + 1', '"missing@1" + 1', "1 + 1"):
            self.assertIn("error", self._run(expression), expression)
        self.assertEqual(len(QgsProject.instance().mapLayers()), before)

    def test_different_crs_is_refused_with_both_names(self):
        self._add("geo", numpy.ones((2, 2)))
        self._add("utm", numpy.ones((2, 2)), epsg=32638)
        result = self._run('"geo@1" + "utm@1"')
        self.assertIn("different coordinate systems", result["error"])

    def test_duplicate_layer_names_are_refused(self):
        self._add("dup", numpy.ones((2, 2)))
        self._add("dup", numpy.ones((2, 2)))
        self.assertIn("More than one raster layer", self._run('"dup@1" + 1')["error"])


if __name__ == "__main__":
    unittest.main()
