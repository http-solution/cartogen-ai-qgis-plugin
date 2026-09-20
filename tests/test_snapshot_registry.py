# -*- coding: utf-8 -*-
"""Tests for agent/tools/_snapshot_registry.py -- the priority-subset
undo/rollback mechanism for MODIFY/DELETE tools, v1.7.0 workstream 2 of
docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md point 20. Mocks
QgsProject/QDomDocument directly (create=True, matching this suite's
convention for QGIS classes not otherwise exercised in the sandbox) since
this module only imports qgis.core/qgis.PyQt.QtXml inside its own
try/except."""
import unittest
from unittest.mock import patch, MagicMock

from cartogen_ai.core.agent.tools._snapshot_registry import (
    SNAPSHOT_REGISTRY, get_snapshot_fn, get_restore_fn,
    _snapshot_remove_layer, _restore_remove_layer,
    _snapshot_field_write, _restore_field_write,
    _snapshot_style, _restore_style,
)


class TestRegistryLookups(unittest.TestCase):
    def test_get_snapshot_fn_returns_none_for_unregistered_tool(self):
        self.assertIsNone(get_snapshot_fn("get_layers"))

    def test_get_snapshot_fn_returns_a_callable_for_registered_tool(self):
        self.assertTrue(callable(get_snapshot_fn("remove_layer")))

    def test_get_restore_fn_returns_none_for_unregistered_tool(self):
        self.assertIsNone(get_restore_fn("restore_layer", "get_layers"))

    def test_every_registered_entry_has_a_snapshot_and_restore_pair(self):
        for tool_name, (snap, restore) in SNAPSHOT_REGISTRY.items():
            self.assertTrue(callable(snap), tool_name)
            self.assertTrue(callable(restore), tool_name)

    def test_priority_subset_tools_are_all_registered(self):
        expected = {
            "remove_layer", "field_calculator", "calculate_area", "calculate_length",
            "apply_categorized_style", "apply_graduated_style", "apply_graduated_symbol_style",
            "set_dataset_status", "set_layer_sensitivity", "set_layer_confidence", "run_query",
        }
        self.assertEqual(set(SNAPSHOT_REGISTRY.keys()), expected)


class TestRemoveLayerSnapshot(unittest.TestCase):
    def test_returns_none_when_layer_not_found(self):
        with patch("cartogen_ai.core.agent.tools._snapshot_registry.QGIS_AVAILABLE", True), \
             patch("cartogen_ai.core.agent.tools._snapshot_registry.QgsProject", create=True) as mock_project:
            mock_project.instance.return_value.mapLayersByName.return_value = []
            result = _snapshot_remove_layer({"layer_name": "ghost"})
        self.assertIsNone(result)

    def test_clones_the_layer_before_removal(self):
        layer = MagicMock()
        clone = MagicMock()
        layer.clone.return_value = clone
        with patch("cartogen_ai.core.agent.tools._snapshot_registry.QGIS_AVAILABLE", True), \
             patch("cartogen_ai.core.agent.tools._snapshot_registry.QgsProject", create=True) as mock_project:
            mock_project.instance.return_value.mapLayersByName.return_value = [layer]
            result = _snapshot_remove_layer({"layer_name": "roads"})
        self.assertEqual(result, {"kind": "restore_layer", "clone": clone})
        layer.clone.assert_called_once()

    def test_restore_readds_the_clone(self):
        clone = MagicMock()
        with patch("cartogen_ai.core.agent.tools._snapshot_registry.QgsProject", create=True) as mock_project:
            ok = _restore_remove_layer({"kind": "restore_layer", "clone": clone})
        self.assertTrue(ok)
        mock_project.instance.return_value.addMapLayer.assert_called_once_with(clone)

    def test_restore_returns_false_on_exception(self):
        with patch("cartogen_ai.core.agent.tools._snapshot_registry.QgsProject", create=True) as mock_project:
            mock_project.instance.return_value.addMapLayer.side_effect = RuntimeError("dead object")
            ok = _restore_remove_layer({"kind": "restore_layer", "clone": MagicMock()})
        self.assertFalse(ok)


class TestFieldWriteSnapshot(unittest.TestCase):
    def _snapshot_fn(self):
        return _snapshot_field_write(lambda args: args.get("new_field"))

    def test_skips_snapshot_when_not_confirmed(self):
        snap = self._snapshot_fn()({"layer_name": "roads", "new_field": "x", "confirmed": False})
        self.assertIsNone(snap)

    def test_returns_none_when_layer_not_found(self):
        with patch("cartogen_ai.core.agent.tools._snapshot_registry.QGIS_AVAILABLE", True), \
             patch("cartogen_ai.core.agent.tools._snapshot_registry.QgsProject", create=True) as mock_project:
            mock_project.instance.return_value.mapLayersByName.return_value = []
            snap = self._snapshot_fn()({"layer_name": "ghost", "new_field": "x", "confirmed": True})
        self.assertIsNone(snap)

    def test_field_not_existing_yet_records_field_existed_false(self):
        layer = MagicMock()
        layer.fields.return_value.indexOf.return_value = -1
        with patch("cartogen_ai.core.agent.tools._snapshot_registry.QGIS_AVAILABLE", True), \
             patch("cartogen_ai.core.agent.tools._snapshot_registry.QgsProject", create=True) as mock_project:
            mock_project.instance.return_value.mapLayersByName.return_value = [layer]
            snap = self._snapshot_fn()({"layer_name": "roads", "new_field": "score", "confirmed": True})
        self.assertEqual(snap["field_existed"], False)
        self.assertEqual(snap["field_name"], "score")
        self.assertNotIn("values", snap)

    def test_existing_field_snapshots_every_feature_value(self):
        layer = MagicMock()
        layer.fields.return_value.indexOf.return_value = 0
        feat1, feat2 = MagicMock(), MagicMock()
        feat1.id.return_value = 1
        feat1.attribute.return_value = "old1"
        feat2.id.return_value = 2
        feat2.attribute.return_value = "old2"
        layer.getFeatures.return_value = [feat1, feat2]
        with patch("cartogen_ai.core.agent.tools._snapshot_registry.QGIS_AVAILABLE", True), \
             patch("cartogen_ai.core.agent.tools._snapshot_registry.QgsProject", create=True) as mock_project:
            mock_project.instance.return_value.mapLayersByName.return_value = [layer]
            snap = self._snapshot_fn()({"layer_name": "roads", "new_field": "score", "confirmed": True})
        self.assertTrue(snap["field_existed"])
        self.assertEqual(snap["values"], {1: "old1", 2: "old2"})

    def test_restore_deletes_field_that_did_not_exist_before(self):
        layer = MagicMock()
        layer.fields.return_value.indexOf.return_value = 5
        with patch("cartogen_ai.core.agent.tools._snapshot_registry.QGIS_AVAILABLE", True), \
             patch("cartogen_ai.core.agent.tools._snapshot_registry.QgsProject", create=True) as mock_project:
            mock_project.instance.return_value.mapLayer.return_value = layer
            ok = _restore_field_write({"layer_id": "id1", "field_name": "score", "field_existed": False})
        self.assertTrue(ok)
        layer.dataProvider.return_value.deleteAttributes.assert_called_once_with([5])
        layer.updateFields.assert_called_once()
        layer.commitChanges.assert_called_once()

    def test_restore_writes_back_old_values_for_existing_field(self):
        layer = MagicMock()
        layer.fields.return_value.indexOf.return_value = 3
        with patch("cartogen_ai.core.agent.tools._snapshot_registry.QGIS_AVAILABLE", True), \
             patch("cartogen_ai.core.agent.tools._snapshot_registry.QgsProject", create=True) as mock_project:
            mock_project.instance.return_value.mapLayer.return_value = layer
            ok = _restore_field_write({"layer_id": "id1", "field_name": "score", "field_existed": True, "values": {1: "old1", 2: "old2"}})
        self.assertTrue(ok)
        layer.changeAttributeValue.assert_any_call(1, 3, "old1")
        layer.changeAttributeValue.assert_any_call(2, 3, "old2")
        layer.commitChanges.assert_called_once()

    def test_restore_rolls_back_on_exception(self):
        layer = MagicMock()
        layer.fields.return_value.indexOf.return_value = 3
        layer.isEditable.return_value = True
        layer.changeAttributeValue.side_effect = RuntimeError("boom")
        with patch("cartogen_ai.core.agent.tools._snapshot_registry.QGIS_AVAILABLE", True), \
             patch("cartogen_ai.core.agent.tools._snapshot_registry.QgsProject", create=True) as mock_project:
            mock_project.instance.return_value.mapLayer.return_value = layer
            ok = _restore_field_write({"layer_id": "id1", "field_name": "score", "field_existed": True, "values": {1: "old1"}})
        self.assertFalse(ok)
        layer.rollBack.assert_called_once()

    def test_restore_returns_false_when_layer_gone(self):
        with patch("cartogen_ai.core.agent.tools._snapshot_registry.QGIS_AVAILABLE", True), \
             patch("cartogen_ai.core.agent.tools._snapshot_registry.QgsProject", create=True) as mock_project:
            mock_project.instance.return_value.mapLayer.return_value = None
            ok = _restore_field_write({"layer_id": "id1", "field_name": "score", "field_existed": True, "values": {}})
        self.assertFalse(ok)


class TestStyleSnapshot(unittest.TestCase):
    def test_returns_none_when_layer_not_found(self):
        with patch("cartogen_ai.core.agent.tools._snapshot_registry.QGIS_AVAILABLE", True), \
             patch("cartogen_ai.core.agent.tools._snapshot_registry.QgsProject", create=True) as mock_project:
            mock_project.instance.return_value.mapLayersByName.return_value = []
            snap = _snapshot_style({"layer_name": "ghost"})
        self.assertIsNone(snap)

    def test_exports_style_xml_via_qdomdocument(self):
        layer = MagicMock()
        fake_doc = MagicMock()
        fake_doc.toString.return_value = "<qgis>...</qgis>"
        with patch("cartogen_ai.core.agent.tools._snapshot_registry.QGIS_AVAILABLE", True), \
             patch("cartogen_ai.core.agent.tools._snapshot_registry.QgsProject", create=True) as mock_project, \
             patch("cartogen_ai.core.agent.tools._snapshot_registry.QDomDocument", create=True, return_value=fake_doc):
            mock_project.instance.return_value.mapLayersByName.return_value = [layer]
            snap = _snapshot_style({"layer_name": "roads"})
        self.assertEqual(snap, {"kind": "restore_style", "layer_id": layer.id.return_value, "xml": "<qgis>...</qgis>"})
        layer.exportNamedStyle.assert_called_once_with(fake_doc)

    def test_restore_imports_style_and_triggers_repaint_on_success(self):
        layer = MagicMock()
        layer.importNamedStyle.return_value = (True, "")
        fake_doc = MagicMock()
        with patch("cartogen_ai.core.agent.tools._snapshot_registry.QGIS_AVAILABLE", True), \
             patch("cartogen_ai.core.agent.tools._snapshot_registry.QgsProject", create=True) as mock_project, \
             patch("cartogen_ai.core.agent.tools._snapshot_registry.QDomDocument", create=True, return_value=fake_doc):
            mock_project.instance.return_value.mapLayer.return_value = layer
            ok = _restore_style({"layer_id": "id1", "xml": "<qgis>...</qgis>"})
        self.assertTrue(ok)
        fake_doc.setContent.assert_called_once_with("<qgis>...</qgis>")
        layer.importNamedStyle.assert_called_once_with(fake_doc)
        layer.triggerRepaint.assert_called_once()

    def test_restore_returns_false_when_import_fails(self):
        layer = MagicMock()
        layer.importNamedStyle.return_value = (False, "bad xml")
        with patch("cartogen_ai.core.agent.tools._snapshot_registry.QGIS_AVAILABLE", True), \
             patch("cartogen_ai.core.agent.tools._snapshot_registry.QgsProject", create=True) as mock_project, \
             patch("cartogen_ai.core.agent.tools._snapshot_registry.QDomDocument", create=True):
            mock_project.instance.return_value.mapLayer.return_value = layer
            ok = _restore_style({"layer_id": "id1", "xml": "bad"})
        self.assertFalse(ok)
        layer.triggerRepaint.assert_not_called()


class TestPropertySnapshotShapes(unittest.TestCase):
    """set_dataset_status/set_layer_sensitivity/set_layer_confidence/run_query
    all share the generic property-snapshot shape -- exercised via the real
    registered entries rather than the private factory functions directly,
    since that's what agent_orchestrator.py actually calls."""

    def _run(self, tool_name, layer, arguments):
        snapshot_fn, _ = SNAPSHOT_REGISTRY[tool_name]
        with patch("cartogen_ai.core.agent.tools._snapshot_registry.QGIS_AVAILABLE", True), \
             patch("cartogen_ai.core.agent.tools._snapshot_registry.QgsProject", create=True) as mock_project:
            mock_project.instance.return_value.mapLayersByName.return_value = [layer] if layer else []
            return snapshot_fn(arguments)

    def test_set_layer_sensitivity_snapshots_customproperty(self):
        layer = MagicMock()
        layer.customProperty.return_value = ""
        snap = self._run("set_layer_sensitivity", layer, {"layer_name": "roads"})
        self.assertEqual(snap["old_value"], "")
        layer.customProperty.assert_called_once_with("cartogen_ai/sensitivity", "")

    def test_set_layer_confidence_snapshots_customproperty(self):
        layer = MagicMock()
        layer.customProperty.return_value = '{"level": "OBSERVED"}'
        snap = self._run("set_layer_confidence", layer, {"layer_name": "roads"})
        self.assertEqual(snap["old_value"], '{"level": "OBSERVED"}')

    def test_set_dataset_status_snapshots_customproperty(self):
        layer = MagicMock()
        layer.customProperty.return_value = ""
        snap = self._run("set_dataset_status", layer, {"layer_name": "roads"})
        self.assertEqual(snap["old_value"], "")

    def test_run_query_snapshots_subset_string(self):
        layer = MagicMock()
        layer.subsetString.return_value = '"val" > 5'
        snap = self._run("run_query", layer, {"layer_name": "roads"})
        self.assertEqual(snap["old_value"], '"val" > 5')

    def test_returns_none_when_layer_missing(self):
        snap = self._run("run_query", None, {"layer_name": "ghost"})
        self.assertIsNone(snap)

    def test_restore_writes_back_old_subset_string(self):
        _, restore_fn = SNAPSHOT_REGISTRY["run_query"]
        layer = MagicMock()
        with patch("cartogen_ai.core.agent.tools._snapshot_registry.QGIS_AVAILABLE", True), \
             patch("cartogen_ai.core.agent.tools._snapshot_registry.QgsProject", create=True) as mock_project:
            mock_project.instance.return_value.mapLayer.return_value = layer
            ok = restore_fn({"layer_id": "id1", "old_value": '"val" > 5'})
        self.assertTrue(ok)
        layer.setSubsetString.assert_called_once_with('"val" > 5')

    def test_restore_writes_back_old_customproperty(self):
        _, restore_fn = SNAPSHOT_REGISTRY["set_layer_sensitivity"]
        layer = MagicMock()
        with patch("cartogen_ai.core.agent.tools._snapshot_registry.QGIS_AVAILABLE", True), \
             patch("cartogen_ai.core.agent.tools._snapshot_registry.QgsProject", create=True) as mock_project:
            mock_project.instance.return_value.mapLayer.return_value = layer
            ok = restore_fn({"layer_id": "id1", "old_value": ""})
        self.assertTrue(ok)
        layer.setCustomProperty.assert_called_once_with("cartogen_ai/sensitivity", "")


if __name__ == "__main__":
    unittest.main()
