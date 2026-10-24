"""PLAN-014 phase 1, real QGIS (CI live job; written without a QGIS install, so CI's first run is its first execution).

1. Credits: a visible web basemap puts its vetted attribution in the layout footer.
2. Geometry: a layout with overlapping, off-page and overflowing items reports them on export; a layout from create_print_layout reports none.
3. Presets and names: a preset sets the dpi; a folder gets <layout>_<date>.<format>.
4. No data (DIAGNOSTIC, pushed before any fix): features whose value is NULL are not painted by apply_graduated_style. A failure of
   TestGraduatedNullIsPainted on the first run is the expected result and the reason for the fix; a pass withdraws that item."""
import datetime
import os
import tempfile
import unittest

from tests.test_network_units_live import QGIS_LIVE_AVAILABLE, _boot

if QGIS_LIVE_AVAILABLE:
    from qgis.core import (QgsFeature, QgsGeometry, QgsLayoutItemLabel, QgsLayoutItemMap, QgsLayoutPoint, QgsLayoutSize, QgsMapRendererSequentialJob,
                           QgsMapSettings, QgsPointXY, QgsPrintLayout, QgsProject, QgsRasterLayer, QgsRectangle, QgsVectorLayer)
    from qgis.PyQt.QtCore import QSize
    from qgis.PyQt.QtGui import QColor

OSM_URI = "type=xyz&url=https://tile.openstreetmap.org/%7Bz%7D/%7Bx%7D/%7By%7D.png&zmax=19&zmin=0"


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "needs real qgis.core bindings")
class _Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        why = _boot()
        if why:
            raise unittest.SkipTest(why)

    def setUp(self):
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def _points(self, name="clinics", values=(1, 2, 3)):
        layer = QgsVectorLayer("Point?crs=EPSG:4326&field=val:double", name, "memory")
        feats = []
        for i, value in enumerate(values):
            f = QgsFeature(layer.fields())
            f.setGeometry(QgsGeometry.fromWkt(f"POINT({44 + i * 0.5} 15)"))
            f.setAttributes([value])
            feats.append(f)
        layer.dataProvider().addFeatures(feats)
        layer.updateExtents()
        QgsProject.instance().addMapLayer(layer)
        return layer


class TestCreditsOnFooter(_Base):
    def test_a_visible_openstreetmap_basemap_is_credited(self):
        self._points()
        basemap = QgsRasterLayer(OSM_URI, "OpenStreetMap", "wms")
        print(f"PLAN014 basemap valid={basemap.isValid()} provider={basemap.providerType()}")
        QgsProject.instance().addMapLayer(basemap)
        from cartogen_ai.core.agent.tools.layout_tools import create_print_layout
        res = create_print_layout("Credit check", confirmed=True)
        self.assertTrue(res.get("success"), res)
        layout = QgsProject.instance().layoutManager().layoutByName(res["layout_name"])
        text = layout.itemById("FOOTER").text()
        from cartogen_ai.core.agent.tools.layout_credits import credit_entries
        from cartogen_ai.core.agent.tools.layout_style import layer_credit_info, visible_layer_entries
        print(f"PLAN014 credit entries: {credit_entries([layer_credit_info(e) for e in visible_layer_entries()])}")
        print(f"PLAN014 footer: {text!r}")
        self.assertIn("Credits: Basemap: OpenStreetMap contributors (ODbL)", text)

    def test_no_basemap_no_credits_line(self):
        self._points()
        from cartogen_ai.core.agent.tools.layout_tools import create_print_layout
        res = create_print_layout("No credit", confirmed=True)
        layout = QgsProject.instance().layoutManager().layoutByName(res["layout_name"])
        self.assertNotIn("Credits:", layout.itemById("FOOTER").text())


class TestGeometryProblemsOnExport(_Base):
    def _layout_with(self, labels):
        project = QgsProject.instance()
        layout = QgsPrintLayout(project)
        layout.initializeDefaults()
        layout.setName("geom")
        map_item = QgsLayoutItemMap(layout)
        map_item.setId("MAP_MAIN")
        layout.addLayoutItem(map_item)
        map_item.attemptMove(QgsLayoutPoint(10, 10))
        map_item.attemptResize(QgsLayoutSize(100, 100))
        map_item.setExtent(QgsRectangle(43, 14, 45, 16))
        for item_id, text, x, y, w, h in labels:
            label = QgsLayoutItemLabel(layout)
            label.setText(text)
            label.setId(item_id)
            layout.addLayoutItem(label)
            label.attemptMove(QgsLayoutPoint(x, y))
            label.attemptResize(QgsLayoutSize(w, h))
        project.layoutManager().addLayout(layout)
        return layout

    def test_overlap_off_page_and_overflow_are_all_reported(self):
        self._points()
        self._layout_with([
            ("OVER_A", "a", 60, 60, 30, 10),                       # on the map: overlaps MAP_MAIN
            ("OFF_PAGE", "b", 290, 200, 30, 20),                   # past the right and bottom edges of an A4 landscape page
            ("OVERFLOW", "Line one\nLine two\nLine three\nLine four\nLine five", 150, 150, 40, 5),
        ])
        from cartogen_ai.core.agent.tools.layout_item_tools import export_layout
        res = export_layout("geom", os.path.join(self.tmp.name, "g.png"), preset="draft", confirmed=True)
        print(f"PLAN014 problems: {res.get('layout_problems')}")
        self.assertTrue(res.get("success"), res)
        text = " | ".join(res.get("layout_problems", []))
        self.assertRegex(text, r"(MAP_MAIN overlaps OVER_A|OVER_A overlaps MAP_MAIN)")
        self.assertIn("OFF_PAGE extends", text)
        self.assertIn("OVERFLOW text needs", text)
        self.assertEqual(res["dpi"], 96)

    def test_a_layout_from_create_print_layout_reports_no_geometry_problem(self):
        self._points()
        from cartogen_ai.core.agent.tools.layout_item_tools import export_layout
        from cartogen_ai.core.agent.tools.layout_tools import create_print_layout
        for orientation in ("Landscape", "Portrait"):
            res = create_print_layout(f"Clean {orientation}", page_orientation=orientation, confirmed=True)
            exported = export_layout(res["layout_name"], os.path.join(self.tmp.name, f"{orientation}.png"), preset="draft", confirmed=True)
            print(f"PLAN014 {orientation} problems: {exported.get('layout_problems')}")
            self.assertTrue(exported.get("success"), exported)
            self.assertEqual(exported.get("layout_problems", []), [], orientation)


class TestPresetsAndNames(_Base):
    def test_a_folder_output_is_named_by_title_and_date_and_a_preset_sets_the_dpi(self):
        self._points()
        from cartogen_ai.core.agent.tools.layout_tools import create_print_layout
        res = create_print_layout("Name check", output_path=self.tmp.name, output_format="png", preset="web", confirmed=True)
        self.assertTrue(res.get("success"), res)
        expected = os.path.join(self.tmp.name, f"Name check_{datetime.date.today().isoformat()}.png")
        self.assertEqual(os.path.normpath(res["output_path"]), os.path.normpath(expected), res)
        self.assertTrue(os.path.isfile(expected))
        self.assertEqual(res["dpi"], 150)

    def test_an_unknown_preset_is_refused_before_anything_is_built(self):
        self._points()
        from cartogen_ai.core.agent.tools.layout_tools import create_print_layout
        res = create_print_layout("Bad preset", output_path=self.tmp.name, preset="poster", confirmed=True)
        self.assertIn("error", res, res)
        self.assertEqual(QgsProject.instance().layoutManager().printLayouts(), [])


class TestGraduatedNullIsPainted(_Base):
    def _painted(self, layer, x, y, size=120):
        settings = QgsMapSettings()
        settings.setLayers([layer])
        settings.setExtent(QgsRectangle(43.5, 14.5, 46.0, 15.5))
        settings.setOutputSize(QSize(size * 2, size))
        settings.setBackgroundColor(QColor(255, 255, 255))
        job = QgsMapRendererSequentialJob(settings)
        job.start()
        job.waitForFinished()
        image = job.renderedImage()
        pixel = settings.mapToPixel().transform(QgsPointXY(x, y))
        count = 0
        for dx in range(-3, 4):
            for dy in range(-3, 4):
                c = QColor(image.pixel(int(pixel.x()) + dx, int(pixel.y()) + dy))
                if (c.red(), c.green(), c.blue()) != (255, 255, 255):
                    count += 1
        return count

    def test_a_feature_with_no_value_is_still_drawn_and_listed_as_no_data(self):
        layer = self._points("scored", (1.0, 2.0, 3.0, None))     # the 4th point (x=45.5) has NULL in val
        from cartogen_ai.core.agent.tools.styling_tools import apply_graduated_style
        res = apply_graduated_style("scored", "val", num_classes=3)
        self.assertTrue(res.get("success"), res)
        control = self._painted(layer, 44.5, 15.0)               # val 2.0: must be painted, or the render itself is broken
        nulled = self._painted(layer, 45.5, 15.0)
        print(f"PLAN014 NULL render: control painted px={control}, NULL feature painted px={nulled}, renderer={layer.renderer().type()}")
        self.assertGreater(control, 0, "control feature was not drawn: the render itself is broken")
        self.assertGreater(nulled, 0, "the feature with no value is not drawn at all")
        labels = [item.label() for item in layer.renderer().legendSymbolItems()]
        self.assertIn("No data", labels)


if __name__ == "__main__":
    unittest.main()
