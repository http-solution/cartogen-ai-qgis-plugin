"""Owner decision 2026-11-22 (master-list row DEF-8): a protection record that is STORED but cannot be read counts as protected, not as untagged.

Two cases, both offline against a fake layer that keeps its custom properties as text:
  - a sensitivity tag that is present but corrupt (invalid JSON, not an object, an unknown level) reads as SENSITIVE, with a reason that says so;
  - a lineage history that is stored but corrupt reads as an 'unreadable' entry, and a layer with unknown ancestry is protected; writing a new
    step keeps the corrupt text under a second property instead of dropping the earlier sources.
An explicit tag set afterwards (PUBLIC, say) wins, which is how a person clears it."""
import json
import unittest
from unittest.mock import patch

from cartogen_ai.core.agent import lineage, protection
from cartogen_ai.core.models import sensitivity as sens


class FakeLayer:
    def __init__(self, name, props=None):
        self._name, self.props = name, dict(props or {})

    def name(self):
        return self._name

    def id(self):
        return "id_" + self._name

    def customProperty(self, key, default=""):
        return self.props.get(key, default)

    def setCustomProperty(self, key, value):
        self.props[key] = value


def tagged(raw, name="clinics"):
    return FakeLayer(name, {sens.SENSITIVITY_PROPERTY_KEY: raw})


class TestACorruptSensitivityTagIsProtected(unittest.TestCase):
    def test_invalid_json_not_an_object_and_an_unknown_level_all_read_as_sensitive(self):
        for raw in ("{not json", "[1, 2]", '"SENSITIVE"', json.dumps({"level": "TOP_SECRET"}), json.dumps({"reason": "no level"})):
            with patch("cartogen_ai.core.logger.log_event") as log:
                record = sens.get_layer_sensitivity(tagged(raw))
            self.assertEqual(record["level"], "SENSITIVE", raw)
            self.assertIn("could not be read", record["reason"], raw)
            self.assertEqual(log.call_args.args[0], "sensitivity_tag_unreadable", raw)

    def test_the_log_names_why_but_never_the_stored_text(self):
        with patch("cartogen_ai.core.logger.log_event") as log:
            sens.get_layer_sensitivity(tagged("{secret client list"))
        self.assertNotIn("secret", repr(log.call_args))

    def test_a_good_tag_an_empty_value_and_no_layer_are_unchanged(self):
        self.assertEqual(sens.get_layer_sensitivity(tagged(json.dumps({"level": "PUBLIC", "reason": "open data"}))), {"level": "PUBLIC", "reason": "open data"})
        self.assertEqual(sens.get_layer_sensitivity(tagged("")), {"level": None, "reason": None})
        self.assertEqual(sens.get_layer_sensitivity(tagged("   ")), {"level": None, "reason": None})
        self.assertEqual(sens.get_layer_sensitivity(FakeLayer("never_tagged")), {"level": None, "reason": None})
        self.assertEqual(sens.get_layer_sensitivity(None), {"level": None, "reason": None})

    def test_tagging_the_layer_again_clears_a_corrupt_tag(self):
        layer = tagged("{not json")
        self.assertTrue(sens.set_layer_sensitivity(layer, "PUBLIC", "checked by hand"))
        self.assertEqual(sens.get_layer_sensitivity(layer)["level"], "PUBLIC")


@patch.object(lineage, "QGIS_AVAILABLE", True)
class TestACorruptLineageIsProtected(unittest.TestCase):
    KEY = lineage.LINEAGE_PROPERTY_KEY

    def test_a_stored_history_that_cannot_be_read_is_an_unreadable_entry_not_no_history(self):
        for raw in ("{not json", '{"a": 1}', '"text"'):
            history = lineage.get_layer_lineage(FakeLayer("derived", {self.KEY: raw}))
            self.assertTrue(lineage.lineage_is_unreadable(history), raw)
            self.assertEqual(history[0]["sources"], [])

    def test_a_good_or_missing_history_is_unchanged(self):
        good = [{"tool": "buffer", "sources": ["a"], "source_ids": []}]
        self.assertEqual(lineage.get_layer_lineage(FakeLayer("d", {self.KEY: json.dumps(good)})), good)
        self.assertEqual(lineage.get_layer_lineage(FakeLayer("d")), [])
        self.assertEqual(lineage.get_layer_lineage(FakeLayer("d", {self.KEY: "[]"})), [])

    def test_writing_a_step_keeps_the_corrupt_text_and_marks_the_history_unreadable(self):
        layer = FakeLayer("derived", {self.KEY: "{earlier sources, damaged"})
        self.assertTrue(lineage.tag_layer_lineage(layer, "buffer", {}, ["a"]))
        self.assertEqual(layer.props[lineage.LINEAGE_UNREADABLE_COPY_KEY], "{earlier sources, damaged")
        history = json.loads(layer.props[self.KEY])
        self.assertEqual([e["tool"] for e in history], [lineage.UNREADABLE_LINEAGE_TOOL, "buffer"])
        self.assertTrue(lineage.lineage_is_unreadable(lineage.get_layer_lineage(layer)))

    def test_writing_a_step_to_a_good_history_just_appends(self):
        layer = FakeLayer("derived", {self.KEY: json.dumps([{"tool": "merge", "sources": ["a"], "source_ids": []}])})
        lineage.tag_layer_lineage(layer, "buffer", {}, ["b"])
        self.assertEqual([e["tool"] for e in json.loads(layer.props[self.KEY])], ["merge", "buffer"])
        self.assertNotIn(lineage.LINEAGE_UNREADABLE_COPY_KEY, layer.props)

    def test_a_layer_with_unknown_ancestry_is_sensitive_for_the_gates(self):
        layer = FakeLayer("derived", {self.KEY: "{damaged"})
        with patch.object(protection, "log_event"):
            record = protection.effective_sensitivity(layer, [layer])
        self.assertEqual(record["level"], "SENSITIVE")
        self.assertIn("could not be read", record["reason"])

    def test_an_explicit_tag_on_the_layer_still_wins_so_a_person_can_clear_it(self):
        layer = FakeLayer("derived", {self.KEY: "{damaged", sens.SENSITIVITY_PROPERTY_KEY: json.dumps({"level": "PUBLIC", "reason": "checked"})})
        self.assertEqual(protection.effective_sensitivity(layer, [layer])["level"], "PUBLIC")

    def test_the_egress_gate_lookup_sees_the_same_level(self):
        layer = FakeLayer("derived", {self.KEY: "{damaged"})
        get_level, _ = protection.lookups([layer])
        self.assertEqual(get_level("derived"), "SENSITIVE")
        clean = FakeLayer("clean")
        get_level, _ = protection.lookups([clean])
        self.assertIsNone(get_level("clean"))


if __name__ == "__main__":
    unittest.main()
