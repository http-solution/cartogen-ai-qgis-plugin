"""PLAN-021 WP-E (#425), no QGIS needed: undoing add_field takes the new column away while it is empty and refuses, with a reason, once it holds values."""
import unittest
from unittest.mock import MagicMock, patch

from cartogen_ai.core.agent.tools import _snapshot_registry as reg
from cartogen_ai.core.agent.tools import transaction_tools as tt


def _layer(values, field_names=("name", "notes")):
    layer = MagicMock()
    layer.id.return_value = "layer1"
    layer.fields.return_value.indexOf.side_effect = lambda n: list(field_names).index(n) if n in field_names else -1
    features = []
    for value in values:
        feature = MagicMock()
        feature.attribute.return_value = value
        features.append(feature)
    layer.getFeatures.return_value = features
    return layer


class TestFieldHoldsValues(unittest.TestCase):
    def test_all_null_or_empty_is_empty(self):
        self.assertFalse(reg.field_holds_values(_layer([None, "NULL", ""]), 1))

    def test_one_real_value_is_enough(self):
        self.assertTrue(reg.field_holds_values(_layer([None, "x"]), 1))
        self.assertTrue(reg.field_holds_values(_layer([0]), 1))        # zero is a value

    def test_a_failure_reading_counts_as_holding_values(self):
        layer = _layer([])
        layer.getFeatures.side_effect = RuntimeError("provider error")
        self.assertTrue(reg.field_holds_values(layer, 1))


class TestSnapshotAndRestore(unittest.TestCase):
    def test_a_field_that_already_exists_has_nothing_to_undo(self):
        with patch.object(reg, "_find_layer", return_value=_layer([])):
            self.assertIsNone(reg._snapshot_added_field({"layer_name": "towns", "field_name": "notes"}))

    def test_a_new_field_is_recorded(self):
        with patch.object(reg, "_find_layer", return_value=_layer([], ("name",))):
            snap = reg._snapshot_added_field({"layer_name": "towns", "field_name": "notes"})
        self.assertEqual(snap["kind"], "restore_added_field")
        self.assertEqual(snap["field_name"], "notes")

    def test_an_empty_field_is_removed(self):
        layer = _layer([None, None])
        layer.deleteAttribute.return_value = True
        snap = {"kind": "restore_added_field", "layer_id": "layer1", "field_name": "notes"}
        with patch.object(reg, "_layer_by_id", return_value=layer), patch("cartogen_ai.core.agent.tools._edit_session.edit_command"):
            self.assertTrue(reg._restore_added_field(snap))
        layer.deleteAttribute.assert_called_once_with(1)

    def test_a_filled_field_is_kept_and_the_reason_is_given(self):
        layer = _layer(["hello", None])
        snap = {"kind": "restore_added_field", "layer_id": "layer1", "field_name": "notes"}
        with patch.object(reg, "_layer_by_id", return_value=layer):
            self.assertFalse(reg._restore_added_field(snap))
        layer.deleteAttribute.assert_not_called()
        self.assertIn("now holds values", snap["refusal"])
        self.assertIn("delete the field", snap["refusal"])

    def test_a_field_already_gone_counts_as_undone(self):
        snap = {"kind": "restore_added_field", "layer_id": "layer1", "field_name": "gone"}
        with patch.object(reg, "_layer_by_id", return_value=_layer([], ("name",))):
            self.assertTrue(reg._restore_added_field(snap))

    def test_it_is_registered_for_the_tool(self):
        self.assertIn("add_field", reg.SNAPSHOT_REGISTRY)
        self.assertIs(reg.get_restore_fn("restore_added_field", "add_field"), reg._restore_added_field)


class TestTheUndoToolPassesTheReasonOn(unittest.TestCase):
    def test_a_refusal_reaches_the_user_instead_of_a_generic_failure(self):
        log = MagicMock()
        undo = {"kind": "restore_added_field", "tool_name": "add_field", "layer_id": "layer1", "field_name": "notes"}
        entry = {"name": "add_field", "index": 0, "undo": undo}
        layer = _layer(["hello"])
        with patch.object(tt, "QGIS_AVAILABLE", True), patch.dict(tt._BOUND, {"log": log}), patch.object(reg, "_layer_by_id", return_value=layer):
            result = tt._undo_via_snapshot(entry, undo, confirmed=True)
        self.assertIn("now holds values", result["error"])
        log.mark_undone.assert_not_called()

    def test_the_tool_description_says_the_limit(self):
        from cartogen_ai.core.agent.tools import TOOLS_SCHEMA
        desc = next(t["function"]["description"] for t in TOOLS_SCHEMA if t["function"]["name"] == "undo_last_operation")
        self.assertIn("add_field", desc)
        self.assertIn("only while it is still empty", desc)


if __name__ == "__main__":
    unittest.main()
