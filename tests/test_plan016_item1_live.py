"""PLAN-016 item 1, real QGIS (CI live job; written without a QGIS install, so CI's first run is its first execution): an export re-reads the
layout's profile file, so a requirement added after the layout was built applies (A29 of the first rc50 hand run)."""
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
class TestProfileReread(unittest.TestCase):
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

    def _write(self, profile):
        with open(os.path.join(self.profiles, "sign.json"), "w", encoding="utf-8") as handle:
            json.dump(profile, handle)

    def test_the_profile_name_is_stored_on_the_layout(self):
        res = self._make({"page_size": "A4"})
        layout = QgsProject.instance().layoutManager().layoutByName(res["layout_name"])
        self.assertEqual(layout.customProperty("cartogen_ai/profile_name"), "sign")

    def test_a_requirement_added_after_the_layout_was_built_blocks_publication(self):
        res = self._make({"page_size": "A4", "sign_off": {"prepared_by": "A. Analyst"}})
        self._write({"page_size": "A4", "require_sign_off": True, "sign_off": {"prepared_by": "A. Analyst"}})
        refused = self._publish(res)
        self.assertIn("error", refused, refused)
        self.assertTrue(any("sign-off" in p for p in refused["problems"]), refused)
        self.assertFalse(os.path.exists(os.path.join(self.tmp.name, "out.png")))

    def test_a_review_added_to_the_file_does_not_pass_a_layout_whose_footer_says_draft(self):
        res = self._make({"require_sign_off": True, "sign_off": {"prepared_by": "A. Analyst"}})
        self._write({"require_sign_off": True, "sign_off": FULL})
        self.assertIn("error", self._publish(res))

    def test_a_requirement_removed_from_the_file_no_longer_blocks(self):
        res = self._make({"require_sign_off": True, "sign_off": {"prepared_by": "A. Analyst"}})
        self._write({"page_size": "A4"})
        self.assertTrue(self._publish(res).get("success"))

    def test_a_deleted_profile_file_falls_back_to_the_stored_copy_and_says_so(self):
        res = self._make({"require_sign_off": True, "sign_off": {"prepared_by": "A. Analyst"}})
        os.remove(os.path.join(self.profiles, "sign.json"))
        refused = self._publish(res)                                   # the stored copy still requires a review
        self.assertIn("error", refused, refused)
        from cartogen_ai.core.agent.tools.layout_item_tools import export_layout
        done = export_layout(res["layout_name"], os.path.join(self.tmp.name, "plain.png"), confirmed=True)
        self.assertTrue(done.get("success"), done)
        self.assertIn("could not be re-read", done.get("profile_note", ""))


if __name__ == "__main__":
    unittest.main()
