"""Direct tests for tools/_sensitivity_notes.py and the tools/map_tools.py compatibility module (audit finding 11: no test named either).

_sensitivity_notes decides whether a person is warned that a layer they are about to export, chart or package is RESTRICTED/SENSITIVE; a
silent failure here means a missing privacy warning, so the "never raises, never gates" promise is pinned."""
import unittest
from unittest import mock

from cartogen_ai.core.agent.tools import _sensitivity_notes as notes

_EFFECTIVE = "cartogen_ai.core.agent.tools._sensitivity_notes.effective_sensitivity"


class _Layer:
    def __init__(self, name):
        self._name = name

    def name(self):
        return self._name


class TestProtectedLayerNotes(unittest.TestCase):
    def _run(self, records, layers=None, what="it goes in the file."):
        layers = layers or [_Layer(n) for n in records]
        with mock.patch(_EFFECTIVE, side_effect=lambda layer, _all: records[layer.name()]):
            return notes.protected_layer_notes(layers, what, all_layers=[])

    def test_a_tagged_restricted_layer_gets_one_note_with_its_reason(self):
        out = self._run({"clinics": {"level": "RESTRICTED", "reason": "patient data"}})
        self.assertEqual(out, ["'clinics' is tagged RESTRICTED (patient data): it goes in the file."])

    def test_a_tag_without_a_reason_has_no_empty_brackets(self):
        out = self._run({"camps": {"level": "SENSITIVE", "reason": None}})
        self.assertEqual(out, ["'camps' is tagged SENSITIVE: it goes in the file."])

    def test_a_derived_layer_names_the_layer_it_came_from(self):
        out = self._run({"buffer_1": {"level": "SENSITIVE", "reason": "x", "derived_from": "camps"}})
        self.assertEqual(out, ["'buffer_1' is derived from 'camps' (SENSITIVE): it goes in the file."])

    def test_public_untagged_and_unknown_levels_get_no_note(self):
        out = self._run({"roads": {"level": "PUBLIC"}, "admin": {"level": None}, "odd": {"level": "WHATEVER"}})
        self.assertEqual(out, [])

    def test_only_the_protected_layers_are_listed_in_order(self):
        out = self._run({"a": {"level": "SENSITIVE"}, "b": {"level": None}, "c": {"level": "RESTRICTED"}})
        self.assertEqual([n.split("'")[1] for n in out], ["a", "c"])

    def test_an_unreadable_tag_counts_as_no_tag_and_does_not_raise(self):
        with mock.patch(_EFFECTIVE, side_effect=RuntimeError("bad tag")):
            self.assertEqual(notes.protected_layer_notes([_Layer("x")], "w", all_layers=[]), [])

    def test_no_layers_or_none_is_an_empty_list(self):
        self.assertEqual(notes.protected_layer_notes(None, "w", all_layers=[]), [])
        self.assertEqual(notes.protected_layer_notes([], "w", all_layers=[]), [])

    def test_without_all_layers_a_missing_project_gives_an_empty_lookup_not_an_error(self):
        # Offline there is no QgsProject; the helper must fall back to [] and still answer.
        seen = {}

        def fake(layer, all_layers):
            seen["all"] = all_layers
            return {"level": "SENSITIVE"}

        with mock.patch(_EFFECTIVE, side_effect=fake):
            out = notes.protected_layer_notes([_Layer("p")], "w")
        self.assertEqual(len(out), 1)
        self.assertIsInstance(seen["all"], list)


class TestMapToolsCompatibilityModule(unittest.TestCase):
    def test_it_re_exports_the_same_objects_as_vector_tools(self):
        from cartogen_ai.core.agent.tools import map_tools, vector_tools
        for name in ("zoom_to_layer", "toggle_visibility", "_extent_to_canvas_crs"):
            self.assertIs(getattr(map_tools, name), getattr(vector_tools, name), name)
        self.assertEqual(sorted(map_tools.__all__), ["_extent_to_canvas_crs", "toggle_visibility", "zoom_to_layer"])


if __name__ == "__main__":
    unittest.main()
