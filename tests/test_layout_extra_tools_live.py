"""Live run of the package G layout tools: every setting is read back from a real QgsPrintLayout. Written without a QGIS install: CI's first
run is its first execution."""
import os
import tempfile
import unittest

try:
    from qgis.core import (QgsFeature, QgsGeometry, QgsLayoutItemMap, QgsLayoutPoint, QgsLayoutSize, QgsPrintLayout, QgsProject, QgsRectangle,
                           QgsVectorLayer)
    from qgis.PyQt.QtCore import Qt
    LIVE = True
except ImportError:
    LIVE = False


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestLayoutExtraTools(unittest.TestCase):
    def setUp(self):
        from tests.test_network_units_live import _boot
        why = _boot()
        if why:
            self.skipTest(why)
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        self.tmp = tempfile.mkdtemp(prefix="cartogen_lay2_")
        self.layer = QgsVectorLayer("Polygon?crs=EPSG:4326&field=name:string&field=pop:integer", "districts", "memory")
        for i in range(4):
            f = QgsFeature(self.layer.fields())
            f.setGeometry(QgsGeometry.fromWkt(f"POLYGON(({35 + i} 31,{36 + i} 31,{36 + i} 32,{35 + i} 32,{35 + i} 31))"))
            f.setAttributes([f"d{i}", 100 * (i + 1)])
            self.layer.dataProvider().addFeatures([f])
        self.layer.updateExtents()
        QgsProject.instance().addMapLayer(self.layer)
        self.layout = QgsPrintLayout(QgsProject.instance())
        self.layout.initializeDefaults()
        self.layout.setName("L2")
        QgsProject.instance().layoutManager().addLayout(self.layout)
        from cartogen_ai.core.agent.tools.layout_tools import LAYOUT_MM
        self.main = QgsLayoutItemMap(self.layout)
        self.main.setId("MAP_MAIN")
        self.layout.addLayoutItem(self.main)
        self.main.attemptMove(QgsLayoutPoint(10, 10, LAYOUT_MM))
        self.main.attemptResize(QgsLayoutSize(200, 140, LAYOUT_MM))
        self.main.setExtent(QgsRectangle(35, 31, 39, 33))

    def test_overview_creates_an_inset_that_shows_the_main_extent(self):
        from cartogen_ai.core.agent.tools.layout_extra_tools import add_overview_map
        res = add_overview_map("L2", inset_box={"x_mm": 215, "y_mm": 10, "width_mm": 60, "height_mm": 40}, color="red")
        self.assertTrue(res.get("success"), res)
        self.assertTrue(res["created_inset"])
        inset = self.layout.itemById("MAP_INSET")
        self.assertIsInstance(inset, QgsLayoutItemMap)
        overview = inset.overviews().overview(0)
        self.assertEqual(overview.linkedMap().id(), "MAP_MAIN")
        self.assertTrue(overview.enabled())
        self.assertGreater(inset.extent().width(), self.main.extent().width())

    def test_overview_uses_an_existing_map_and_refuses_bad_ids(self):
        from cartogen_ai.core.agent.tools.layout_extra_tools import add_overview_map
        other = QgsLayoutItemMap(self.layout)
        other.setId("MAP_LOCATOR")
        self.layout.addLayoutItem(other)
        res = add_overview_map("L2", overview_map_id="MAP_LOCATOR")
        self.assertTrue(res.get("success"), res)
        self.assertFalse(res["created_inset"])
        self.assertIn("no map with id", add_overview_map("L2", overview_map_id="NOPE")["error"])
        self.assertIn("different maps", add_overview_map("L2", overview_map_id="MAP_MAIN")["error"])
        self.assertIn("not found", add_overview_map("Nope", overview_map_id="MAP_LOCATOR")["error"])

    def test_guides_and_grid(self):
        from cartogen_ai.core.agent.tools.layout_extra_tools import set_layout_guides_grid
        res = set_layout_guides_grid("L2", guides=[{"orientation": "vertical", "position_mm": 20}, {"orientation": "horizontal", "position_mm": 15}],
                                     grid_mm=5, snap_to_grid=True, snap_to_guides=True)
        self.assertTrue(res.get("success"), res)
        self.assertEqual(len(self.layout.guides().guides(Qt.Orientation.Vertical, 0)), 1)
        self.assertEqual(len(self.layout.guides().guides(Qt.Orientation.Horizontal, 0)), 1)
        self.assertAlmostEqual(self.layout.gridSettings().resolution().length(), 5)
        self.assertTrue(self.layout.snapper().snapToGrid())
        self.assertTrue(set_layout_guides_grid("L2", clear_guides=True)["success"])
        self.assertEqual(len(self.layout.guides().guides(Qt.Orientation.Vertical, 0)), 0)
        self.assertIn("error", set_layout_guides_grid("L2", guides=[{"orientation": "diagonal", "position_mm": 1}]))

    def test_atlas(self):
        from cartogen_ai.core.agent.tools.layout_extra_tools import set_layout_atlas
        res = set_layout_atlas("L2", "districts", page_name_field="name", sort_field="pop", filter_expression='"pop" > 150',
                               hide_coverage=True, margin_percent=10, scaling="auto")
        self.assertTrue(res.get("success"), res)
        self.assertEqual(res["pages"], 3)
        atlas = self.layout.atlas()
        self.assertTrue(atlas.enabled())
        self.assertEqual(atlas.coverageLayer().name(), "districts")
        self.assertTrue(atlas.hideCoverage())
        self.assertTrue(self.main.atlasDriven())
        self.assertAlmostEqual(self.main.atlasMargin(), 0.1)
        self.assertIn("env()", set_layout_atlas("L2", "districts", filter_expression="env('HOME') = 'x'")["error"])
        self.assertIn("not a field", set_layout_atlas("L2", "districts", sort_field="nope")["error"])
        self.assertIn("not found", set_layout_atlas("L2", "nope")["error"])
        self.assertTrue(set_layout_atlas("L2", disable=True)["success"])
        self.assertFalse(self.layout.atlas().enabled())

    def test_export_with_world_file_and_geopdf_options(self):
        from cartogen_ai.core.agent.tools.layout_item_tools import export_layout
        path = os.path.join(self.tmp, "map.png")
        res = export_layout("L2", path, dpi=60, world_file=True)
        self.assertTrue(res.get("success"), res)
        self.assertTrue(os.path.isfile(path))
        self.assertTrue(os.path.isfile(os.path.join(self.tmp, "map.pgw")), res)
        plain = export_layout("L2", os.path.join(self.tmp, "plain.png"), dpi=60)
        self.assertTrue(plain.get("success"), plain)
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "plain.pgw")))
        self.assertIn("pdf", export_layout("L2", os.path.join(self.tmp, "x.png"), geopdf=True)["error"])
        self.assertIn("image", export_layout("L2", os.path.join(self.tmp, "x.pdf"), world_file=True)["error"])
        pdf = export_layout("L2", os.path.join(self.tmp, "geo.pdf"), dpi=60, geopdf=True)
        # GeoPDF needs the GDAL PDF driver; either it works or the error says the export failed. Both are acceptable, a crash is not.
        self.assertTrue(pdf.get("success") or "failed" in pdf.get("error", ""), pdf)


if __name__ == "__main__":
    unittest.main()
