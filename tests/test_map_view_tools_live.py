"""Live-QGIS tests for the M2 tools: groups, project CRS, CRS assignment, bookmarks, project properties, measuring. set_map_view needs
the QGIS interface, which the CI process does not have, so only its refusals are checked here. Written without a QGIS install."""
import unittest

try:
    from qgis.core import QgsFeature, QgsGeometry, QgsProject, QgsVectorLayer
    LIVE = True
except ImportError:
    LIVE = False


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestMapViewToolsLive(unittest.TestCase):
    def setUp(self):
        from tests.test_network_units_live import _boot
        why = _boot()
        if why:
            self.skipTest(why)
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        for name, x in (("roads", 35.0), ("rivers", 36.0)):
            layer = QgsVectorLayer("Point?crs=EPSG:4326&field=n:string", name, "memory")
            f = QgsFeature(layer.fields())
            f.setGeometry(QgsGeometry.fromWkt(f"POINT({x} 31)"))
            layer.dataProvider().addFeatures([f])
            QgsProject.instance().addMapLayer(layer)

    def test_group_create_move_and_options(self):
        from cartogen_ai.core.agent.tools.map_view_tools import create_layer_group, move_layers_to_group, set_group_options
        res = create_layer_group("Water", ["rivers"])
        self.assertTrue(res.get("success"), res)
        root = QgsProject.instance().layerTreeRoot()
        group = root.findGroup("Water")
        self.assertEqual([c.name() for c in group.children()], ["rivers"])
        self.assertIn("already exists", create_layer_group("Water")["error"])
        self.assertIn("not found", create_layer_group("Other", ["nope"])["error"])
        self.assertEqual(root.findGroup("Other"), None)   # nothing half-created
        self.assertEqual(move_layers_to_group("Water", ["roads"])["layers_moved"], ["roads"])
        self.assertEqual(sorted(c.name() for c in group.children()), ["rivers", "roads"])
        opts = set_group_options("Water", visible=False, expanded=False, mutually_exclusive=True)
        self.assertEqual((opts["visible"], opts["expanded"], opts["mutually_exclusive"]), (False, False, True))
        self.assertIn("at least one", set_group_options("Water")["error"])

    def test_project_crs_and_layer_crs_assignment(self):
        from cartogen_ai.core.agent.tools.map_view_tools import assign_layer_crs, set_project_crs
        self.assertEqual(set_project_crs("EPSG:3857")["project_crs"], "EPSG:3857")
        self.assertIn("Unknown crs", set_project_crs("EPSG:99999999")["error"])
        self.assertEqual(assign_layer_crs("roads", "EPSG:3857")["status"], "PREVIEW_REQUIRED")
        self.assertEqual(QgsProject.instance().mapLayersByName("roads")[0].crs().authid(), "EPSG:4326")   # preview changed nothing
        res = assign_layer_crs("roads", "EPSG:3857", confirmed=True)
        self.assertEqual(res["crs"], "EPSG:3857")

    def test_bookmarks(self):
        from cartogen_ai.core.agent.tools.map_view_tools import create_bookmark, go_to_bookmark, list_bookmarks
        self.assertTrue(create_bookmark("Roads", layer_name="roads").get("success"))
        self.assertTrue(create_bookmark("Box", extent=[35, 31, 36, 32]).get("success"))
        self.assertIn("already exists", create_bookmark("Box", extent=[35, 31, 36, 32])["error"])
        self.assertEqual(sorted(b["name"] for b in list_bookmarks()["bookmarks"]), ["Box", "Roads"])
        self.assertIn("No bookmark", go_to_bookmark("Nope")["error"])

    def test_project_properties(self):
        from cartogen_ai.core.agent.tools.map_view_tools import set_project_properties
        from qgis.core import QgsExpressionContextUtils
        res = set_project_properties(title="Flood response", variables={"region": "North"})
        self.assertTrue(res.get("success"), res)
        self.assertEqual(QgsProject.instance().title(), "Flood response")
        self.assertEqual(QgsExpressionContextUtils.projectScope(QgsProject.instance()).variable("region"), "North")
        self.assertIn("not allowed", set_project_properties(variables={"bad name": "x"})["error"])

    def test_measure_on_the_ellipsoid(self):
        from cartogen_ai.core.agent.tools.map_view_tools import measure_distance
        res = measure_distance([[0, 0], [1, 0]])
        self.assertTrue(res.get("success"), res)
        self.assertAlmostEqual(res["length_m"], 111319.5, delta=200)   # one degree of longitude on the equator
        self.assertAlmostEqual(res["bearing_degrees"], 90.0, delta=0.5)
        poly = measure_distance([[0, 0], [0.01, 0], [0.01, 0.01], [0, 0.01]], close_polygon=True)
        self.assertAlmostEqual(poly["area_ha"], 123.0, delta=3)         # about 1.11 km square
        self.assertIn("error", measure_distance([[0, 0]]))
        self.assertIn("error", measure_distance([[0, 0], [1, 1]], crs="nonsense"))

    def test_the_view_tool_refuses_bad_input_before_touching_the_canvas(self):
        from cartogen_ai.core.agent.tools.map_view_tools import set_map_view
        self.assertIn("at least one", set_map_view()["error"])
        self.assertIn("not a scale", set_map_view(scale="big")["error"])
        self.assertIn("xmin < xmax", set_map_view(extent=[5, 0, 1, 1])["error"])
        self.assertIn("not both", set_map_view(extent=[0, 0, 1, 1], center=[0, 0])["error"])


if __name__ == "__main__":
    unittest.main()
