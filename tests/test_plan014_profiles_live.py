"""PLAN-014 phase 2b, real QGIS (CI live job; written without a QGIS install, so CI's first run is its first execution): a layout made with a
profile takes its page size, orientation, preset, file name pattern and required elements from the file; explicit arguments beat the profile."""
import datetime
import json
import os
import tempfile
import unittest
from unittest.mock import patch

from tests.test_network_units_live import QGIS_LIVE_AVAILABLE, _boot

if QGIS_LIVE_AVAILABLE:
    from qgis.core import QgsFeature, QgsGeometry, QgsProject, QgsVectorLayer

PROFILE = {"profile_version": 1, "name": "weekly", "page_size": "A3", "orientation": "portrait", "export_preset": "web",
           "file_name_pattern": "{layout}-{date}", "required_elements": ["MAP_MAIN", "TITLE", "BODY_TEXT"]}


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "needs real qgis.core bindings")
class TestProfilesOnLayouts(unittest.TestCase):
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
        self._write("weekly", PROFILE)
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

    def _write(self, name, data):
        with open(os.path.join(self.profiles, name + ".json"), "w", encoding="utf-8") as handle:
            json.dump(data, handle)

    def _make(self, title="Prof test", **kw):
        from cartogen_ai.core.agent.tools.layout_tools import create_print_layout
        return create_print_layout(title, confirmed=True, **kw)

    def test_the_profile_sets_page_size_and_orientation(self):
        res = self._make(profile="weekly")
        self.assertTrue(res.get("success"), res)
        self.assertEqual((res["page_size"], res["orientation"]), ("A3", "Portrait"))
        layout = QgsProject.instance().layoutManager().layoutByName(res["layout_name"])
        page = layout.pageCollection().page(0).pageSize()
        self.assertAlmostEqual(page.width(), 297, delta=0.5)
        self.assertAlmostEqual(page.height(), 420, delta=0.5)

    def test_an_explicit_argument_beats_the_profile(self):
        res = self._make(profile="weekly", page_size="A2", page_orientation="Landscape")
        self.assertTrue(res.get("success"), res)
        self.assertEqual((res["page_size"], res["orientation"]), ("A2", "Landscape"))

    def test_export_uses_the_stored_preset_and_file_name_pattern_and_checks_the_required_elements(self):
        from cartogen_ai.core.agent.tools.layout_item_tools import export_layout
        res = self._make(profile="weekly")
        folder = os.path.join(self.tmp.name, "out")
        os.makedirs(folder)
        exported = export_layout(res["layout_name"], folder, output_format="png", confirmed=True)
        self.assertTrue(exported.get("success"), exported)
        self.assertEqual(exported["dpi"], 150)                                                    # the 'web' preset of the profile
        self.assertEqual(os.path.basename(exported["output_path"]), f"{res['layout_name']}-{datetime.date.today().isoformat()}.png")
        print(f"PLAN014 profile export: missing={exported.get('missing_elements')} problems={exported.get('layout_problems')}")
        self.assertIn("summary text", exported.get("missing_elements", []))                       # BODY_TEXT is required and no body_text was given
        self.assertNotIn("legend", exported.get("missing_elements", []))                          # not required by this profile

    def test_with_the_summary_text_the_required_elements_are_all_present(self):
        from cartogen_ai.core.agent.tools.layout_item_tools import export_layout
        res = self._make(profile="weekly", body_text="Finding one")
        exported = export_layout(res["layout_name"], os.path.join(self.tmp.name, "x.png"), confirmed=True)
        self.assertTrue(exported.get("success"), exported)
        self.assertNotIn("missing_elements", exported)

    def test_an_unknown_profile_is_refused_and_lists_the_available_ones(self):
        res = self._make(profile="nope")
        self.assertIn("error", res, res)
        self.assertIn("Available: weekly", res["error"])
        self.assertEqual(QgsProject.instance().layoutManager().printLayouts(), [])

    def test_an_invalid_profile_file_is_refused_with_its_problems(self):
        self._write("broken", {"page_size": "A5", "watermark": "x.png"})
        res = self._make(profile="broken")
        self.assertIn("error", res, res)
        self.assertIn("page_size must be one of", res["error"])
        self.assertIn("'watermark'", res["error"])
        self.assertEqual(QgsProject.instance().layoutManager().printLayouts(), [])

    def test_a_layout_without_a_profile_is_as_before(self):
        res = self._make()
        self.assertEqual((res["page_size"], res["orientation"]), ("A4", "Landscape"))


if __name__ == "__main__":
    unittest.main()
