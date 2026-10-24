"""PLAN-014 phase 3a, real QGIS (CI live job; written without a QGIS install, so CI's first run is its first execution): a profile's logo,
masthead colours and font reach the layout, a missing logo or font warns instead of failing, and the logo never overlaps the title."""
import json
import os
import tempfile
import unittest
from unittest.mock import patch

from tests.test_network_units_live import QGIS_LIVE_AVAILABLE, _boot

if QGIS_LIVE_AVAILABLE:
    from qgis.core import QgsFeature, QgsGeometry, QgsLayoutExporter, QgsProject, QgsVectorLayer
    from qgis.PyQt.QtCore import QSize
    from qgis.PyQt.QtGui import QColor, QFontDatabase, QImage


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "needs real qgis.core bindings")
class TestBrandingOnLayouts(unittest.TestCase):
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
        self.profiles = os.path.join(self.tmp.name, "profiles")
        os.makedirs(self.profiles)
        image = QImage(60, 30, QImage.Format.Format_RGB32)
        image.fill(QColor("#ff0000"))
        self.assertTrue(image.save(os.path.join(self.profiles, "mark.png")))
        patcher = patch("cartogen_ai.core.agent.tools.map_profiles.profile_dirs", lambda: [self.profiles])
        patcher.start()
        self.addCleanup(patcher.stop)
        layer = QgsVectorLayer("Point?crs=EPSG:4326&field=val:double", "clinics", "memory")
        f = QgsFeature(layer.fields())
        f.setGeometry(QgsGeometry.fromWkt("POINT(44 15)"))
        f.setAttributes([1.0])
        layer.dataProvider().addFeatures([f])
        layer.updateExtents()
        QgsProject.instance().addMapLayer(layer)

    def _make(self, profile, **kw):
        with open(os.path.join(self.profiles, "brand.json"), "w", encoding="utf-8") as handle:
            json.dump(profile, handle)
        from cartogen_ai.core.agent.tools.layout_tools import create_print_layout
        res = create_print_layout("Brand test", confirmed=True, profile="brand", **kw)
        self.assertTrue(res.get("success"), res)
        return res, QgsProject.instance().layoutManager().layoutByName(res["layout_name"])

    def test_the_logo_is_added_beside_the_title_and_is_drawn(self):
        res, layout = self._make({"logo_path": "mark.png", "masthead_colour": "#2b5d8a"})
        logo, title = layout.itemById("LOGO"), layout.itemById("TITLE")
        self.assertIsNotNone(logo, res)
        self.assertTrue(logo.picturePath().endswith("mark.png"))
        self.assertLessEqual(logo.x() + logo.rect().width(), title.x() + 0.01)                 # left of the title, no overlap
        image = QgsLayoutExporter(layout).renderPageToImage(0, QSize(1170, 827))
        cx = int((logo.x() + logo.rect().width() / 2) / 297 * image.width())
        cy = int((logo.y() + logo.rect().height() / 2) / 210 * image.height())
        self.assertGreater(QColor(image.pixel(cx, cy)).red(), 200, "the red logo should be painted at the centre of the logo box")
        self.assertLess(QColor(image.pixel(cx, cy)).green(), 80)

    def test_the_logo_keeps_every_size_and_orientation_free_of_geometry_problems(self):
        from cartogen_ai.core.agent.tools.layout_geometry_checks import layout_geometry_problems
        for size in ("A4", "A3"):
            for orientation in ("Landscape", "Portrait"):
                with self.subTest(size=size, orientation=orientation):
                    _, layout = self._make({"logo_path": "mark.png", "logo_position": "right"}, page_size=size, page_orientation=orientation)
                    self.assertIsNotNone(layout.itemById("LOGO"))
                    self.assertEqual(layout_geometry_problems(layout), [])
                    QgsProject.instance().layoutManager().removeLayout(layout)

    def test_masthead_colour_and_a_readable_text_colour_reach_the_title(self):
        _, layout = self._make({"masthead_colour": "#2b5d8a", "masthead_text_colour": "#ffffff"})
        title = layout.itemById("TITLE")
        self.assertEqual(title.backgroundColor().name(), "#2b5d8a")
        self.assertEqual(title.textFormat().color().name(), "#ffffff")

    def test_an_unreadable_text_colour_is_replaced_with_a_warning(self):
        res, layout = self._make({"masthead_colour": "#2b5d8a", "masthead_text_colour": "#2f6a9a"})
        self.assertEqual(layout.itemById("TITLE").textFormat().color().name(), "#ffffff")
        self.assertTrue(any("hard to read" in w for w in res.get("style_warnings", [])), res.get("style_warnings"))

    def test_a_missing_logo_file_warns_and_builds_the_layout_without_it(self):
        res, layout = self._make({"logo_path": "absent.png"})
        self.assertIsNone(layout.itemById("LOGO"))
        self.assertTrue(any("logo" in w for w in res.get("style_warnings", [])), res.get("style_warnings"))

    def test_an_installed_font_is_applied_and_a_missing_one_warns(self):
        family = QFontDatabase.families()[0]
        res, layout = self._make({"font_family": family})
        self.assertEqual(layout.itemById("TITLE").textFormat().font().family(), family)
        self.assertFalse(any("font" in w for w in res.get("style_warnings", [])), res.get("style_warnings"))
        res, layout = self._make({"font_family": "No Such Typeface Xyz"})
        self.assertTrue(any("not installed" in w for w in res.get("style_warnings", [])), res.get("style_warnings"))

    def test_no_branding_fields_leaves_the_layout_as_before(self):
        _, layout = self._make({"page_size": "A4"})
        self.assertIsNone(layout.itemById("LOGO"))


if __name__ == "__main__":
    unittest.main()
