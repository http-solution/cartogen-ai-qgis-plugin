"""PLAN-016 item 5, real QGIS (CI live job; written without a QGIS install, so CI's first run is its first execution): the footer is sized from
the text measured in its real font, and the growth and the layout geometry check use that one measure."""
import json
import os
import tempfile
import unittest
from unittest.mock import patch

from tests.test_network_units_live import QGIS_LIVE_AVAILABLE, _boot

if QGIS_LIVE_AVAILABLE:
    from qgis.core import QgsFeature, QgsGeometry, QgsProject, QgsVectorLayer

FULL = {"prepared_by": "A. Analyst", "reviewed_by": "B. Reviewer", "review_date": "2026-10-20", "status": "Reviewed"}


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "needs real qgis.core bindings")
class TestFooterMeasured(unittest.TestCase):
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
        with open(os.path.join(self.profiles, "sign.json"), "w", encoding="utf-8") as handle:
            json.dump(profile, handle)
        from cartogen_ai.core.agent.tools.layout_tools import create_print_layout
        res = create_print_layout("Sign test", confirmed=True, profile="sign", body_text="Finding", **kw)
        self.assertTrue(res.get("success"), res)
        return res

    def _publish(self, res, **kw):
        from cartogen_ai.core.agent.tools.layout_item_tools import export_layout
        return export_layout(res["layout_name"], os.path.join(self.tmp.name, "out.png"), purpose="publication", **kw)

    def test_wide_glyphs_need_more_height_than_the_character_estimate_says(self):
        """The A22 finding: the estimate assumes half-em glyphs; 'W' is nearly a full em wide in any font."""
        from qgis.PyQt.QtGui import QFont
        from cartogen_ai.core.agent.tools.layout_style import FOOTER_PAD_MM, footer_height_mm, measured_text_height_mm
        text = "W" * 400
        measured = measured_text_height_mm(text, 100.0, QFont(), 7.0) + FOOTER_PAD_MM
        self.assertGreater(measured, footer_height_mm(text, 100.0, 7.0))

    def test_the_measure_scales_with_the_font_size_and_the_width(self):
        from qgis.PyQt.QtGui import QFont
        from cartogen_ai.core.agent.tools.layout_style import measured_text_height_mm
        text = "Sources: " + "district clinics; " * 20
        small = measured_text_height_mm(text, 120.0, QFont(), 7.0)
        self.assertGreater(measured_text_height_mm(text, 120.0, QFont(), 14.0), small * 1.5)
        self.assertGreater(measured_text_height_mm(text, 60.0, QFont(), 7.0), small * 1.5)
        self.assertGreater(measured_text_height_mm("a\nb\nc", 120.0, QFont(), 7.0), measured_text_height_mm("a", 120.0, QFont(), 7.0) * 2)

    def test_the_footer_box_holds_its_measured_text_and_the_check_agrees(self):
        from cartogen_ai.core.agent.tools.layout_geometry_checks import layout_geometry_problems
        from cartogen_ai.core.agent.tools.layout_style import footer_needed_mm
        for size, orientation in (("A4", "Landscape"), ("A3", "Portrait")):
            with self.subTest(size=size, orientation=orientation):
                res = self._make({"footer_lines": ["Line one of the footer", "Line two of the footer", "Line three of the footer"], "sign_off": FULL},
                                 page_size=size, page_orientation=orientation)
                layout = QgsProject.instance().layoutManager().layoutByName(res["layout_name"])
                footer = layout.itemById("FOOTER")
                self.assertGreaterEqual(footer.rect().height() + 0.8, footer_needed_mm(footer), "the box is shorter than its measured text")
                self.assertEqual(layout_geometry_problems(layout), [])
                self.assertFalse(any("footer" in w for w in res.get("style_warnings", [])), res.get("style_warnings"))
                QgsProject.instance().layoutManager().removeLayout(layout)


if __name__ == "__main__":
    unittest.main()
