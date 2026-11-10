"""PLAN-023 R3-4: calculate_change_matrix on real GeoTIFFs in real QGIS, with the plan's 2 by 2 known answer, hectares in a projected and a geographic CRS, and the two
table layers it writes. Written without a QGIS install: CI's first run is its first execution."""
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
WGS84 = ('GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563]],PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433]]')


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestChangeMatrixLive(unittest.TestCase):
    def setUp(self):
        from tests.test_network_units_live import _boot
        why = _boot()
        if why:
            self.skipTest(why)
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        self.dir = tempfile.mkdtemp(prefix="cartogen_cm_")

    def _raster(self, name, array, projection=UTM36N, geotransform=(500000.0, 30.0, 0.0, 4000000.0, 0.0, -30.0), nodata=0.0):
        import numpy as np
        path = os.path.join(self.dir, f"{name}.tif")
        arr = np.asarray(array, dtype=np.float32)
        ds = gdal.GetDriverByName("GTiff").Create(path, arr.shape[1], arr.shape[0], 1, gdal.GDT_Float32)
        ds.SetGeoTransform(geotransform)
        ds.SetProjection(projection)
        band = ds.GetRasterBand(1)
        band.WriteArray(arr)
        band.SetNoDataValue(nodata)
        ds = None
        layer = QgsRasterLayer(path, name)
        self.assertTrue(layer.isValid(), name)
        QgsProject.instance().addMapLayer(layer)

    def _tool(self):
        from cartogen_ai.core.agent.tools.registry import TOOL_REGISTRY
        return TOOL_REGISTRY["calculate_change_matrix"]

    def _rows(self, layer_name):
        layer = QgsProject.instance().mapLayersByName(layer_name)[0]
        return [dict(zip(layer.fields().names(), f.attributes(), strict=True)) for f in layer.getFeatures()]

    def test_the_plans_two_by_two_example_with_hectares_tables_and_chart(self):
        self._raster("lc2018", [[1, 1], [2, 2]])
        self._raster("lc2021", [[1, 2], [2, 2]])
        result = self._tool()("lc2018", "lc2021", classes={"1": "Forest", "2": "Cropland"})
        self.assertTrue(result.get("success"), result)
        self.assertEqual(result["matrix"]["cells"], [[1, 1], [0, 2]])
        forest, cropland = result["per_class"]
        self.assertEqual((forest["name"], forest["loss"], forest["gain"]), ("Forest", 1, 0))
        self.assertEqual((cropland["name"], cropland["loss"], cropland["gain"]), ("Cropland", 0, 1))
        self.assertAlmostEqual(forest["ha_loss"], 0.09, places=6)                  # one 30 m cell
        self.assertAlmostEqual(result["totals"]["hectares"], 0.36, places=6)       # four cells
        self.assertEqual(result["totals"]["changed_cells"], 1)
        self.assertEqual(result["layers_created"], ["change_matrix", "change_matrix_summary"])
        transitions = self._rows("change_matrix")
        self.assertEqual(sorted((t["from_class"], t["to_class"], t["cells"]) for t in transitions), [(1, 1, 1), (1, 2, 1), (2, 2, 2)])
        summary = {r["class_name"]: r for r in self._rows("change_matrix_summary")}
        self.assertEqual((summary["Forest"]["loss"], summary["Cropland"]["gain"], summary["Cropland"]["net"]), (1, 1, 1))
        self.assertIn("exact", result["area_method"])
        self.assertTrue("chart_path" in result or "chart_note" in result, result)       # matplotlib may be missing; either is reported

    def test_a_geographic_raster_gets_row_by_row_areas_and_says_they_are_approximate(self):
        gt = (30.0, 1.0, 0.0, 1.0, 0.0, -1.0)            # a 1 degree cell from the equator to 1 degree north
        self._raster("a", [[1]], WGS84, gt)
        self._raster("b", [[1]], WGS84, gt)
        result = self._tool()("a", "b", chart=False)
        self.assertTrue(result.get("success"), result)
        self.assertTrue(1.2360e6 < result["totals"]["hectares"] < 1.2370e6, result["totals"])
        self.assertIn("approximate", result["area_method"])
        self.assertNotIn("chart_path", result)

    def test_cells_nodata_in_either_raster_are_left_out(self):
        self._raster("a", [[1, 0], [2, 2]])              # 0 is NoData
        self._raster("b", [[1, 2], [0, 2]])
        result = self._tool()("a", "b", chart=False)
        self.assertEqual(result["totals"]["valid_cells"], 2)
        self.assertEqual(result["matrix"]["cells"], [[1, 0], [0, 1]])

    def test_plain_refusals_and_no_tables_written(self):
        self._raster("a", [[1.5, 2.0], [1.0, 2.0]])
        self._raster("b", [[1, 2], [1, 2]])
        self._raster("shifted", [[1, 2], [1, 2]], geotransform=(500090.0, 30.0, 0.0, 4000000.0, 0.0, -30.0))
        tool = self._tool()
        self.assertIn("reclassify", tool("a", "b")["error"])
        self.assertIn("not found", tool("b", "nope")["error"])
        self.assertIn("error", tool("b", "shifted"))                                   # a different grid is refused unless align_to_first
        self.assertIn("not a number", tool("b", "b", classes={"forest": "x"})["error"])
        self.assertEqual(len(QgsProject.instance().mapLayersByName("change_matrix")), 0)


if __name__ == "__main__":
    unittest.main()
