"""PLAN-014 phase 3b, real QGIS (CI live job; written without a QGIS install, so CI's first run is its first execution): a profile's footer
lines and sign-off line reach the footer, and require_sign_off blocks a publication export until a named, dated review is in the profile."""
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
class TestSignOffOnLayouts(unittest.TestCase):
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

    def test_footer_lines_and_the_sign_off_line_are_in_the_footer_before_the_disclaimer(self):
        res = self._make({"footer_lines": ["Contact: info@example.org"], "sign_off": FULL})
        layout = QgsProject.instance().layoutManager().layoutByName(res["layout_name"])
        lines = layout.itemById("FOOTER").text().split("\n")
        self.assertIn("Contact: info@example.org", lines)
        self.assertIn("Prepared by A. Analyst | Reviewed by B. Reviewer on 2026-10-20 | Status: Reviewed", lines)
        self.assertLess(lines.index("Contact: info@example.org"), len(lines) - 1)                # the disclaimer is still last
        self.assertFalse(any("footer" in w for w in res.get("style_warnings", [])), res.get("style_warnings"))   # the map gives up height instead
        self.assertGreater(layout.itemById("MAP_MAIN").rect().height(), 60)                                      # and keeps most of it

    def test_with_no_reviewer_the_footer_says_draft_not_reviewed(self):
        res = self._make({"sign_off": {"prepared_by": "A. Analyst"}})
        layout = QgsProject.instance().layoutManager().layoutByName(res["layout_name"])
        self.assertIn("Prepared by A. Analyst | Status: Draft - not reviewed", layout.itemById("FOOTER").text())

    def test_a_footer_with_extra_lines_stays_on_the_page_and_free_of_geometry_problems(self):
        from cartogen_ai.core.agent.tools.layout_geometry_checks import layout_geometry_problems
        res = self._make({"footer_lines": ["Line one", "Line two", "Line three"], "sign_off": FULL}, page_size="A3")
        layout = QgsProject.instance().layoutManager().layoutByName(res["layout_name"])
        self.assertEqual(layout_geometry_problems(layout), [])
        self.assertFalse(any("footer" in w for w in res.get("style_warnings", [])), res.get("style_warnings"))

    def test_required_sign_off_blocks_publication_until_the_profile_has_a_review(self):
        res = self._make({"require_sign_off": True, "sign_off": {"prepared_by": "A. Analyst"}})
        refused = self._publish(res)
        self.assertIn("error", refused, refused)
        self.assertTrue(any("sign-off" in p for p in refused["problems"]), refused)
        self.assertFalse(os.path.exists(os.path.join(self.tmp.name, "out.png")))
        card = self._publish(res, override_reason="internal copy")                                 # a reason turns it into the confirm card
        self.assertEqual(card.get("status"), "PREVIEW_REQUIRED", card)

    def test_a_reviewed_profile_publishes_without_a_sign_off_problem(self):
        res = self._make({"require_sign_off": True, "sign_off": FULL})
        done = self._publish(res)
        self.assertTrue(done.get("success"), done)

    def test_without_require_sign_off_a_draft_still_publishes(self):
        res = self._make({"sign_off": {"prepared_by": "A. Analyst"}})
        self.assertTrue(self._publish(res).get("success"))


if __name__ == "__main__":
    unittest.main()
