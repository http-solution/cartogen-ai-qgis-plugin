"""Master-list row DEF-8, the owner's two answers of 2026-11-22 ("yes make both fail closed"):
  - export: when QGIS cannot say whether features are selected, an export that did not say only_selected=False refuses instead of writing the whole layer;
  - egress gate: when QGIS is there but its settings cannot be read, the mode is ENFORCE and strict is ON (an unset setting on a fresh install is still OFF, and a
    missing QGIS is still OFF). Offline against fakes; not seen on a real QGIS failure."""
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

from cartogen_ai.core.agent.tools.export_tools import _write_vector
from cartogen_ai.core.models import egress_gate


class TestAnUnreadableSelectionRefusesTheExport(unittest.TestCase):
    def _run(self, only_selected, raises=True):
        import cartogen_ai.core.agent.tools.export_tools as mod
        writer = MagicMock()
        writer.writeAsVectorFormatV2.return_value = (0, "")
        writer.writeAsVectorFormatV3.return_value = (0, "", "", "")
        layer = MagicMock()
        layer.customProperty.return_value = ""
        if raises:
            layer.selectedFeatureCount.side_effect = RuntimeError("wrapped C/C++ object has been deleted")
        else:
            layer.selectedFeatureCount.return_value = 0
        with patch.object(mod, "QGIS_AVAILABLE", True), patch.object(mod, "QgsVectorFileWriter", writer, create=True), \
             patch.object(mod, "QgsCoordinateTransformContext", MagicMock(), create=True), patch.object(mod, "_VFW_NO_ERROR", 0):
            return _write_vector(layer, "/tmp/out.gpkg", "GPKG", only_selected=only_selected), writer

    def test_unspecified_and_true_both_refuse_and_nothing_is_written(self):
        for value in (None, True):
            res, writer = self._run(value)
            self.assertIn("could not say whether features are selected", res.get("error", ""), value)
            self.assertNotIn("success", res)
            writer.writeAsVectorFormatV3.assert_not_called()
            writer.writeAsVectorFormatV2.assert_not_called()

    def test_saying_only_selected_false_exports_the_full_layer_on_purpose(self):
        res, _ = self._run(False)
        self.assertTrue(res["success"])

    def test_a_readable_empty_selection_is_unchanged(self):
        res, _ = self._run(None, raises=False)
        self.assertTrue(res["success"])


def _qgis_with(settings_class):
    core = types.ModuleType("qgis.core")
    core.QgsSettings = settings_class
    return {"qgis": types.ModuleType("qgis"), "qgis.core": core}


class Unset:
    def value(self, key, default=None, **kw):
        return default


class Broken:
    def __init__(self):
        raise RuntimeError("settings store unavailable")


class TestAnUnreadableSettingTightensTheEgressGate(unittest.TestCase):
    def test_unreadable_settings_mean_enforce_and_strict_and_log_the_class_only(self):
        with patch.dict(sys.modules, _qgis_with(Broken)), patch("cartogen_ai.core.logger.log_event") as log:
            self.assertEqual(egress_gate.read_mode(), egress_gate.MODE_ENFORCE)
            self.assertTrue(egress_gate.read_strict())
        self.assertEqual(log.call_args.args[0], "egress_setting_unreadable")
        self.assertNotIn("unavailable", repr(log.call_args))

    def test_an_unset_setting_is_still_off_and_not_strict(self):
        with patch.dict(sys.modules, _qgis_with(Unset)):
            self.assertEqual(egress_gate.read_mode(), egress_gate.MODE_OFF)
            self.assertFalse(egress_gate.read_strict())

    def test_a_missing_qgis_is_still_off(self):
        with patch.dict(sys.modules, {"qgis": None, "qgis.core": None}):
            self.assertEqual(egress_gate.read_mode(), egress_gate.MODE_OFF)
            self.assertFalse(egress_gate.read_strict())

    def test_a_stored_value_is_still_honoured(self):
        class Stored:
            def value(self, key, default=None, **kw):
                return egress_gate.MODE_WARN if "mode" in key else default
        with patch.dict(sys.modules, _qgis_with(Stored)):
            self.assertEqual(egress_gate.read_mode(), egress_gate.MODE_WARN)


if __name__ == "__main__":
    unittest.main()
