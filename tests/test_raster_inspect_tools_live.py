"""PLAN-023 R10-4 on real GeoTIFFs in real QGIS: the value read back equals the known cell (and its column and row), a point outside is reported, a class raster's attribute table is read
with its names and counts, and pyramids are built into a sidecar .ovr with the overview count read back, the raster file left byte-identical, an existing .ovr asking before it is replaced, and
a small raster refused. Written without a QGIS install: CI's first run is its first execution."""
import hashlib
import os
import pathlib
import tempfile
import unittest

try:
    from osgeo import gdal, osr
    from qgis.core import QgsCoordinateReferenceSystem, QgsProject, QgsRasterLayer
    LIVE = True
except ImportError:
    LIVE = False


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestRasterInspectLive(unittest.TestCase):
    def setUp(self):
        from tests.test_network_units_live import _boot
        why = _boot()
        if why:
            self.skipTest(why)
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        QgsProject.instance().setCrs(QgsCoordinateReferenceSystem("EPSG:32636"))
        self.dir = tempfile.mkdtemp(prefix="cartogen_ri_")

    def _tif(self, name, array, dtype=None, rat=None):
        import numpy as np
        arr = np.asarray(array)
        path = os.path.join(self.dir, f"{name}.tif")
        ds = gdal.GetDriverByName("GTiff").Create(path, arr.shape[1], arr.shape[0], 1, dtype or gdal.GDT_Float32)
        ds.SetGeoTransform((500000.0, 10.0, 0.0, 4000000.0 + 10.0 * arr.shape[0], 0.0, -10.0))
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(32636)
        ds.SetProjection(srs.ExportToWkt())
        band = ds.GetRasterBand(1)
        band.WriteArray(arr)
        if rat is not None:
            band.SetDefaultRAT(rat)
        ds = None
        layer = QgsRasterLayer(path, name)
        self.assertTrue(layer.isValid(), name)
        QgsProject.instance().addMapLayer(layer)
        return path

    def test_the_value_read_back_equals_the_known_cell_with_its_column_and_row(self):
        import numpy as np
        from cartogen_ai.core.agent.tools.raster_inspect_tools import get_raster_value
        self._tif("r", np.arange(16, dtype=np.float32).reshape(4, 4))
        out = get_raster_value("r", 500025.0, 4000015.0)                     # row 2, column 2 of a 4 x 4 grid of 10 m cells: 2 * 4 + 2
        self.assertTrue(out.get("inside"), out)
        self.assertEqual((out["column"], out["row"]), (2, 2))
        self.assertEqual(list(out["values"].values()), [10.0])
        self.assertFalse(out["nodata"])
        self.assertFalse(get_raster_value("r", 1.0, 1.0)["inside"])
        self.assertIn("band must be", get_raster_value("r", 500025.0, 4000015.0, band=3)["error"])
        self.assertIn("not found", get_raster_value("zzz", 1.0, 1.0)["error"])

    def test_a_point_given_in_another_crs_is_transformed(self):
        import numpy as np
        from cartogen_ai.core.agent.tools.raster_inspect_tools import get_raster_value
        self._tif("r", np.ones((4, 4), dtype=np.float32))
        out = get_raster_value("r", 33.0, 0.0, crs="EPSG:4326")           # UTM 36N central meridian is 33 E: easting 500000, northing 0, below this raster
        self.assertTrue(out.get("success"), out)
        self.assertFalse(out["inside"])
        self.assertAlmostEqual(out["point_in_layer_crs"][0], 500000.0, delta=1.0)

    def test_a_class_rasters_attribute_table_is_read(self):
        import numpy as np
        from cartogen_ai.core.agent.tools.raster_inspect_tools import raster_attribute_table
        table = gdal.RasterAttributeTable()
        table.CreateColumn("Value", gdal.GFT_Integer, gdal.GFU_MinMax)
        table.CreateColumn("Class", gdal.GFT_String, gdal.GFU_Name)
        table.CreateColumn("Count", gdal.GFT_Integer, gdal.GFU_PixelCount)
        for row, (value, name, count) in enumerate([(1, "Forest", 6), (2, "Crops", 10)]):
            table.SetValueAsInt(row, 0, value)
            table.SetValueAsString(row, 1, name)
            table.SetValueAsInt(row, 2, count)
        grid = np.array([[1] * 4 + [2] * 4] * 2 + [[2] * 8] * 2, dtype=np.uint8)
        self._tif("classes", grid, dtype=gdal.GDT_Byte, rat=table)
        out = raster_attribute_table("classes")
        self.assertTrue(out.get("has_attribute_table"), out)
        self.assertEqual(out["columns"], ["Value", "Class", "Count"])
        self.assertEqual(out["rows"], [{"Value": 1, "Class": "Forest", "Count": 6}, {"Value": 2, "Class": "Crops", "Count": 10}])
        self._tif("plain", np.ones((4, 4), dtype=np.uint8), dtype=gdal.GDT_Byte)
        self.assertFalse(raster_attribute_table("plain")["has_attribute_table"])

    def test_pyramids_are_built_beside_the_raster_and_the_raster_is_untouched(self):
        import numpy as np
        from cartogen_ai.core.agent.tools.raster_inspect_tools import build_pyramids
        path = self._tif("big", np.random.default_rng(1).random((1024, 1024)).astype(np.float32))
        before = hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
        out = build_pyramids("big")
        self.assertTrue(out.get("built"), out)
        self.assertEqual((out["levels"], out["overview_levels_now"]), ([2, 4], 2))
        self.assertTrue(os.path.exists(path + ".ovr"))
        self.assertEqual(hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest(), before)         # the raster file is byte-identical
        card = build_pyramids("big", levels=[2, 4, 8], method="nearest")
        self.assertEqual(card["status"], "PREVIEW_REQUIRED")
        self.assertEqual(gdal.Open(path).GetRasterBand(1).GetOverviewCount(), 2)               # nothing replaced yet
        again = build_pyramids(confirmed=True, **{k: v for k, v in card["arguments"].items() if k != "confirmed"})
        self.assertEqual((again["levels"], again["overview_levels_now"]), ([2, 4, 8], 3))
        self.assertEqual(hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest(), before)

    def test_a_small_raster_and_bad_requests_are_refused(self):
        import numpy as np
        from cartogen_ai.core.agent.tools.raster_inspect_tools import build_pyramids
        self._tif("small", np.ones((100, 100), dtype=np.float32))
        self.assertIn("would not make it draw", build_pyramids("small")["error"])
        self._tif("big2", np.ones((1024, 1024), dtype=np.float32))
        self.assertIn("method", build_pyramids("big2", method="fancy")["error"])
        self.assertIn("levels", build_pyramids("big2", levels=[1, 2])["error"])


if __name__ == "__main__":
    unittest.main()
