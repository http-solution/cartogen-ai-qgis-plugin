"""rc48 B15: grass:r.sunmask.datetime failed twice with "Incorrect parameter value for east" because the model gave east=2.0, north=2.0 for a DEM
in metres. The tool now puts the point of interest at the centre of the elevation layer when it is missing or outside it. Written without a QGIS
install: CI's first run is its first execution, and the first test also checks the cause (GRASS refusing a point outside the layer)."""
import tempfile
import unittest

try:
    from qgis.core import QgsApplication, QgsProject, QgsRasterLayer
    LIVE = True
except ImportError:
    LIVE = False

from cartogen_ai.core.agent.tools.processing_allowlist_tools import centre_point_of_interest, single_value_message

try:
    import numpy as np
    from osgeo import gdal, osr
    GDAL = True
except ImportError:
    GDAL = False

EXTENT = (500000.0, 1000000.0, 501000.0, 1001000.0)


class TestCentrePointOfInterest(unittest.TestCase):
    def test_a_point_outside_the_layer_is_replaced_by_its_centre_with_a_note(self):
        params, note = centre_point_of_interest("grass:r.sunmask.datetime", {"elevation": "dem", "east": "2.0", "north": "2.0"}, EXTENT)
        self.assertEqual((params["east"], params["north"]), ("500500.0", "1000500.0"))
        self.assertIn("centre", note)

    def test_missing_or_text_coordinates_are_replaced_too(self):
        for given in ({}, {"east": "abc", "north": "1"}, {"east": None, "north": None}):
            params, note = centre_point_of_interest("grass:r.sunmask.datetime", dict(given, elevation="dem"), EXTENT)
            self.assertEqual(params["east"], "500500.0", given)
            self.assertTrue(note)

    def test_a_point_inside_the_layer_is_left_alone(self):
        given = {"elevation": "dem", "east": "500100", "north": "1000200"}
        params, note = centre_point_of_interest("grass:r.sunmask.datetime", given, EXTENT)
        self.assertEqual(params, given)
        self.assertIsNone(note)

    def test_other_algorithms_and_unknown_extents_are_untouched(self):
        given = {"east": "2", "north": "2"}
        self.assertEqual(centre_point_of_interest("grass:r.sunmask.position", given, EXTENT), (given, None))
        self.assertEqual(centre_point_of_interest("grass:r.sunmask.datetime", given, None), (given, None))


class TestSingleValueMessage(unittest.TestCase):
    def test_the_message_names_the_single_value_and_the_radius_for_r_circle(self):
        text = single_value_message("grass:r.circle", 0.0)
        self.assertIn("single value (0)", text)
        self.assertIn("pass max", text)
        self.assertNotIn("pass max", single_value_message("native:slope", 3.0))


@unittest.skipUnless(LIVE and GDAL, "requires real QGIS, GDAL and numpy")
class TestOutputReportLive(unittest.TestCase):
    def setUp(self):
        from tests.test_network_units_live import _boot
        why = _boot()
        if why:
            self.skipTest(why)

    def _raster(self, values):
        path = tempfile.mkdtemp() + "/r.tif"
        ds = gdal.GetDriverByName("GTiff").Create(path, 4, 4, 1, gdal.GDT_Float32)
        ds.SetGeoTransform((0, 1, 0, 4, 0, -1))
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(32631)
        ds.SetProjection(srs.ExportToWkt())
        ds.GetRasterBand(1).WriteArray(values)
        ds.FlushCache()
        return QgsRasterLayer(path, "r")

    def test_a_one_value_raster_gets_the_warning_and_a_varied_one_does_not(self):
        from cartogen_ai.core.agent.tools.processing_allowlist_tools import _output_report
        flat = _output_report(self._raster(np.zeros((4, 4), dtype="float32")), "grass:r.circle")
        self.assertIn("single value", flat.get("warning", ""), flat)
        varied = _output_report(self._raster(np.arange(16, dtype="float32").reshape(4, 4)), "grass:r.circle")
        self.assertNotIn("warning", varied)


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestSunmaskLive(unittest.TestCase):
    def setUp(self):
        from tests._geometry_probe import _make_rasters
        from tests.test_network_units_live import _boot
        why = _boot()
        if why:
            self.skipTest(why)
        if QgsApplication.processingRegistry().algorithmById("grass:r.sunmask.datetime") is None:
            self.skipTest("the GRASS provider is not installed in this QGIS")
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        QgsProject.instance().addMapLayer(QgsRasterLayer(_make_rasters(tempfile.mkdtemp())["dem"], "dem"))

    def test_a_point_outside_the_dem_still_runs(self):
        from cartogen_ai.core.agent.tools.processing_allowlist_tools import run_allowlisted_processing_algorithm
        result = run_allowlisted_processing_algorithm(
            "grass:r.sunmask.datetime", {"elevation": "dem", "year": 2026, "month": 6, "day": 21, "hour": 15, "minute": 0, "second": 0,
                                         "timezone": 0, "east": "99999", "north": "99999"}, new_layer_name="shadow_b15")
        print("SUNMASK", result)
        self.assertTrue(result.get("success"), result)
        self.assertIn("parameter_note", result)


if __name__ == "__main__":
    unittest.main()
