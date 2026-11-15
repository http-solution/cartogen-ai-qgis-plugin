"""PLAN-021 WP-B, real QGIS (CI live job; written without a QGIS install, so CI's first run is its first execution): the legend never has an entry cut
by its frame, the footer check reports its numbers and no false warning, and the layout keeps the name it was asked for."""
import unittest

from tests.test_network_units_live import QGIS_LIVE_AVAILABLE, _boot

if QGIS_LIVE_AVAILABLE:
    from qgis.core import (QgsCategorizedSymbolRenderer, QgsFeature, QgsGeometry, QgsProject, QgsRendererCategory, QgsSymbol,
                           QgsVectorLayer)
    from qgis.PyQt.QtGui import QColor


def _categorised_polygons(name, categories):
    layer = QgsVectorLayer("Polygon?crs=EPSG:4326&field=kind:string", name, "memory")
    features = []
    for i in range(categories):
        f = QgsFeature(layer.fields())
        x = 43.9 + 0.01 * i
        f.setGeometry(QgsGeometry.fromWkt(f"POLYGON(({x} 14.9,{x + 0.009} 14.9,{x + 0.009} 15.0,{x} 15.0,{x} 14.9))"))
        f.setAttributes([f"class {i}"])
        features.append(f)
    layer.dataProvider().addFeatures(features)
    layer.updateExtents()
    cats = [QgsRendererCategory(f"class {i}", QgsSymbol.defaultSymbol(layer.geometryType()), f"class {i}") for i in range(categories)]
    for i, cat in enumerate(cats):
        cat.symbol().setColor(QColor.fromHsv((i * 29) % 360, 160, 220))
    layer.setRenderer(QgsCategorizedSymbolRenderer("kind", cats))
    return layer


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "needs real qgis.core bindings")
class TestLayoutFitsItsFrames(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        why = _boot()
        if why:
            raise unittest.SkipTest(why)

    def setUp(self):
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)

    def _layers(self, count, categories):
        for n in range(count):
            QgsProject.instance().addMapLayer(_categorised_polygons(f"zones_{n}", categories))

    def _make(self, title="Fit test", **kw):
        from cartogen_ai.core.agent.tools.layout_tools import create_print_layout
        res = create_print_layout(title, confirmed=True, body_text="Finding", **kw)
        self.assertTrue(res.get("success"), res)
        self.addCleanup(lambda: QgsProject.instance().layoutManager().removeLayout(
            QgsProject.instance().layoutManager().layoutByName(res["layout_name"])))
        return res

    def test_a_small_legend_is_left_whole_with_its_plain_title(self):
        self._layers(1, 3)
        res = self._make(page_size="A4", page_orientation="Landscape")
        check = res["legend_check"]
        self.assertEqual(check["dropped"], 0, check)
        self.assertTrue(check["fits"], check)
        layout = QgsProject.instance().layoutManager().layoutByName(res["layout_name"])
        self.assertEqual(layout.itemById("LEGEND").title(), "Legend")

    def test_a_legend_with_far_more_entries_than_its_frame_is_fitted_and_says_so(self):
        for size, orientation in (("A4", "Landscape"), ("A3", "Portrait")):
            with self.subTest(size=size, orientation=orientation):
                QgsProject.instance().clear()
                self._layers(4, 14)
                res = self._make(page_size=size, page_orientation=orientation)
                check = res["legend_check"]
                self.assertTrue(check["fits"], check)                                   # never an entry cut by the frame
                self.assertLessEqual(check["content_mm"], check["frame_mm"] + 0.5, check)
                layout = QgsProject.instance().layoutManager().layoutByName(res["layout_name"])
                title = layout.itemById("LEGEND").title()
                if check["dropped"]:
                    self.assertIn("more layer", title)
                    self.assertTrue(any("legend:" in w for w in res.get("style_warnings", [])), res.get("style_warnings"))
                    self.assertEqual(len(res["legend_layers"]) + check["dropped"], 4)
                else:
                    self.assertEqual(title, "Legend")
                self.assertGreaterEqual(len(res["legend_layers"]), 1)

    def test_the_footer_check_reports_its_numbers_and_the_text_fits_the_page(self):
        self._layers(1, 3)
        for size, orientation in (("A4", "Landscape"), ("A3", "Portrait")):
            with self.subTest(size=size, orientation=orientation):
                res = self._make(title=f"Footer {size}", page_size=size, page_orientation=orientation)
                check = res["footer_check"]
                self.assertTrue(check["fits"], check)
                self.assertLessEqual(check["bottom_mm"], check["page_mm"], check)
                self.assertFalse(any("footer" in w for w in res.get("style_warnings", [])), res.get("style_warnings"))

    def test_the_layout_keeps_the_name_it_was_asked_for_and_the_old_spelling_still_finds_it(self):
        self._layers(1, 3)
        res = self._make(title="Big Map", page_size="A3", page_orientation="Landscape")
        self.assertEqual(res["layout_name"], "Big Map")
        from cartogen_ai.core.agent.tools._layout_names import lookup
        manager = QgsProject.instance().layoutManager()
        self.assertIsNotNone(lookup(manager, "Big Map"))
        self.assertIsNotNone(lookup(manager, "Layout_Big_Map"))


if __name__ == "__main__":
    unittest.main()
