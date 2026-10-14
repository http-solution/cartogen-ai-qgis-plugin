"""Live-QGIS check of delineate_watershed on a synthetic DEM written with GDAL (no network). Two V-shaped valleys one arc-second apart in a
real EPSG:4326 GeoTIFF, with the left channel passing through the reported outlet 32°01'47.39"N, 35°48'21.00"E. Written without a QGIS
install: CI's first run is its first execution."""
import os
import tempfile
import unittest

try:
    from qgis.core import QgsProject, QgsRasterLayer
    LIVE = True
except ImportError:
    LIVE = False

PX = 1 / 3600.0
LON, LAT = 35.8058333333, 32.0298305556        # the reported outlet


def _write_dem(path, rows=100, cols=80):
    import numpy as np
    from osgeo import gdal, osr
    r, c = np.indices((rows, cols))
    lateral = np.where(c <= 40, 10.0 * np.abs(c - 12), 10.0 * np.abs(c - 62))
    dem = ((rows - r) * 0.5 + lateral + 600.0).astype(np.float32)
    ds = gdal.GetDriverByName("GTiff").Create(path, cols, rows, 1, gdal.GDT_Float32)
    # the cell centre of (row 60, col 12) is the outlet
    ds.SetGeoTransform((LON - 12.5 * PX, PX, 0, LAT + 60.5 * PX, 0, -PX))
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(4326)
    ds.SetProjection(srs.ExportToWkt())
    ds.GetRasterBand(1).WriteArray(dem)
    ds.GetRasterBand(1).SetNoDataValue(-9999)
    ds = None


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestDelineateWatershedLive(unittest.TestCase):
    def setUp(self):
        from tests.test_network_units_live import _boot
        why = _boot()
        if why:
            self.skipTest(why)
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)

    def _add_dem(self):
        path = os.path.join(tempfile.mkdtemp(), "dem.tif")
        _write_dem(path)
        layer = QgsRasterLayer(path, "DEM_test")
        self.assertTrue(layer.isValid())
        QgsProject.instance().addMapLayer(layer)
        return layer

    def test_the_reported_location_gives_a_measured_basin_and_layers(self):
        from cartogen_ai.core.agent.tools.watershed_tools import delineate_watershed
        self._add_dem()
        res = delineate_watershed(location="32° 1'47.39\"N, 35°48'21.00\"E", return_period_years=20, snap_distance_m=0)
        self.assertTrue(res.get("success"), res)
        m = res["measurements"]
        # The left valley of this 80-column DEM spans about 40 columns (the ridge is at column ~37 and ties drain left) x 61 rows (0..60) of
        # 26.2 m x 30.7 m cells (~805 m2): about 2 440 cells = 1.96 km2. The first CI run measured 1.9647 km2, i.e. the tool was right and the
        # bound copied from the 50-column unit test was wrong.
        self.assertGreater(m["watershed_area_km2"], 1.5)
        self.assertLess(m["watershed_area_km2"], 2.2)
        self.assertGreater(m["longest_hydraulic_flow_path_km"], 1.7)
        self.assertLess(m["longest_hydraulic_flow_path_km"], 2.6)
        self.assertGreater(m["H_elevation_drop_m"], 0)
        self.assertGreater(res["time_of_concentration_kirpich_min"], 0)
        self.assertEqual(sorted(res["layers_added"]), ["Watershed basin", "Watershed longest flow path", "Watershed outlet"])
        for name in res["layers_added"]:
            self.assertEqual(QgsProject.instance().mapLayersByName(name)[0].featureCount(), 1)
        basin = next(QgsProject.instance().mapLayersByName("Watershed basin")[0].getFeatures())
        self.assertFalse(basin.geometry().isEmpty())
        self.assertTrue(basin.geometry().isGeosValid())

    def test_the_reply_asks_for_the_design_inputs_instead_of_inventing_them(self):
        from cartogen_ai.core.agent.tools.watershed_tools import delineate_watershed
        self._add_dem()
        res = delineate_watershed(lat=LAT, lon=LON, return_period_years=20)
        needed = res["design_inputs_needed"]
        self.assertIn("20-year", needed["rainfall_intensity"])
        self.assertIn("runoff_coefficient", needed)
        self.assertNotIn("peak_flow_m3_s", res)
        self.assertIn("calculate_rational_watershed_peak_flow", res["next_step"])

    def test_no_dem_gives_the_exact_fetch_dem_call(self):
        from cartogen_ai.core.agent.tools.watershed_tools import delineate_watershed
        res = delineate_watershed(lat=LAT, lon=LON)
        self.assertIn("fetch_dem(lat=32.02983", res["error"])

    def test_a_point_outside_the_dem_and_a_bad_location_are_refused(self):
        from cartogen_ai.core.agent.tools.watershed_tools import delineate_watershed
        self._add_dem()
        self.assertIn("error", delineate_watershed(lat=10.0, lon=10.0, dem_layer="DEM_test"))
        self.assertIn("could not be read", delineate_watershed(location="near the hospital")["error"])


if __name__ == "__main__":
    unittest.main()
