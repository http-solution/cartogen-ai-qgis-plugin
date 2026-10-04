# -*- coding: utf-8 -*-
"""Control flow of _edit_session.edit_command and _add_calculated_field with fake layers (GitHub #143, #144).
tests/test_edit_session_live.py runs the same behaviour in real QGIS."""
import unittest
from unittest.mock import MagicMock, patch

from cartogen_ai.core.agent.tools._edit_session import EditError, edit_command, set_value


def _layer(editable=False, start_ok=True, commit_ok=True):
    layer = MagicMock()
    layer.isEditable.return_value = editable
    layer.startEditing.return_value = start_ok
    layer.commitChanges.return_value = commit_ok
    layer.commitErrors.return_value = ["disk full"]
    return layer


class TestEditCommand(unittest.TestCase):
    def test_a_layer_that_is_not_editable_is_started_and_committed_by_this_call(self):
        layer = _layer()
        with edit_command(layer, "x") as owned:
            self.assertTrue(owned)
        layer.startEditing.assert_called_once()
        layer.beginEditCommand.assert_called_once_with("x")
        layer.endEditCommand.assert_called_once()
        layer.commitChanges.assert_called_once()

    def test_a_layer_the_user_is_already_editing_is_never_started_committed_or_rolled_back(self):
        layer = _layer(editable=True)
        with edit_command(layer, "x") as owned:
            self.assertFalse(owned)
        layer.startEditing.assert_not_called()
        layer.commitChanges.assert_not_called()
        layer.rollBack.assert_not_called()
        layer.endEditCommand.assert_called_once()

    def test_a_layer_that_cannot_be_edited_raises(self):
        layer = _layer(start_ok=False)
        with self.assertRaises(EditError):
            with edit_command(layer, "x"):
                pass
        layer.beginEditCommand.assert_not_called()

    def test_a_failure_inside_undoes_only_this_command_and_rolls_back_only_an_owned_session(self):
        owned_layer = _layer()
        owned_layer.isEditable.side_effect = [False, True]
        with self.assertRaises(RuntimeError):
            with edit_command(owned_layer, "x"):
                raise RuntimeError("boom")
        owned_layer.destroyEditCommand.assert_called_once()
        owned_layer.rollBack.assert_called_once()
        owned_layer.commitChanges.assert_not_called()

        users_layer = _layer(editable=True)
        with self.assertRaises(RuntimeError):
            with edit_command(users_layer, "x"):
                raise RuntimeError("boom")
        users_layer.destroyEditCommand.assert_called_once()
        users_layer.rollBack.assert_not_called()          # the user's other pending edits stay

    def test_a_rejected_commit_rolls_back_and_raises_with_the_providers_text(self):
        layer = _layer(commit_ok=False)
        layer.isEditable.side_effect = [False, True]
        with self.assertRaises(EditError) as ctx:
            with edit_command(layer, "x"):
                pass
        self.assertIn("disk full", str(ctx.exception))
        layer.rollBack.assert_called_once()

    def test_set_value_raises_when_the_write_is_refused(self):
        layer = MagicMock()
        layer.changeAttributeValue.return_value = False
        with self.assertRaises(EditError):
            set_value(layer, 1, 2, 3.0)
        layer.changeAttributeValue.return_value = True
        set_value(layer, 1, 2, 3.0)


class TestAddCalculatedField(unittest.TestCase):
    def _call(self, layer, **kw):
        from cartogen_ai.core.agent.tools import vector_tools as vt
        with patch.object(vt, "QGIS_AVAILABLE", True), \
             patch.object(vt, "QgsExpression", create=True) as expr_cls, \
             patch("cartogen_ai.core.agent.tools._edit_session.add_numeric_field", return_value=4):
            expr = expr_cls.return_value
            expr.hasParserError.return_value = kw.pop("parser_error", False)
            expr.parserErrorString.return_value = "syntax"
            expr.prepare.return_value = kw.pop("prepare_ok", True)
            # False when the expression is prepared, True once it is evaluated on a feature
            expr.hasEvalError.side_effect = [False, True, True] if kw.pop("eval_error", False) else [False] * 5
            expr.evalErrorString.return_value = "bad function"
            expr.evaluate.return_value = 7.0
            return vt._add_calculated_field(layer, "score", kw.pop("expression", "1+1"), **kw)

    def _feature_layer(self, **kw):
        layer = _layer(**kw)
        feat = MagicMock()
        feat.id.return_value = 11
        layer.getFeatures.return_value = [feat]
        layer.changeAttributeValue.return_value = True
        return layer

    def test_a_malformed_expression_changes_nothing(self):
        layer = self._feature_layer()
        res = self._call(layer, parser_error=True)
        self.assertIn("Invalid expression", res["error"])
        layer.startEditing.assert_not_called()

    def test_an_expression_that_cannot_be_prepared_changes_nothing(self):
        layer = self._feature_layer()
        res = self._call(layer, prepare_ok=False)
        self.assertIn("error", res)
        layer.startEditing.assert_not_called()

    def test_an_evaluation_error_aborts_the_whole_write(self):
        layer = self._feature_layer()
        layer.isEditable.side_effect = [False, True]
        res = self._call(layer, eval_error=True)
        self.assertIn("nothing was changed", res["error"])
        layer.rollBack.assert_called_once()
        layer.commitChanges.assert_not_called()

    def test_a_read_only_layer_is_an_error(self):
        layer = self._feature_layer(start_ok=False)
        self.assertIn("error", self._call(layer))

    def test_success_reports_the_count_and_is_committed_when_owned(self):
        layer = self._feature_layer()
        res = self._call(layer)
        self.assertTrue(res["success"])
        self.assertEqual(res["features_updated"], 1)
        layer.commitChanges.assert_called_once()
        self.assertNotIn("note", res)

    def test_on_a_layer_in_edit_mode_the_values_stay_in_the_users_session(self):
        layer = self._feature_layer(editable=True)
        res = self._call(layer)
        self.assertTrue(res["success"])
        self.assertIn("NOT saved", res["note"])
        layer.commitChanges.assert_not_called()


if __name__ == "__main__":
    unittest.main()
