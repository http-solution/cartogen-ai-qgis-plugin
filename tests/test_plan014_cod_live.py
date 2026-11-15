"""PLAN-014 phase 3c, real QGIS (CI live job; written without a QGIS install, so CI's first run is its first execution): a profile's COD credit
wording leads the credits line of the footer, and an export of a layout whose boundary layer has duplicate P-codes reports it."""
import json
import os
import tempfile
import unittest
from unittest.mock import patch

from tests.test_network_units_live import QGIS_LIVE_AVAILABLE, _boot

if QGIS_LIVE_AVAILABLE:
    from qgis.core import QgsFeature, QgsGeometry, QgsProject, QgsVectorLayer

CREDIT = "Boundaries: COD, see source metadata"


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "needs real qgis.core bindings")
class TestCodOnLayouts(unittest.TestCase):
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

    def _layer(self, codes):
        layer = QgsVectorLayer("Polygon?crs=EPSG:4326&field=admin2_pcode:string", "districts", "memory")
        for i, code in enumerate(codes):
            f = QgsFeature(layer.fields())
            f.setGeometry(QgsGeometry.fromWkt(f"POLYGON(({44 + i} 15,{45 + i} 15,{45 + i} 16,{44 + i} 16,{44 + i} 15))"))
            f.setAttributes([code])
            layer.dataProvider().addFeatures([f])
        layer.updateExtents()
        QgsProject.instance().addMapLayer(layer)

    def _make(self, profile):
        with open(os.path.join(self.profiles, "cod.json"), "w", encoding="utf-8") as handle:
            json.dump(profile, handle)
        from cartogen_ai.core.agent.tools.layout_tools import create_print_layout
        res = create_print_layout("COD test", confirmed=True, profile="cod", body_text="Finding")
        self.assertTrue(res.get("success"), res)
        return res, QgsProject.instance().layoutManager().layoutByName(res["layout_name"])

    def test_the_cod_credit_leads_the_credits_line(self):
        self._layer(["YE1201", "YE1202"])
        _, layout = self._make({"cod_boundaries": True, "cod_credit": CREDIT})
        lines = layout.itemById("FOOTER").text().split("\n")
        credit_lines = [x for x in lines if x.startswith("Credits: ")]
        self.assertEqual(len(credit_lines), 1, lines)
        self.assertTrue(credit_lines[0].startswith("Credits: " + CREDIT), credit_lines[0])

    def test_without_the_flag_there_is_no_cod_credit(self):
        self._layer(["YE1201", "YE1202"])
        _, layout = self._make({"page_size": "A4"})
        self.assertNotIn(CREDIT, layout.itemById("FOOTER").text())

    def test_duplicate_pcodes_are_reported_on_export_when_the_flag_is_on(self):
        from cartogen_ai.core.agent.tools.layout_item_tools import export_layout
        self._layer(["YE1201", "YE1201", "YE1202"])
        res, _ = self._make({"cod_boundaries": True, "cod_credit": CREDIT})
        done = export_layout(res["layout_name"], os.path.join(self.tmp.name, "a.png"), confirmed=True)
        self.assertTrue(done.get("success"), done)
        self.assertEqual(done["pcode_findings"][0]["layer"], "districts")
        self.assertEqual(done["pcode_findings"][0]["duplicates"], 1)

    def test_clean_pcodes_or_no_flag_report_nothing(self):
        from cartogen_ai.core.agent.tools.layout_item_tools import export_layout
        self._layer(["YE1201", "YE1202"])
        res, _ = self._make({"cod_boundaries": True, "cod_credit": CREDIT})
        self.assertNotIn("pcode_findings", export_layout(res["layout_name"], os.path.join(self.tmp.name, "b.png"), confirmed=True))
        QgsProject.instance().clear()
        self._layer(["YE1201", "YE1201"])
        res, _ = self._make({"page_size": "A4"})
        self.assertNotIn("pcode_findings", export_layout(res["layout_name"], os.path.join(self.tmp.name, "c.png"), confirmed=True))


if __name__ == "__main__":
    unittest.main()
