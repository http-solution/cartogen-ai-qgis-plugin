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


if __name__ == "__main__":
    unittest.main()
