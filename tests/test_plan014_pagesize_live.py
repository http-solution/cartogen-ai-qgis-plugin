"""PLAN-014 phase 2, real QGIS (CI live job; written without a QGIS install, so CI's first run is its first execution).

A layout for A3, A2 or A1 is the finished A4 layout scaled by one factor. Checked here, in both orientations: the page has the right size, no item
sticks out or overlaps (the layout geometry check), the map shows the SAME area as the A4 layout, text sizes grow by the factor, A4 is unchanged,
and the layout still exports to an image of the right proportions."""
import os
import tempfile
import unittest

from tests.test_network_units_live import QGIS_LIVE_AVAILABLE, _boot

if QGIS_LIVE_AVAILABLE:
    from qgis.core import QgsFeature, QgsGeometry, QgsProject, QgsVectorLayer
    from qgis.PyQt.QtGui import QImage

SIZES = {"a3": (297, 420), "a2": (420, 594), "a1": (594, 841)}


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "needs real qgis.core bindings")
class TestPageSizes(unittest.TestCase):
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
        layer = QgsVectorLayer("Point?crs=EPSG:4326&field=val:double", "clinics", "memory")
        feats = []
        for i in range(4):
            f = QgsFeature(layer.fields())
            f.setGeometry(QgsGeometry.fromWkt(f"POINT({44 + i * 0.5} 15)"))
            f.setAttributes([float(i)])
            feats.append(f)
        layer.dataProvider().addFeatures(feats)
        layer.updateExtents()
        QgsProject.instance().addMapLayer(layer)

    def _make(self, name, orientation, **kw):
        from cartogen_ai.core.agent.tools.layout_tools import create_print_layout
        res = create_print_layout(name, page_orientation=orientation, confirmed=True, **kw)
        self.assertTrue(res.get("success"), res)
        return res, QgsProject.instance().layoutManager().layoutByName(res["layout_name"])

    def test_a4_by_name_is_identical_to_the_default(self):
        _, default = self._make("Default", "Landscape")
        _, named = self._make("Named", "Landscape", page_size="A4")
        for item_id in ("MAP_MAIN", "TITLE", "LEGEND", "SCALEBAR", "FOOTER", "MAP_INFO"):
            a, b = default.itemById(item_id), named.itemById(item_id)
            self.assertEqual((a.x(), a.y(), a.rect().width(), a.rect().height()), (b.x(), b.y(), b.rect().width(), b.rect().height()), item_id)

    def test_each_size_and_orientation_scales_cleanly(self):
        from cartogen_ai.core.agent.tools.layout_item_tools import export_layout
        from cartogen_ai.core.agent.tools.layout_page_scale import scale_factor
        for orientation in ("Landscape", "Portrait"):
            _, base = self._make(f"Base {orientation}", orientation)
            base_extent = base.itemById("MAP_MAIN").extent()
            base_title = base.itemById("TITLE").textFormat().size()
            for key, (w, h) in SIZES.items():
                with self.subTest(size=key, orientation=orientation):
                    res, layout = self._make(f"{key} {orientation}", orientation, page_size=key.upper())
                    self.assertEqual(res["page_size"], key.upper())
                    page = layout.pageCollection().page(0).pageSize()
                    expected = (h, w) if orientation == "Landscape" else (w, h)
                    self.assertAlmostEqual(page.width(), expected[0], delta=0.5)
                    self.assertAlmostEqual(page.height(), expected[1], delta=0.5)
                    extent = layout.itemById("MAP_MAIN").extent()
                    for got, want in ((extent.xMinimum(), base_extent.xMinimum()), (extent.xMaximum(), base_extent.xMaximum()),
                                      (extent.yMinimum(), base_extent.yMinimum()), (extent.yMaximum(), base_extent.yMaximum())):
                        self.assertAlmostEqual(got, want, delta=abs(want) * 1e-6 + 1e-6, msg="the map must show the same area as A4")
                    k = scale_factor(key, orientation.lower())
                    self.assertAlmostEqual(layout.itemById("TITLE").textFormat().size(), base_title * k, delta=0.2)
                    out = os.path.join(self.tmp.name, f"{key}_{orientation}.png")
                    exported = export_layout(layout.name(), out, preset="draft", confirmed=True)
                    print(f"PLAN014 {key} {orientation}: problems={exported.get('layout_problems')} warnings={res.get('style_warnings')}")
                    self.assertTrue(exported.get("success"), exported)
                    self.assertEqual(exported.get("layout_problems", []), [], f"{key} {orientation}")
                    image = QImage(out)
                    self.assertFalse(image.isNull())
                    self.assertAlmostEqual(image.width() / image.height(), expected[0] / expected[1], delta=0.01)

    def test_an_unsupported_size_is_refused_and_nothing_is_built(self):
        from cartogen_ai.core.agent.tools.layout_tools import create_print_layout
        res = create_print_layout("Too small", page_size="A5", confirmed=True)
        self.assertIn("error", res, res)
        self.assertEqual(QgsProject.instance().layoutManager().printLayouts(), [])


if __name__ == "__main__":
    unittest.main()
