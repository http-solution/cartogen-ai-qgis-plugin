# -*- coding: utf-8 -*-
"""Clipping a population raster to a window keeps its pixel values (real GDAL) -- F19, rc7 smoke test.

Uses a synthetic local GeoTIFF instead of the WorldPop server, so CI needs no network: the code under
test is _clip_raster_to_bbox, which is identical for a local path and for /vsicurl/<url>. What this does
NOT cover is the remote range-request behaviour against data.worldpop.org.
Written without a QGIS/GDAL install; its first execution is CI."""
import os
import tempfile
import unittest

try:
    from osgeo import gdal, osr
    import numpy as np
    GDAL_AVAILABLE = True
except ImportError:
    GDAL_AVAILABLE = False


def _make_raster(path, size=100, origin=(40.0, 20.0), pixel=0.1):
    """size x size pixels covering lon 40..50, lat 10..20; every pixel holds its own column*1000+row."""
    drv = gdal.GetDriverByName("GTiff")
    ds = drv.Create(path, size, size, 1, gdal.GDT_Float32)
    ds.SetGeoTransform((origin[0], pixel, 0, origin[1], 0, -pixel))
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(4326)
    ds.SetProjection(srs.ExportToWkt())
    cols, rows = np.meshgrid(np.arange(size), np.arange(size))
    ds.GetRasterBand(1).WriteArray((cols * 1000 + rows).astype("float32"))
    ds.FlushCache()
    ds = None


@unittest.skipUnless(GDAL_AVAILABLE, "needs osgeo.gdal + numpy")
class TestClipKeepsPixelValues(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.src = os.path.join(self.tmp.name, "country.tif")
        self.dst = os.path.join(self.tmp.name, "area.tif")
        _make_raster(self.src)

    def test_the_window_has_the_expected_size_and_the_same_values(self):
        from cartogen_ai.core.agent.tools.humanitarian_tools import _clip_raster_to_bbox
        info = _clip_raster_to_bbox(self.src, (42.0, 14.0, 44.0, 16.0), self.dst)
        self.assertEqual((info["width"], info["height"]), (20, 20))
        ds = gdal.Open(self.dst)
        out = ds.GetRasterBand(1).ReadAsArray()
        ds = None
        full = gdal.Open(self.src).GetRasterBand(1).ReadAsArray()
        # lon 42 -> column 20, lat 16 -> row 40
        self.assertTrue((out == full[40:60, 20:40]).all())
        self.assertEqual(float(out.sum()), float(full[40:60, 20:40].sum()))

    def test_the_clip_is_much_smaller_than_the_source(self):
        from cartogen_ai.core.agent.tools.humanitarian_tools import _clip_raster_to_bbox
        _clip_raster_to_bbox(self.src, (42.0, 14.0, 44.0, 16.0), self.dst)
        ds = gdal.Open(self.dst)
        self.assertLess(ds.RasterXSize * ds.RasterYSize, 100 * 100 // 10)
        ds = None

    def test_a_window_outside_the_raster_is_a_runtime_error_with_a_message(self):
        from cartogen_ai.core.agent.tools.humanitarian_tools import _clip_raster_to_bbox
        with self.assertRaises(RuntimeError) as ctx:
            _clip_raster_to_bbox(self.src, (100.0, 50.0, 101.0, 51.0), self.dst)
        self.assertTrue(str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
