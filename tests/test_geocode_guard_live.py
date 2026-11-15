"""Live run of the geocoding refusal (tracker item 1.26) on real QGIS layers: a layer tagged SENSITIVE or RESTRICTED stops geocode_batch and geocode_and_enrich before any lookup, whether it is named as the source or only
recognised by its values; open and untagged layers go ahead. The lookup itself is replaced by a counter, so no network is used. Written without a QGIS install: CI's first run is its first execution."""
import unittest
from unittest import mock

try:
    from qgis.core import QgsFeature, QgsGeometry, QgsProject, QgsVectorLayer
    LIVE = True
except ImportError:
    LIVE = False


def _boot():
    from tests.test_chat_widget_live import _boot_qgis
    _boot_qgis()


def _layer(name, addresses, level=None):
    layer = QgsVectorLayer("Point?crs=EPSG:4326&field=address:string&field=cases:integer", name, "memory")
    feats = []
    for i, text in enumerate(addresses):
        f = QgsFeature(layer.fields())
        f.setGeometry(QgsGeometry.fromWkt(f"POINT({i} {i})"))
        f.setAttributes([text, i])
        feats.append(f)
    layer.dataProvider().addFeatures(feats)
    QgsProject.instance().addMapLayer(layer)
    if level:
        from cartogen_ai.core.models import sensitivity
        sensitivity.set_layer_sensitivity(layer, level, "test")
    return layer


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestGeocodeRefusal(unittest.TestCase):
    def setUp(self):
        _boot()
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        from cartogen_ai.core.agent.tools import system_tools
        self.calls = []

        def fake(name):
            self.calls.append(name)
            return {"location": name, "lat": 1.0, "lon": 2.0}
        patcher = mock.patch.object(system_tools, "_geocode_one", fake)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.tools = system_tools

    def test_text_that_matches_a_sensitive_layer_is_refused_before_any_lookup(self):
        _layer("case_addresses", ["12 Main Street", "4 Oak Road"], "SENSITIVE")
        result = self.tools.geocode_batch(["12 main street"])
        self.assertEqual(result["status"], "GEOCODING_REFUSED_PROTECTED")
        self.assertEqual(result["layers"], ["case_addresses"])
        self.assertIn("1 of the 1 text(s) match", result["error"])
        self.assertEqual(self.calls, [])

    def test_a_restricted_layer_is_refused_for_a_single_lookup_too(self):
        _layer("clients", ["7 Elm Close"], "RESTRICTED")
        result = self.tools.geocode_and_enrich("7 Elm Close")
        self.assertEqual(result["status"], "GEOCODING_REFUSED_PROTECTED")
        self.assertEqual(self.calls, [])

    def test_naming_a_protected_layer_as_the_source_refuses_even_when_the_texts_do_not_match(self):
        _layer("case_addresses", ["12 Main Street"], "SENSITIVE")
        result = self.tools.geocode_batch(["Somewhere Else"], source_layer="case_addresses")
        self.assertEqual(result["status"], "GEOCODING_REFUSED_PROTECTED")
        self.assertIn("named as the source", result["error"])
        self.assertEqual(self.calls, [])

    def test_an_open_layer_goes_ahead(self):
        _layer("clinics", ["Al Amal Clinic"], "PUBLIC")
        result = self.tools.geocode_batch(["Al Amal Clinic"], source_layer="clinics")
        self.assertTrue(result.get("success"), result)
        self.assertEqual(self.calls, ["Al Amal Clinic"])

    def test_an_untagged_layer_goes_ahead_under_the_default_setting(self):
        _layer("plain", ["Town Hall"])
        result = self.tools.geocode_and_enrich("Town Hall")
        self.assertEqual(result["lat"], 1.0)
        self.assertEqual(self.calls, ["Town Hall"])

    def test_a_protected_layer_elsewhere_in_the_project_does_not_block_unrelated_text(self):
        _layer("case_addresses", ["12 Main Street"], "SENSITIVE")
        result = self.tools.geocode_batch(["Amman"])
        self.assertTrue(result.get("success"), result)
        self.assertEqual(self.calls, ["Amman"])

    def test_retagging_the_layer_open_lifts_the_refusal(self):
        layer = _layer("case_addresses", ["12 Main Street"], "SENSITIVE")
        self.assertEqual(self.tools.geocode_batch(["12 Main Street"])["status"], "GEOCODING_REFUSED_PROTECTED")
        from cartogen_ai.core.models import sensitivity
        sensitivity.set_layer_sensitivity(layer, "PUBLIC", "released copy")
        self.assertTrue(self.tools.geocode_batch(["12 Main Street"]).get("success"))

    def test_an_unknown_source_layer_is_an_error_not_a_pass(self):
        result = self.tools.geocode_batch(["Amman"], source_layer="no_such_layer")
        self.assertIn("is not a layer in this project", result["error"])
        self.assertEqual(self.calls, [])

    def test_the_protected_layer_is_never_changed(self):
        layer = _layer("case_addresses", ["12 Main Street"], "SENSITIVE")
        before = [(f.id(), f["address"]) for f in layer.getFeatures()]
        self.tools.geocode_batch(["12 Main Street"])
        self.assertEqual([(f.id(), f["address"]) for f in layer.getFeatures()], before)
        self.assertFalse(layer.isEditable())
        from cartogen_ai.core.models import sensitivity
        self.assertEqual(sensitivity.get_layer_sensitivity(layer)["level"], "SENSITIVE")


if __name__ == "__main__":
    unittest.main()
