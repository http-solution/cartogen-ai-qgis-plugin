# -*- coding: utf-8 -*-
"""The egress gate's lock on set_layer_sensitivity (docs/OLLAMA_ENFORCEMENT_GATE_SCOPE_2026-09-24.md):
when the gate is on, the model must not be able to lower a protected layer's tag itself, or the way
past a blocked call would be to re-tag the layer PUBLIC and retry. Gate off => unchanged behaviour."""
import unittest
from unittest.mock import MagicMock, patch

from cartogen_ai.core.agent.tools import TOOLS_SCHEMA
from cartogen_ai.core.agent.tools import sensitivity_tools as st
from cartogen_ai.core.models import egress_gate as eg


class _Base(unittest.TestCase):
    def _call(self, current, new, mode=eg.MODE_ENFORCE, strict=False, confirmed=False):
        layer = MagicMock()
        with patch.object(st, "QGIS_AVAILABLE", True), \
             patch.object(st, "_find_layer_by_name", return_value=layer), \
             patch.object(st._sens, "get_layer_sensitivity", return_value={"level": current, "reason": None}), \
             patch.object(st._sens, "set_layer_sensitivity", return_value=True) as mock_set, \
             patch.object(eg, "read_mode", return_value=mode), \
             patch.object(eg, "read_strict", return_value=strict):
            res = st.set_layer_sensitivity("beneficiaries", new, "why", confirmed=confirmed)
        return res, mock_set


class TestLoosenLock(_Base):
    def test_lowering_a_protected_layer_needs_confirmation(self):
        res, mock_set = self._call("SENSITIVE", "PUBLIC")
        self.assertEqual(res["status"], "PREVIEW_REQUIRED")
        self.assertTrue(res["is_destructive"])
        self.assertEqual(res["arguments"]["confirmed"], True)
        self.assertEqual(res["arguments"]["level"], "PUBLIC")
        mock_set.assert_not_called()

    def test_the_confirmed_call_goes_through(self):
        res, mock_set = self._call("SENSITIVE", "PUBLIC", confirmed=True)
        self.assertTrue(res["success"])
        mock_set.assert_called_once()

    def test_tightening_is_never_gated(self):
        res, mock_set = self._call("PUBLIC", "SENSITIVE")
        self.assertTrue(res["success"])
        mock_set.assert_called_once()

    def test_moving_between_open_levels_is_not_gated(self):
        res, _ = self._call("PUBLIC", "INTERNAL")
        self.assertTrue(res["success"])

    def test_untagged_to_public_is_free_unless_strict(self):
        res, _ = self._call(None, "PUBLIC", strict=False)
        self.assertTrue(res["success"])            # nothing was protecting it, so nothing to lose
        res, mock_set = self._call(None, "PUBLIC", strict=True)
        self.assertEqual(res["status"], "PREVIEW_REQUIRED")  # strict mode was blocking it
        mock_set.assert_not_called()

    def test_gate_off_behaves_exactly_as_before(self):
        res, mock_set = self._call("SENSITIVE", "PUBLIC", mode=eg.MODE_OFF)
        self.assertTrue(res["success"])
        mock_set.assert_called_once()

    def test_warn_mode_also_locks(self):
        res, _ = self._call("SENSITIVE", "PUBLIC", mode=eg.MODE_WARN)
        self.assertEqual(res["status"], "PREVIEW_REQUIRED")


class TestModelCannotSupplyConfirmed(unittest.TestCase):
    def test_confirmed_is_not_in_the_advertised_schema(self):
        # _real_execute_tool strips any argument not in the schema, so a model that passes
        # confirmed=True itself has it discarded; only the UI's confirm button injects it.
        for item in TOOLS_SCHEMA:
            fn = item.get("function", {})
            if fn.get("name") == "set_layer_sensitivity":
                self.assertNotIn("confirmed", fn["parameters"]["properties"])
                return
        self.fail("set_layer_sensitivity is not registered")


if __name__ == "__main__":
    unittest.main()
