"""Live-QGIS tests for elevation_tools.py and layout_chart_profile_tools.py. Written without a QGIS install: CI's first run is their first
execution. They check that settings and items are stored and read back, NOT how a profile or chart looks when drawn."""
import tempfile
import unittest

try:
    from qgis.core import QgsFeature, QgsGeometry, QgsPrintLayout, QgsProject, QgsRasterLayer, QgsVectorLayer
    LIVE = True
except ImportError:
    LIVE = False


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestElevationAndChartLive(unittest.TestCase):
    def setUp(self):
        from tests._geometry_probe import _make_rasters
        from tests.test_network_units_live import _boot
        why = _boot()
        if why:
            self.skipTest(why)
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        paths = _make_rasters(tempfile.mkdtemp())
        self.dem = QgsRasterLayer(paths["dem"], "dem")
        QgsProject.instance().addMapLayer(self.dem)
        self.towns = QgsVectorLayer("Point?crs=EPSG:4326&field=name:string&field=pop:integer", "towns", "memory")
        for i, (n, pop) in enumerate((("a", 5), ("b", 50), ("c", 500))):
            f = QgsFeature(self.towns.fields())
            f.setGeometry(QgsGeometry.fromWkt(f"POINT({i} {i})"))
            f.setAttributes([n, pop])
            self.towns.dataProvider().addFeatures([f])
        QgsProject.instance().addMapLayer(self.towns)
        self.layout = QgsPrintLayout(QgsProject.instance())
        self.layout.initializeDefaults()
        self.layout.setName("gaps")
        QgsProject.instance().layoutManager().addLayout(self.layout)

    def test_raster_elevation_round_trip(self):
        from cartogen_ai.core.agent.tools.elevation_tools import set_layer_elevation
        res = set_layer_elevation("dem", enabled=True, mode="surface", band=1, z_offset=5, z_scale=2)
        print("GAPRESULT raster_elevation", res)
        self.assertTrue(res.get("success"), res)
        self.assertTrue(res["elevation"]["enabled"])
        self.assertEqual((res["elevation"]["z_offset"], res["elevation"]["z_scale"]), (5.0, 2.0))
        self.assertTrue(self.dem.elevationProperties().isEnabled())

    def test_vector_elevation_round_trip(self):
        from cartogen_ai.core.agent.tools.elevation_tools import set_layer_elevation
        self.assertIn("no elevation on/off switch", set_layer_elevation("towns", enabled=True).get("error", ""))
        res = set_layer_elevation("towns", clamping="relative", extrusion=12, z_offset=1)
        print("GAPRESULT vector_elevation", res)
        self.assertTrue(res.get("success"), res)
        self.assertTrue(res["elevation"]["extrusion_enabled"])
        self.assertEqual(res["elevation"]["z_offset"], 1.0)
        self.assertEqual(res["elevation"]["extrusion"], 12.0)

    def test_elevation_refusals(self):
        from cartogen_ai.core.agent.tools.elevation_tools import set_layer_elevation
        self.assertIn("error", set_layer_elevation("missing", enabled=True))
        self.assertIn("error", set_layer_elevation("dem", clamping="relative"))
        self.assertIn("error", set_layer_elevation("towns", band=1))
        self.assertIn("error", set_layer_elevation("dem"))

    def test_project_terrain(self):
        from cartogen_ai.core.agent.tools.elevation_tools import set_project_terrain
        res = set_project_terrain("flat", offset=3)
        print("GAPRESULT terrain_flat", res)
        self.assertTrue(res.get("success"), res)
        self.assertEqual(res["offset"], 3.0)
        res = set_project_terrain("dem", layer_name="dem", offset=1, scale=2)
        print("GAPRESULT terrain_dem", res)
        self.assertTrue(res.get("success"), res)
        self.assertEqual((res["offset"], res["scale"]), (1.0, 2.0))
        self.assertIn("error", set_project_terrain("dem"))
        self.assertIn("error", set_project_terrain("flat", scale=2))

    def test_chart_item(self):
        from cartogen_ai.core.agent.tools.layout_chart_profile_tools import add_layout_chart
        for kind in ("bar", "line", "pie"):
            res = add_layout_chart("gaps", "towns", "name", "pop", chart_type=kind, item_id=f"CHART_{kind.upper()}")
            print("GAPRESULT chart", kind, res)
            self.assertTrue(res.get("success"), res)
            self.assertIsNotNone(self.layout.itemById(f"CHART_{kind.upper()}"))
        self.assertIn("error", add_layout_chart("gaps", "towns", "nope", "pop"))
        self.assertIn("error", add_layout_chart("nolayout", "towns", "name", "pop"))

    def test_elevation_profile_item(self):
        from cartogen_ai.core.agent.tools.elevation_tools import set_layer_elevation
        from cartogen_ai.core.agent.tools.layout_chart_profile_tools import add_layout_elevation_profile
        off = add_layout_elevation_profile("gaps", ["dem"], 0, 0, 3, 3)
        self.assertIn("Elevation is not turned on", off.get("error", ""), off)
        self.assertTrue(set_layer_elevation("dem", enabled=True, mode="surface").get("success"))
        res = add_layout_elevation_profile("gaps", ["dem"], 0.2, 0.2, 3.5, 3.5, item_id="PROFILE1")
        print("GAPRESULT profile", res)
        self.assertTrue(res.get("success"), res)
        self.assertIsNotNone(self.layout.itemById("PROFILE1"))
        self.assertIn("error", add_layout_elevation_profile("gaps", ["dem"], 1, 1, 1, 1))


if __name__ == "__main__":
    unittest.main()
