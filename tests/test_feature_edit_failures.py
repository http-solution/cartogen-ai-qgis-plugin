# -*- coding: utf-8 -*-
"""Feature-adding tools must not report success when the provider refuses the save (GitHub #144, audit F08)."""
import unittest
from unittest.mock import MagicMock, patch

from cartogen_ai.core.agent.tools import _edit_session as es


def _layer(editable=False, start_ok=True, commit_ok=True):
    layer = MagicMock()
    state = {"editing": editable}

    def start():
        state["editing"] = start_ok
        return start_ok
    layer.isEditable.side_effect = lambda: state["editing"]
    layer.startEditing.side_effect = start
    layer.commitChanges.return_value = commit_ok
    layer.commitErrors.return_value = ["disk full"]
    return layer


class TestFeatureEditHelpers(unittest.TestCase):
    def test_a_layer_that_will_not_edit_raises(self):
        with self.assertRaises(es.EditError):
            es.begin_feature_edits(_layer(start_ok=False))

    def test_a_refused_commit_rolls_back_and_raises_with_the_providers_text(self):
        layer = _layer(commit_ok=False)
        owned = es.begin_feature_edits(layer)
        self.assertTrue(owned)
        with self.assertRaises(es.EditError) as ctx:
            es.finish_feature_edits(layer, owned)
        self.assertIn("disk full", str(ctx.exception))
        layer.rollBack.assert_called_once()

    def test_a_layer_the_user_is_editing_is_never_committed_by_the_tool(self):
        layer = _layer(editable=True)
        owned = es.begin_feature_edits(layer)
        self.assertFalse(owned)
        es.finish_feature_edits(layer, owned)
        layer.commitChanges.assert_not_called()
        layer.startEditing.assert_not_called()


class TestHazardRefresh(unittest.TestCase):
    def test_a_refused_commit_keeps_the_old_features_and_raises(self):
        from cartogen_ai.core.agent.tools import hazard_monitoring_tools as hm
        layer = _layer(commit_ok=False)
        layer.getFeatures.return_value = []
        layer.fields.return_value = []
        with self.assertRaises(es.EditError):
            hm._replace_point_features(layer, [])
        layer.rollBack.assert_called_once()

    def test_a_good_commit_returns_the_count(self):
        from cartogen_ai.core.agent.tools import hazard_monitoring_tools as hm
        layer = _layer()
        layer.getFeatures.return_value = []
        layer.fields.return_value = []
        with patch.object(hm, "QgsFeature", create=True, return_value=MagicMock()):
            self.assertEqual(hm._replace_point_features(layer, [{"__geom__": object()}, {"__geom__": object()}]), 2)


class TestHazardRefreshIsAtomic(unittest.TestCase):
    """Audit A05: a rejected deletion or insertion must undo the whole refresh, not commit a half-empty layer."""

    def _layer(self, delete_ok=True, add_results=()):
        layer = _layer()
        feature = MagicMock()
        feature.id.return_value = 7
        layer.getFeatures.return_value = [feature]
        layer.fields.return_value = []
        layer.deleteFeatures.return_value = delete_ok
        layer.addFeature.side_effect = list(add_results) or [True, True]
        return layer

    def _refresh(self, layer, rows=2):
        from cartogen_ai.core.agent.tools import hazard_monitoring_tools as hm
        with patch.object(hm, "QgsFeature", create=True, return_value=MagicMock()):
            return hm._replace_point_features(layer, [{"__geom__": object()} for _ in range(rows)])

    def test_a_rejected_deletion_undoes_the_command_and_rolls_back(self):
        layer = self._layer(delete_ok=False)
        with self.assertRaises(es.EditError):
            self._refresh(layer)
        layer.destroyEditCommand.assert_called()
        layer.rollBack.assert_called()
        layer.commitChanges.assert_not_called()
        layer.addFeature.assert_not_called()

    def test_a_rejected_insertion_undoes_everything_and_never_commits(self):
        layer = self._layer(add_results=[True, False])
        with self.assertRaises(es.EditError) as ctx:
            self._refresh(layer)
        self.assertIn("2 of 2", str(ctx.exception))
        layer.destroyEditCommand.assert_called()
        layer.rollBack.assert_called()
        layer.commitChanges.assert_not_called()

    def test_a_clean_refresh_commits_once_and_counts_every_row(self):
        layer = self._layer(add_results=[True, True])
        self.assertEqual(self._refresh(layer), 2)
        layer.commitChanges.assert_called_once()
        layer.destroyEditCommand.assert_not_called()

    def test_in_a_users_edit_session_the_tool_undoes_only_its_own_command(self):
        layer = _layer(editable=True)
        layer.getFeatures.return_value = []
        layer.fields.return_value = []
        layer.addFeature.return_value = False
        with self.assertRaises(es.EditError):
            self._refresh(layer, rows=1)
        layer.destroyEditCommand.assert_called()
        layer.rollBack.assert_not_called()          # the user's own pending edits are not rolled back
        layer.commitChanges.assert_not_called()


if __name__ == "__main__":
    unittest.main()
