# -*- coding: utf-8 -*-
"""Live-QGIS tests for H6 aggregate_survey_indicator. Written without a QGIS install: CI's first run is their first execution."""
import unittest

try:
    from qgis.core import QgsFeature, QgsProject, QgsVectorLayer
    QGIS_LIVE_AVAILABLE = True
except ImportError:
    QGIS_LIVE_AVAILABLE = False


def _boot_qgis():
    from tests.test_chat_widget_live import _boot_qgis as _shared_boot
    return _shared_boot()


def _survey():
    layer = QgsVectorLayer("None?field=district:string&field=water:string&field=wt:double", "survey", "memory")
    rows = ([("North", "Yes", 2.0)] * 20 + [("North", "No", 1.0)] * 20 + [("South", "Yes", 1.0)] * 5
            + [("North", "Yes", -1.0), ("North", "dk", 1.0)])
    feats = []
    for district, water, wt in rows:
        f = QgsFeature(layer.fields())
        f.setAttributes([district, water, wt])
        feats.append(f)
    layer.dataProvider().addFeatures(feats)
    return layer


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "requires real QGIS")
class TestAggregateSurveyIndicator(unittest.TestCase):
    def setUp(self):
        _boot_qgis()
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        QgsProject.instance().addMapLayer(_survey())

    def test_weighted_share_suppression_and_exclusions(self):
        from cartogen_ai.core.agent.tools.survey_tools import aggregate_survey_indicator
        res = aggregate_survey_indicator("survey", "district", "water", weight_field="wt", min_n=30)
        self.assertTrue(res.get("success"), res)
        north = next(g for g in res["groups"] if g["group"] == "North")
        south = next(g for g in res["groups"] if g["group"] == "South")
        self.assertAlmostEqual(north["estimate"], 0.6667, places=4)
        self.assertTrue(south["suppressed"])
        self.assertEqual(res["groups_suppressed"], 1)
        self.assertEqual(res["excluded_records"], {"missing_or_invalid_value": 1, "invalid_weight": 1})

    def test_results_table_leaves_out_suppressed_groups(self):
        from cartogen_ai.core.agent.tools.survey_tools import aggregate_survey_indicator
        res = aggregate_survey_indicator("survey", "district", "water", weight_field="wt", output_table_name="survey_results")
        self.assertEqual(res.get("table_layer"), "survey_results")
        table = QgsProject.instance().mapLayersByName("survey_results")[0]
        self.assertEqual([f["group"] for f in table.getFeatures()], ["North"])

    def test_bad_fields_are_errors(self):
        from cartogen_ai.core.agent.tools.survey_tools import aggregate_survey_indicator
        self.assertIn("error", aggregate_survey_indicator("ghost", "district", "water"))
        self.assertIn("error", aggregate_survey_indicator("survey", "nope", "water"))
        self.assertIn("error", aggregate_survey_indicator("survey", "district", "water", weight_field="nope"))


if __name__ == "__main__":
    unittest.main()
