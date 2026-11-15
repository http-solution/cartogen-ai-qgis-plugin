"""PLAN-023 R3-1: calculate_spectral_index on real GeoTIFFs in real QGIS, read back with GDAL and compared with the hand-computed values of the plan.

Written without a QGIS install: CI's first run is its first execution."""
import os
import tempfile
import unittest

try:
    from osgeo import gdal
    from qgis.core import QgsProject, QgsRasterLayer
    LIVE = True
except ImportError:
    LIVE = False


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestSpectralIndexLive(unittest.TestCase):
    def setUp(self):
        from tests.test_network_units_live import _boot
        why = _boot()
        if why:
            self.skipTest(why)
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        self.dir = tempfile.mkdtemp(prefix="cartogen_si_")

    def _raster(self, name, bands, nodata=None, size=(3, 3), origin=(500000.0, 4000000.0), cell=30.0):
        """A GeoTIFF with one band per array in `bands` (2-D numpy arrays), loaded into the project under `name`."""
        import numpy as np
        path = os.path.join(self.dir, f"{name}.tif")
        rows, cols = size
        ds = gdal.GetDriverByName("GTiff").Create(path, cols, rows, len(bands), gdal.GDT_Float32)
        ds.SetGeoTransform((origin[0], cell, 0.0, origin[1], 0.0, -cell))
        ds.SetProjection('PROJCS["WGS 84 / UTM zone 36N",GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563]],'
                         'PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433]],PROJECTION["Transverse_Mercator"],'
                         'PARAMETER["latitude_of_origin",0],PARAMETER["central_meridian",33],PARAMETER["scale_factor",0.9996],'
                         'PARAMETER["false_easting",500000],PARAMETER["false_northing",0],UNIT["metre",1]]')
        for i, arr in enumerate(bands, start=1):
            band = ds.GetRasterBand(i)
            band.WriteArray(np.asarray(arr, dtype=np.float32))
            if nodata is not None:
                band.SetNoDataValue(nodata)
        ds = None
        layer = QgsRasterLayer(path, name)
        self.assertTrue(layer.isValid(), name)
        QgsProject.instance().addMapLayer(layer)
        return layer

    def _read(self, layer_name):
        ds = gdal.Open(QgsProject.instance().mapLayersByName(layer_name)[0].source())
        band = ds.GetRasterBand(1)
        return band.ReadAsArray(), band.GetNoDataValue()

    def _flat(self, value, shape=(3, 3)):
        import numpy as np
        return np.full(shape, value, dtype=np.float32)

    def _tool(self):
        from cartogen_ai.core.agent.tools.registry import TOOL_REGISTRY
        return TOOL_REGISTRY["calculate_spectral_index"]

    def test_savi_matches_the_hand_computed_value_and_keeps_nodata(self):
        nir, red = self._flat(0.5), self._flat(0.1)
        nir[0, 0] = -9999.0                                   # NoData in one input
        self._raster("nir", [nir], nodata=-9999.0)
        self._raster("red", [red], nodata=-9999.0)
        result = self._tool()("SAVI", {"nir": "nir", "red": "red"})
        self.assertTrue(result.get("success"), result)
        self.assertEqual(result["layer_name"], "SAVI")
        values, nodata = self._read("SAVI")
        self.assertEqual(nodata, -9999.0)
        self.assertAlmostEqual(float(values[1, 1]), 0.5455, places=4)       # 0.4 / 1.1 x 1.5
        self.assertEqual(float(values[0, 0]), -9999.0)
        self.assertEqual((result["valid_cells"], result["no_data_cells"]), (8, 1))
        self.assertEqual(result["inputs"], {"nir": "nir", "red": "red"})
        self.assertIn("L = 0.5", result["formula"])

    def test_evi_ndmi_nbr_match_the_plan(self):
        for name, value in (("nir", 0.5), ("red", 0.1), ("blue", 0.05), ("swir1", 0.3), ("swir2", 0.1)):
            self._raster(name, [self._flat(value)])
        evi = self._tool()("EVI", {"nir": "nir", "red": "red", "blue": "blue"}, output_name="my_evi")
        self.assertEqual(evi["layer_name"], "my_evi")
        self.assertAlmostEqual(float(self._read("my_evi")[0][1, 1]), 0.5797, places=4)
        self._tool()("NDMI", {"nir": "nir", "swir1": "swir1"})
        self.assertAlmostEqual(float(self._read("NDMI")[0][1, 1]), 0.25, places=5)
        self._tool()("NBR", {"nir": "nir", "swir2": "swir2"})
        self.assertAlmostEqual(float(self._read("NBR")[0][1, 1]), 0.6667, places=4)

    def test_a_zero_denominator_is_nodata_not_zero(self):
        nir, red = self._flat(0.5), self._flat(0.1)
        nir[1, 1], red[1, 1] = 0.0, 0.0
        self._raster("nir", [nir])
        self._raster("red", [red])
        result = self._tool()("NDVI", {"nir": "nir", "red": "red"})
        values, nodata = self._read("NDVI")
        self.assertEqual(float(values[1, 1]), nodata)
        self.assertEqual(result["no_data_cells"], 1)

    def test_band_references_pick_bands_of_a_multiband_layer(self):
        self._raster("scene", [self._flat(0.1), self._flat(0.5)])              # band 1 red, band 2 nir
        result = self._tool()("NDVI", {"nir": "scene@2", "red": "scene@1"})
        self.assertTrue(result.get("success"), result)
        self.assertAlmostEqual(float(self._read("NDVI")[0][1, 1]), 0.6667, places=4)
        self.assertEqual(result["inputs"], {"nir": "scene@2", "red": "scene@1"})

    def test_digital_number_inputs_get_a_scale_note_for_evi_but_not_for_ndvi(self):
        for name, value in (("nir", 5000.0), ("red", 1000.0), ("blue", 500.0)):
            self._raster(name, [self._flat(value)])
        self.assertIn("digital numbers", self._tool()("EVI", {"nir": "nir", "red": "red", "blue": "blue"}).get("scale_note", ""))
        self.assertNotIn("scale_note", self._tool()("NDVI", {"nir": "nir", "red": "red"}))

    def test_plain_refusals(self):
        self._raster("nir", [self._flat(0.5)])
        self._raster("red", [self._flat(0.1)])
        self._raster("shifted", [self._flat(0.1)], origin=(500090.0, 4000000.0))
        tool = self._tool()
        self.assertIn("not a supported index", tool("XYZ", {"nir": "nir"})["error"])
        self.assertIn("Missing: red", tool("NDVI", {"nir": "nir"})["error"])
        self.assertIn("not found", tool("NDVI", {"nir": "nir", "red": "nope"})["error"])
        self.assertIn("has 1 band", tool("NDVI", {"nir": "nir@3", "red": "red"})["error"])
        self.assertIn("error", tool("NDVI", {"nir": "nir", "red": "shifted"}))       # different grid: refused unless align_to_first
        self.assertEqual(len(QgsProject.instance().mapLayersByName("NDVI")), 0)


if __name__ == "__main__":
    unittest.main()
