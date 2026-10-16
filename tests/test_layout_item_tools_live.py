"""Live run of the M5 layout tools: every setting is read back from a real QgsPrintLayout.
Written without a QGIS install: CI's first run is its first execution."""
import os
import tempfile
import unittest

try:
    from qgis.core import (QgsFeature, QgsGeometry, QgsLayoutItemAttributeTable, QgsLayoutItemLabel, QgsLayoutItemMap, QgsLayoutItemPicture,
                           QgsLayoutItemPolyline, QgsLayoutItemShape, QgsLayoutPoint, QgsLayoutSize, QgsPrintLayout, QgsProject,
                           QgsRectangle, QgsVectorLayer)
    LIVE = True
except ImportError:
    LIVE = False


def _boot():
    from tests.test_chat_widget_live import _boot_qgis
    _boot_qgis()


def _case(**kwargs):
    return kwargs


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestLayoutItemTools(unittest.TestCase):
    def setUp(self):
        _boot()
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        self.tmp = tempfile.mkdtemp(prefix="cartogen_lay_")
        self.layer = QgsVectorLayer("Polygon?crs=EPSG:4326&field=name:string&field=pop:integer", "districts", "memory")
        feats = []
        for i in range(5):
            f = QgsFeature(self.layer.fields())
            f.setGeometry(QgsGeometry.fromWkt(f"POLYGON(({35 + i} 31,{36 + i} 31,{36 + i} 32,{35 + i} 32,{35 + i} 31))"))
            f.setAttributes([f"d{i}", 100 * (i + 1)])
            feats.append(f)
        self.layer.dataProvider().addFeatures(feats)
        self.layer.updateExtents()
        QgsProject.instance().addMapLayer(self.layer)
        self.layout = QgsPrintLayout(QgsProject.instance())
        self.layout.initializeDefaults()
        self.layout.setName("L1")
        QgsProject.instance().layoutManager().addLayout(self.layout)
        from cartogen_ai.core.agent.tools.layout_tools import LAYOUT_MM
        self.map_item = QgsLayoutItemMap(self.layout)
        self.map_item.setId("MAP_MAIN")
        self.layout.addLayoutItem(self.map_item)
        self.map_item.attemptMove(QgsLayoutPoint(10, 10, LAYOUT_MM))
        self.map_item.attemptResize(QgsLayoutSize(180, 120, LAYOUT_MM))

    def test_label_shape_arrow_table_picture(self):
        from cartogen_ai.core.agent.tools.layout_item_tools import add_layout_item
        r = add_layout_item("L1", "label", item_id="NOTE", x_mm=10, y_mm=140, width_mm=100, height_mm=10, text="Draft", font_size=14)
        self.assertTrue(r.get("success"), r)
        label = self.layout.itemById("NOTE")
        self.assertIsInstance(label, QgsLayoutItemLabel)
        self.assertEqual(label.text(), "Draft")
        self.assertAlmostEqual(label.textFormat().size(), 14)
        r = add_layout_item("L1", "shape", item_id="BOX", x_mm=200, y_mm=10, width_mm=40, height_mm=30, shape="ellipse",
                            fill_color="pale yellow", outline_color="dark red", outline_width_mm=0.8)
        self.assertTrue(r.get("success"), r)
        self.assertIsInstance(self.layout.itemById("BOX"), QgsLayoutItemShape)
        r = add_layout_item("L1", "arrow", item_id="ARROW", from_x_mm=100, from_y_mm=100, to_x_mm=150, to_y_mm=60)
        self.assertTrue(r.get("success"), r)
        self.assertIsInstance(self.layout.itemById("ARROW"), QgsLayoutItemPolyline)
        r = add_layout_item("L1", "table", item_id="TBL", x_mm=200, y_mm=50, width_mm=90, height_mm=60, layer_name="districts",
                            fields=["name", "pop"], max_rows=3)
        self.assertTrue(r.get("success"), r)
        self.assertIsNotNone(self.layout.itemById("TBL"))
        tables = [m for m in self.layout.multiFrames() if isinstance(m, QgsLayoutItemAttributeTable)]
        self.assertEqual(len(tables), 1)
        self.assertEqual(tables[0].maximumNumberOfFeatures(), 3)
        png = os.path.join(self.tmp, "logo.png")
        from qgis.PyQt.QtGui import QImage
        img = QImage(20, 20, QImage.Format.Format_ARGB32)
        img.fill(0xFF00AA00)
        self.assertTrue(img.save(png))
        r = add_layout_item("L1", "picture", item_id="LOGO", x_mm=250, y_mm=150, width_mm=30, height_mm=30, picture_path=png)
        self.assertTrue(r.get("success"), r)
        self.assertIsInstance(self.layout.itemById("LOGO"), QgsLayoutItemPicture)

    def test_refusals_change_nothing(self):
        from cartogen_ai.core.agent.tools.layout_item_tools import add_layout_item
        before = len(self.layout.items())
        cases = [
            _case(kind="html", x_mm=1, y_mm=1, width_mm=10, height_mm=10),
            _case(kind="picture", x_mm=1, y_mm=1, width_mm=10, height_mm=10, picture_path="https://example.org/a.png"),
            _case(kind="label", x_mm=1, y_mm=1, width_mm=10, height_mm=10),
            _case(kind="label", text="x", x_mm=1, y_mm=1, width_mm=10),
            _case(kind="table", x_mm=1, y_mm=1, width_mm=10, height_mm=10, layer_name="missing"),
            _case(kind="table", x_mm=1, y_mm=1, width_mm=10, height_mm=10, layer_name="districts", fields=["nope"]),
            _case(kind="label", text="x", x_mm=1, y_mm=1, width_mm=10, height_mm=10, item_id="MAP_MAIN"),
            _case(kind="label", text="x", x_mm=1, y_mm=1, width_mm=10, height_mm=10, item_id="a<b"),
        ]
        for kwargs in cases:
            self.assertIn("error", add_layout_item("L1", **kwargs), kwargs)
        self.assertIn("error", add_layout_item("missing", "label", text="x", x_mm=1, y_mm=1, width_mm=10, height_mm=10))
        self.assertEqual(len(self.layout.items()), before)

    def test_edit_and_remove(self):
        from cartogen_ai.core.agent.tools.layout_item_tools import add_layout_item, edit_layout_item
        add_layout_item("L1", "label", item_id="T", x_mm=10, y_mm=10, width_mm=50, height_mm=10, text="x")
        r = edit_layout_item("L1", "T", x_mm=30, width_mm=80, frame=True)
        self.assertTrue(r.get("success"), r)
        item = self.layout.itemById("T")
        self.assertAlmostEqual(item.positionWithUnits().x(), 30)
        self.assertAlmostEqual(item.positionWithUnits().y(), 10)
        self.assertAlmostEqual(item.sizeWithUnits().width(), 80)
        self.assertAlmostEqual(item.sizeWithUnits().height(), 10)
        self.assertTrue(item.hasFrame())
        # QGIS turns an item about its centre and moves the stored top-left corner to match, so rotation is checked on its own
        r = edit_layout_item("L1", "T", rotation=15)
        self.assertTrue(r.get("success"), r)
        self.assertAlmostEqual(self.layout.itemById("T").itemRotation(), 15)
        self.assertIn("error", edit_layout_item("L1", "T"))
        self.assertIn("error", edit_layout_item("L1", "NOPE", x_mm=1))
        self.assertTrue(edit_layout_item("L1", "T", remove=True).get("success"))
        self.assertIsNone(self.layout.itemById("T"))

    def test_map_scale_extent_rotation_lock(self):
        from cartogen_ai.core.agent.tools.layout_item_tools import set_layout_map
        r = set_layout_map("L1", extent_layer="districts", rotation=10, lock_layers=True)
        self.assertTrue(r.get("success"), r)
        self.assertAlmostEqual(self.map_item.mapRotation(), 10)
        self.assertTrue(self.map_item.keepLayerSet())
        self.assertIn(self.layer, self.map_item.layers())
        r = set_layout_map("L1", bbox=[35, 31, 36, 32], scale=250000)
        self.assertTrue(r.get("success"), r)
        self.assertAlmostEqual(self.map_item.scale(), 250000, delta=1)
        self.assertIsInstance(self.map_item.extent(), QgsRectangle)
        self.assertIn("error", set_layout_map("L1"))
        self.assertIn("error", set_layout_map("L1", map_theme="no-such-theme"))
        self.assertIn("error", set_layout_map("L1", extent_layer="missing"))
        self.assertIn("error", set_layout_map("L1", map_item_id="NOPE", scale=1000))

    def test_page_size_orientation_and_pages(self):
        from cartogen_ai.core.agent.tools.layout_item_tools import set_layout_page
        r = set_layout_page("L1", size="A3", orientation="portrait", pages=2)
        self.assertTrue(r.get("success"), r)
        pc = self.layout.pageCollection()
        self.assertEqual(pc.pageCount(), 2)
        size = pc.page(0).pageSize()
        self.assertAlmostEqual(size.width(), 297, delta=0.5)
        self.assertAlmostEqual(size.height(), 420, delta=0.5)
        r = set_layout_page("L1", orientation="landscape", pages=1)
        self.assertTrue(r.get("success"), r)
        size = pc.page(0).pageSize()
        self.assertGreater(size.width(), size.height())
        self.assertEqual(pc.pageCount(), 1)
        self.assertIn("error", set_layout_page("L1", size="A9"))
        self.assertIn("error", set_layout_page("L1", pages=0))
        self.assertIn("error", set_layout_page("L1"))

    def test_template_round_trip_and_export(self):
        from cartogen_ai.core.agent.tools.layout_item_tools import add_layout_item, export_layout, load_layout_template, save_layout_template
        add_layout_item("L1", "label", item_id="KEEP", x_mm=10, y_mm=140, width_mm=60, height_mm=10, text="Kept")
        qpt = os.path.join(self.tmp, "t.qpt")
        self.assertTrue(save_layout_template("L1", qpt).get("success"))
        self.assertTrue(os.path.getsize(qpt) > 0)
        loaded = load_layout_template(qpt, "L2")
        self.assertTrue(loaded.get("success"), loaded)
        copy = QgsProject.instance().layoutManager().layoutByName("L2")
        self.assertIsNotNone(copy.itemById("KEEP"))
        self.assertEqual(copy.itemById("KEEP").text(), "Kept")
        self.assertIn("error", load_layout_template(qpt, "L2"))
        self.assertIn("error", load_layout_template(os.path.join(self.tmp, "nope.qpt"), "L3"))
        self.assertIn("error", save_layout_template("L1", os.path.join(self.tmp, "t.txt")))
        for name in ("m.pdf", "m.png", "m.svg"):
            out = os.path.join(self.tmp, name)
            r = export_layout("L1", out, dpi=72)
            self.assertTrue(r.get("success"), (name, r))
            self.assertTrue(os.path.getsize(out) > 0, name)
        self.assertIn("error", export_layout("L1", os.path.join(self.tmp, "m.docx")))
        self.assertIn("error", export_layout("L1", os.path.join(self.tmp, "m.png"), dpi=5))
        self.assertIn("error", export_layout("nope", os.path.join(self.tmp, "m2.png")))

    def test_html_template_is_refused(self):
        from cartogen_ai.core.agent.tools.layout_item_tools import load_layout_template, save_layout_template
        from qgis.core import QgsLayoutFrame, QgsLayoutItemHtml
        html = QgsLayoutItemHtml(self.layout)
        self.layout.addMultiFrame(html)
        frame = QgsLayoutFrame(self.layout, html)
        html.addFrame(frame)
        qpt = os.path.join(self.tmp, "html.qpt")
        self.assertTrue(save_layout_template("L1", qpt).get("success"))
        refused = load_layout_template(qpt, "WithHtml")
        self.assertIn("error", refused)
        self.assertIsNone(QgsProject.instance().layoutManager().layoutByName("WithHtml"))


if __name__ == "__main__":
    unittest.main()
