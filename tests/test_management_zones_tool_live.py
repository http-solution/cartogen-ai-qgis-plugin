"""PLAN-023 R3-5: create_zoning_map on real GeoTIFFs in real QGIS: the plan's two flat patches, a stray cell that must merge, a two-raster stack, and the polygon layer it
writes (zone numbers, legend labels with the mean, areas). Written without a QGIS install: CI's first run is its first execution."""
import os
import tempfile
import unittest

try:
    from osgeo import gdal
    from qgis.core import QgsProject, QgsRasterLayer
    LIVE = True
except ImportError:
    LIVE = False

UTM36N = ('PROJCS["WGS 84 / UTM zone 36N",GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563]],PRIMEM["Greenwich",0],'
          'UNIT["degree",0.0174532925199433]],PROJECTION["Transverse_Mercator"],PARAMETER["latitude_of_origin",0],PARAMETER["central_meridian",33],'
          'PARAMETER["scale_factor",0.9996],PARAMETER["false_easting",500000],PARAMETER["false_northing",0],UNIT["metre",1]]')


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestManagementZonesLive(unittest.TestCase):
    def setUp(self):
        from tests.test_network_units_live import _boot
        why = _boot()
        if why:
            self.skipTest(why)
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        self.dir = tempfile.mkdtemp(prefix="cartogen_mz_")

    def _raster(self, name, array, nodata=-9999.0):
        import numpy as np
        path = os.path.join(self.dir, f"{name}.tif")
        arr = np.asarray(array, dtype=np.float32)
        ds = gdal.GetDriverByName("GTiff").Create(path, arr.shape[1], arr.shape[0], 1, gdal.GDT_Float32)
        ds.SetGeoTransform((500000.0, 30.0, 0.0, 4000000.0, 0.0, -30.0))
        ds.SetProjection(UTM36N)
        band = ds.GetRasterBand(1)
        band.WriteArray(arr)
        band.SetNoDataValue(nodata)
        ds = None
        layer = QgsRasterLayer(path, name)
        self.assertTrue(layer.isValid(), name)
        QgsProject.instance().addMapLayer(layer)

    def _patches(self, stray=False):
        import numpy as np
        arr = np.full((10, 10), 0.2, dtype=np.float32)
        arr[:, 5:] = 0.8
        if stray:
            arr[3, 1] = 0.8
        return arr

    def _rows(self, name):
        layer = QgsProject.instance().mapLayersByName(name)[0]
        return layer, [dict(zip(layer.fields().names(), f.attributes(), strict=True)) for f in layer.getFeatures()]

    def _tool(self):
        from cartogen_ai.core.agent.tools.registry import TOOL_REGISTRY
        return TOOL_REGISTRY["create_zoning_map"]

    def test_two_flat_patches_make_two_zones_with_exact_means_and_areas(self):
        self._raster("ndvi", self._patches())
        result = self._tool()(["ndvi"], n_zones=2, min_zone_area_ha=0)
        self.assertTrue(result.get("success"), result)
        self.assertEqual(result["zones"], 2)
        layer, rows = self._rows("management_zones")
        self.assertEqual(layer.featureCount(), 2)
        by_zone = {r["zone"]: r for r in rows}
        self.assertAlmostEqual(by_zone[1]["mean_1"], 0.2, places=5)
        self.assertAlmostEqual(by_zone[2]["mean_1"], 0.8, places=5)
        self.assertEqual((by_zone[1]["cells"], by_zone[2]["cells"]), (50, 50))
        self.assertAlmostEqual(by_zone[1]["area_ha"], 50 * 0.09, places=4)           # 50 cells of 30 m x 30 m
        self.assertIn("mean 0.2", by_zone[1]["label"])
        self.assertIn("mean 0.8", by_zone[2]["label"])
        self.assertTrue(by_zone[1]["label"].startswith("Zone 1: ndvi"))
        self.assertIn("not a yield forecast", result["note"])
        self.assertEqual(layer.crs().authid(), "EPSG:32636")
        self.assertTrue(all(f.hasGeometry() and not f.geometry().isEmpty() for f in layer.getFeatures()))

    def test_a_stray_cell_is_merged_into_the_surrounding_zone(self):
        self._raster("ndvi", self._patches(stray=True))
        result = self._tool()(["ndvi"], n_zones=2, min_zone_area_ha=0.2, output_name="zones_merged")      # a single 30 m cell is 0.09 ha
        self.assertEqual(result["patches_merged"], 1)
        _layer, rows = self._rows("zones_merged")
        by_zone = {r["zone"]: r for r in rows}
        self.assertEqual((by_zone[1]["cells"], by_zone[2]["cells"]), (50, 50))                           # the 0.8 stray cell now counts as zone 1
        without = self._tool()(["ndvi"], n_zones=2, min_zone_area_ha=0, output_name="zones_raw")
        self.assertEqual(without["patches_merged"], 0)
        rows_raw = {r["zone"]: r for r in self._rows("zones_raw")[1]}
        self.assertEqual((rows_raw[1]["cells"], rows_raw[2]["cells"]), (49, 51))

    def test_a_stack_of_two_rasters_gives_a_mean_for_each_in_the_label(self):
        self._raster("ndvi", self._patches())
        self._raster("ndre", self._patches() * 0.5)
        result = self._tool()(["ndvi", "ndre"], n_zones=2, min_zone_area_ha=0)
        self.assertEqual(result["rasters"], ["ndvi", "ndre"])
        rows = {r["zone"]: r for r in self._rows("management_zones")[1]}
        self.assertAlmostEqual(rows[2]["mean_2"], 0.4, places=5)
        self.assertIn("ndre mean 0.4", rows[2]["label"])

    def test_the_same_seed_gives_the_same_zones(self):
        self._raster("ndvi", self._patches(stray=True))
        self._tool()(["ndvi"], n_zones=3, min_zone_area_ha=0, seed=7, output_name="a")
        self._tool()(["ndvi"], n_zones=3, min_zone_area_ha=0, seed=7, output_name="b")
        key = lambda name: sorted((r["zone"], r["cells"]) for r in self._rows(name)[1])      # noqa: E731
        self.assertEqual(key("a"), key("b"))

    def test_plain_refusals_and_no_layer_added(self):
        self._raster("ndvi", self._patches())
        tool = self._tool()
        self.assertIn("between 2 and 8", tool(["ndvi"], n_zones=1)["error"])
        self.assertIn("not found", tool(["nope"], n_zones=3)["error"])
        self.assertIn("between 1 and 5", tool([], n_zones=3)["error"])
        self.assertIn("cannot be negative", tool(["ndvi"], min_zone_area_ha=-1)["error"])
        self.assertEqual(len(QgsProject.instance().mapLayersByName("management_zones")), 0)


if __name__ == "__main__":
    unittest.main()
