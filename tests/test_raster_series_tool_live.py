"""PLAN-023 R3-3: raster_time_series_stats on real GeoTIFFs in real QGIS, read back with GDAL and compared with the hand-computed answers of the plan.

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
class TestRasterSeriesLive(unittest.TestCase):
    def setUp(self):
        from tests.test_network_units_live import _boot
        why = _boot()
        if why:
            self.skipTest(why)
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        self.dir = tempfile.mkdtemp(prefix="cartogen_ts_")

    def _raster(self, name, array, nodata=-9999.0, origin=(500000.0, 4000000.0)):
        import numpy as np
        path = os.path.join(self.dir, f"{name}.tif")
        arr = np.asarray(array, dtype=np.float32)
        ds = gdal.GetDriverByName("GTiff").Create(path, arr.shape[1], arr.shape[0], 1, gdal.GDT_Float32)
        ds.SetGeoTransform((origin[0], 30.0, 0.0, origin[1], 0.0, -30.0))
        ds.SetProjection('PROJCS["WGS 84 / UTM zone 36N",GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563]],'
                         'PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433]],PROJECTION["Transverse_Mercator"],'
                         'PARAMETER["latitude_of_origin",0],PARAMETER["central_meridian",33],PARAMETER["scale_factor",0.9996],'
                         'PARAMETER["false_easting",500000],PARAMETER["false_northing",0],UNIT["metre",1]]')
        band = ds.GetRasterBand(1)
        band.WriteArray(arr)
        band.SetNoDataValue(nodata)
        ds = None
        layer = QgsRasterLayer(path, name)
        self.assertTrue(layer.isValid(), name)
        QgsProject.instance().addMapLayer(layer)

    def _read(self, name):
        ds = gdal.Open(QgsProject.instance().mapLayersByName(name)[0].source())
        band = ds.GetRasterBand(1)
        return band.ReadAsArray(), band.GetNoDataValue()

    def _tool(self):
        from cartogen_ai.core.agent.tools.registry import TOOL_REGISTRY
        return TOOL_REGISTRY["raster_time_series_stats"]

    def _years(self, values_per_year):
        """One 2 x 2 raster per year; `values_per_year` is a list of 2 x 2 lists."""
        names = []
        for i, values in enumerate(values_per_year):
            self._raster(f"y{2018 + i}", values)
            names.append(f"y{2018 + i}")
        return names

    def test_trend_of_1_2_3_4_over_four_years_is_exactly_one_per_year(self):
        names = self._years([[[1, 8], [5, 1]], [[2, 6], [5, 2]], [[3, 4], [5, 3]], [[4, 2], [5, 4]]])
        result = self._tool()(names, statistic="trend", times=[2018, 2019, 2020, 2021])
        self.assertTrue(result.get("success"), result)
        values, nodata = self._read("ts_trend")
        self.assertEqual(float(values[0, 0]), 1.0)             # 1, 2, 3, 4
        self.assertEqual(float(values[0, 1]), -2.0)            # 8, 6, 4, 2
        self.assertEqual(float(values[1, 0]), 0.0)             # flat
        self.assertEqual(nodata, -9999.0)
        self.assertEqual(result["rasters_used"], 4)
        self.assertEqual(result["times_years"], [2018.0, 2019.0, 2020.0, 2021.0])
        self.assertIn("per year", result["units"])

    def test_trend_with_dates_and_a_cell_with_too_few_valid_values(self):
        grids = [[[1, -9999.0], [1, 1]], [[2, -9999.0], [2, 2]], [[3, 5.0], [3, 3]], [[4, 6.0], [4, 4]]]
        names = self._years(grids)
        result = self._tool()(names, statistic="trend", times=["2018-01-01", "2019-01-01", "2020-01-01", "2021-01-01"])
        values, nodata = self._read("ts_trend")
        self.assertAlmostEqual(float(values[0, 0]), 1.0, delta=0.01)       # leap year makes the spacing 0.9993 to 1.0007
        self.assertEqual(float(values[0, 1]), nodata)                       # only 2 valid observations of the 3 needed
        self.assertEqual(result["no_data_cells"], 1)

    def test_anomaly_of_14_against_a_baseline_of_8_10_12_is_z_2(self):
        names = self._years([[[8, 8], [8, 8]], [[10, 10], [10, 10]], [[12, 12], [12, 12]], [[14, 6], [10, 14]]])
        result = self._tool()(names, statistic="anomaly")
        self.assertTrue(result.get("success"), result)
        values, _nodata = self._read("ts_anomaly")
        self.assertAlmostEqual(float(values[0, 0]), 2.0, places=5)          # (14 - 10) / 2
        self.assertAlmostEqual(float(values[0, 1]), -2.0, places=5)         # (6 - 10) / 2
        self.assertAlmostEqual(float(values[1, 0]), 0.0, places=5)
        self.assertEqual(result["target"], "y2021")
        self.assertEqual(result["baseline"], ["y2018", "y2019", "y2020"])

    def test_anomaly_with_an_explicit_target_and_baseline(self):
        names = self._years([[[14, 14], [14, 14]], [[8, 8], [8, 8]], [[10, 10], [10, 10]], [[12, 12], [12, 12]]])
        result = self._tool()(names, statistic="anomaly", target=names[0], baseline=names[1:], output_name="z_2018")
        self.assertEqual(result["layer_name"], "z_2018")
        self.assertAlmostEqual(float(self._read("z_2018")[0][0, 0]), 2.0, places=5)

    def test_mean_skips_nodata_and_names_the_layer(self):
        names = self._years([[[2, -9999.0], [1, 1]], [[4, -9999.0], [1, 1]], [[9, -9999.0], [1, 1]]])
        result = self._tool()(names, statistic="mean")
        values, nodata = self._read("ts_mean")
        self.assertAlmostEqual(float(values[0, 0]), 5.0, places=5)
        self.assertEqual(float(values[0, 1]), nodata)
        self.assertEqual(result["layer_name"], "ts_mean")

    def test_plain_refusals_and_no_layer_added(self):
        names = self._years([[[1, 1], [1, 1]], [[2, 2], [2, 2]], [[3, 3], [3, 3]]])
        self._raster("shifted", [[1, 1], [1, 1]], origin=(500090.0, 4000000.0))
        tool = self._tool()
        self.assertIn("one time per raster", tool(names, statistic="trend", times=[2018])["error"])
        self.assertIn("not a time", tool(names, statistic="trend", times=["a", "b", "c"])["error"])
        self.assertIn("at least 3 baseline", tool(names[:3], statistic="anomaly")["error"])
        self.assertIn("not found", tool([*names, "nope"], statistic="mean")["error"])
        self.assertIn("statistic must be", tool(names, statistic="median")["error"])
        self.assertIn("error", tool([*names, "shifted"], statistic="mean"))                  # a different grid is refused unless align_to_first
        self.assertEqual(len(QgsProject.instance().mapLayersByName("ts_mean")), 0)


if __name__ == "__main__":
    unittest.main()
