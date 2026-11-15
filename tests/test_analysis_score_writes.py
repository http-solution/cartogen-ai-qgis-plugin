"""The analysis tools' output-field writers go through the layer's edit buffer, keyed by feature id (GitHub #293, follow-up to #143/#144/#159).
Fake layers and stub qgis modules, so this runs without QGIS; the real provider behaviour is not exercised here."""
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

from cartogen_ai.core.agent.tools import analysis_tools as at


class _QVariant:
    Double = 6
    String = 10


def _qgis_stubs():
    core = types.ModuleType("qgis.core")
    core.QgsField = lambda name, kind: (name, kind)
    qt = types.ModuleType("qgis.PyQt.QtCore")
    qt.QVariant = _QVariant
    pyqt = types.ModuleType("qgis.PyQt")
    pyqt.QtCore = qt
    qgis = types.ModuleType("qgis")
    qgis.core, qgis.PyQt = core, pyqt
    return {"qgis": qgis, "qgis.core": core, "qgis.PyQt": pyqt, "qgis.PyQt.QtCore": qt}


def _layer(editable=False, commit_ok=True, change_ok=True, field_names=()):
    layer = MagicMock()
    names = list(field_names)
    layer.isEditable.return_value = editable
    layer.startEditing.return_value = True
    layer.commitChanges.return_value = commit_ok
    layer.commitErrors.return_value = ["read-only source"]
    layer.changeAttributeValue.return_value = change_ok
    layer.addAttribute.side_effect = lambda f: names.append(f[0]) or True
    fields = MagicMock()
    fields.indexOf.side_effect = lambda n: names.index(n) if n in names else -1
    layer.fields.return_value = fields
    return layer


# Two units that share a name keep separate rows, because rows carry the feature id and a unique label.
ROWS = [{"unit": "Al-Dhale", "__fid__": 1}, {"unit": "Al-Dhale [#2]", "__fid__": 2}, {"unit": "Taiz", "__fid__": 3}]
SCORES = [{"unit": "Al-Dhale", "severity_score": 0.9}, {"unit": "Al-Dhale [#2]", "severity_score": 0.1}]


class TestScoreWrites(unittest.TestCase):
    def setUp(self):
        p = patch.dict(sys.modules, _qgis_stubs())
        p.start()
        self.addCleanup(p.stop)

    def test_values_go_to_the_matching_feature_ids_through_the_edit_buffer(self):
        layer = _layer()
        self.assertIsNone(at._write_scores_to_layer(layer, ROWS, SCORES, "sev"))
        layer.addAttribute.assert_called_once()
        layer.dataProvider.assert_not_called()                    # nothing bypasses the edit buffer
        calls = {c.args[0]: c.args[2] for c in layer.changeAttributeValue.call_args_list}
        self.assertEqual(calls, {1: 0.9, 2: 0.1})                  # same-name units are not merged
        layer.beginEditCommand.assert_called_once()
        layer.commitChanges.assert_called_once()

    def test_a_layer_the_user_is_editing_is_not_committed_or_rolled_back(self):
        layer = _layer(editable=True)
        self.assertIsNone(at._write_scores_to_layer(layer, ROWS, SCORES, "sev"))
        layer.commitChanges.assert_not_called()
        layer.rollBack.assert_not_called()

    def test_a_refused_value_write_is_reported_and_undone(self):
        layer = _layer(change_ok=False)
        layer.isEditable.side_effect = [False, True, True]
        error = at._write_scores_to_layer(layer, ROWS, SCORES, "sev")
        self.assertIn("Could not write scores into 'sev'", error)
        layer.destroyEditCommand.assert_called_once()
        layer.rollBack.assert_called_once()
        layer.commitChanges.assert_not_called()

    def test_a_rejected_commit_returns_the_providers_text(self):
        layer = _layer(commit_ok=False)
        layer.isEditable.side_effect = [False, True, True]
        error = at._write_scores_to_layer(layer, ROWS, SCORES, "sev")
        self.assertIn("read-only source", error)

    def test_the_presence_gap_status_is_a_text_field(self):
        layer = _layer()
        self.assertIsNone(at._write_presence_gap_status_to_layer(layer, ROWS, [{"unit": "Taiz"}], [{"unit": "Al-Dhale"}], [], "gap_status"))
        self.assertEqual(layer.addAttribute.call_args.args[0], ("gap_status", _QVariant.String))
        values = {c.args[0]: c.args[2] for c in layer.changeAttributeValue.call_args_list}
        self.assertEqual(values, {3: "gap", 1: "covered"})

    def test_population_and_damage_writers_use_the_same_path(self):
        for fn, key in ((at._write_population_to_layer, "population"), (at._write_damage_severity_to_layer, "severity_score")):
            layer = _layer()
            self.assertIsNone(fn(layer, ROWS, [{"unit": "Taiz", key: 5.0}], "out"))
            layer.dataProvider.assert_not_called()
            layer.changeAttributeValue.assert_called_once_with(3, 0, 5.0)

    def test_an_existing_non_numeric_field_is_refused_not_overwritten(self):
        layer = _layer(field_names=["sev"])
        field = MagicMock()
        field.isNumeric.return_value = False
        layer.fields.return_value.at.return_value = field
        error = at._write_scores_to_layer(layer, ROWS, SCORES, "sev")
        self.assertIn("non-numeric", error)
        layer.changeAttributeValue.assert_not_called()


if __name__ == "__main__":
    unittest.main()
