# -*- coding: utf-8 -*-
"""#153: rasters on different grids are refused, or aligned onto the first one with a stated rule. Written without a local QGIS:
CI's first run is its first execution."""
import os
import unittest

try:
    from qgis.core import QgsCoordinateReferenceSystem, QgsProject, QgsRasterLayer
    QGIS_LIVE_AVAILABLE = True
except ImportError:
    QGIS_LIVE_AVAILABLE = False

try:
    import numpy as np
    from osgeo import gdal  # noqa: F401
    GDAL_AVAILABLE = True
except ImportError:
    GDAL_AVAILABLE = False


def _boot_qgis():
    from tests.test_chat_widget_live import _boot_qgis as _shared_boot
    return _shared_boot()


def _write(arr, origin_x, origin_y, pixel):
    from cartogen_ai.core.agent.tools import raster_numpy
    info = {"geotransform": (origin_x, pixel, 0.0, origin_y, 0.0, -pixel),
            "projection": QgsCoordinateReferenceSystem("EPSG:4326").toWkt()}
    return raster_numpy.write_single_band(arr.astype("uint8"), info, nodata=0)


@unittest.skipUnless(QGIS_LIVE_AVAILABLE and GDAL_AVAILABLE, "requires real QGIS with GDAL bindings and numpy")
class TestRasterAlignment(unittest.TestCase):
    def setUp(self):
        _boot_qgis()
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        self.paths = [
            _write(np.full((10, 10), 200), 44.0, 15.1, 0.01),     # NIR: 10x10 cells, 0.01 deg
            _write(np.full((20, 20), 100), 44.0, 15.1, 0.005),    # Red: same area, twice the resolution
        ]
        for p in self.paths:
            self.addCleanup(lambda p=p: os.path.exists(p) and os.remove(p))
        self.nir = QgsRasterLayer(self.paths[0], "nir")
        self.red = QgsRasterLayer(self.paths[1], "red")
        self.assertTrue(self.nir.isValid() and self.red.isValid())
        QgsProject.instance().addMapLayers([self.nir, self.red])

    def _ndvi(self, **kw):
        from cartogen_ai.core.agent.tools.raster_tools import calculate_ndvi
        return calculate_ndvi("red", "nir", **kw)

    def test_a_different_cell_size_is_refused_by_default_and_the_message_offers_alignment(self):
        out = self._ndvi()
        self.assertIn("error", out)
        self.assertIn("align_to_first", out["error"])

    def test_align_to_first_runs_and_says_what_it_did(self):
        out = self._ndvi(align_to_first=True, resampling="nearest")
        self.assertTrue(out.get("success"), out)
        self.assertIn("alignment", out)
        self.assertIn("nearest", out["alignment"])
        self.assertIn("'nir'", out["alignment"])

    def test_the_users_own_layers_are_untouched(self):
        self._ndvi(align_to_first=True)
        self.assertEqual((self.red.width(), self.red.height()), (20, 20))
        self.assertEqual(self.red.source(), self.paths[1])

    def test_a_bad_resampling_name_is_rejected(self):
        out = self._ndvi(align_to_first=True, resampling="magic")
        self.assertIn("error", out)
        self.assertIn("resampling", out["error"])


if __name__ == "__main__":
    unittest.main()
