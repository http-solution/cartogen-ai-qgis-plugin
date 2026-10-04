# -*- coding: utf-8 -*-
"""Live-QGIS test for H4: reading forecast rows (including real QDate values) from a layer. Written without a QGIS install."""
import datetime
import unittest

try:
    from qgis.core import QgsFeature, QgsProject, QgsVectorLayer
    from qgis.PyQt.QtCore import QDate
    QGIS_LIVE_AVAILABLE = True
except ImportError:
    QGIS_LIVE_AVAILABLE = False


def _boot_qgis():
    from tests.test_chat_widget_live import _boot_qgis as _shared_boot
    return _shared_boot()


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "requires real QGIS")
class TestEvaluateForecastTriggerOnALayer(unittest.TestCase):
    def setUp(self):
        _boot_qgis()
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)

    def _layer(self):
        layer = QgsVectorLayer("None?field=district:string&field=q:double&field=day:date", "forecast", "memory")
        today = datetime.date.today()
        feats = []
        for district, q, offset in (("A", 150.0, 2), ("A", 90.0, 3), ("B", 150.0, 30), ("B", 20.0, 1)):
            f = QgsFeature(layer.fields())
            d = today + datetime.timedelta(days=offset)
            f.setAttributes([district, q, QDate(d.year, d.month, d.day)])
            feats.append(f)
        layer.dataProvider().addFeatures(feats)
        QgsProject.instance().addMapLayer(layer)
        return layer

    def test_qdate_values_and_the_lead_window(self):
        from cartogen_ai.core.agent.tools.trigger_tools import evaluate_forecast_trigger
        self._layer()
        res = evaluate_forecast_trigger("forecast", "q", threshold=100, unit_field="district", date_field="day", lead_days=7)
        self.assertTrue(res.get("success"), res)
        units = {u["unit"]: u for u in res["units"]}
        self.assertTrue(units["A"]["activated"])
        self.assertFalse(units["B"]["activated"])     # its 150 forecast is 30 days away
        self.assertEqual(res["activated_count"], 1)
        self.assertIn("q >= 100", res["rule"])

    def test_unknown_layer_and_field(self):
        from cartogen_ai.core.agent.tools.trigger_tools import evaluate_forecast_trigger
        self._layer()
        self.assertIn("error", evaluate_forecast_trigger("ghost", "q", threshold=1))
        self.assertIn("error", evaluate_forecast_trigger("forecast", "nope", threshold=1))


if __name__ == "__main__":
    unittest.main()
