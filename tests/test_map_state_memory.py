# -*- coding: utf-8 -*-
"""Unit tests for map_state_memory.py -- the design-state half of the §1.16
"smart mapping" dual-memory work. Pure Python, no QGIS needed: memory_manager
is a small fake object matching SpatialMemoryManager's
get_project_notes()/store_project_note() surface, the same pattern
tests/test_learning.py already uses for the sibling pref:*/rule:*/usage:*
mechanism."""
import unittest
from cartogen_ai.core.agent.map_state_memory import record_output, recall_output


class _FakeMemoryManager:
    def __init__(self):
        self._notes = {}

    def get_project_notes(self):
        return dict(self._notes)

    def store_project_note(self, key, value):
        self._notes[key] = value
        return {"success": True, "key": key, "value": value}


class TestRecallOutput(unittest.TestCase):
    def test_nothing_recorded_returns_none(self):
        mm = _FakeMemoryManager()
        self.assertIsNone(recall_output(mm, "proximity_buffer"))

    def test_none_memory_manager_returns_none(self):
        self.assertIsNone(recall_output(None, "proximity_buffer"))

    def test_recalls_exactly_what_was_recorded(self):
        mm = _FakeMemoryManager()
        record_output(mm, "proximity_buffer", "layer_1", "5km Buffer",
                       style_profile="proximity_buffer", properties={"color": "#ff0000"})
        recalled = recall_output(mm, "proximity_buffer")
        self.assertEqual(recalled["layer_id"], "layer_1")
        self.assertEqual(recalled["layer_name"], "5km Buffer")
        self.assertEqual(recalled["style_profile"], "proximity_buffer")
        self.assertEqual(recalled["properties"], {"color": "#ff0000"})

    def test_different_roles_are_kept_separate(self):
        mm = _FakeMemoryManager()
        record_output(mm, "proximity_buffer", "layer_1", "Buffer", properties={"color": "#ff0000"})
        record_output(mm, "hazard_extent", "layer_2", "Flood Extent", properties={"color": "#00ff00"})
        self.assertEqual(recall_output(mm, "proximity_buffer")["layer_id"], "layer_1")
        self.assertEqual(recall_output(mm, "hazard_extent")["layer_id"], "layer_2")

    def test_corrupt_stored_value_is_ignored_not_raised(self):
        mm = _FakeMemoryManager()
        mm.store_project_note("layout:proximity_buffer", "not valid json{{{")
        self.assertIsNone(recall_output(mm, "proximity_buffer"))

    def test_non_dict_json_is_ignored(self):
        mm = _FakeMemoryManager()
        mm.store_project_note("layout:proximity_buffer", "[1, 2, 3]")
        self.assertIsNone(recall_output(mm, "proximity_buffer"))


class TestRecordOutput(unittest.TestCase):
    def test_none_memory_manager_is_a_safe_no_op(self):
        self.assertIsNone(record_output(None, "proximity_buffer", "x", "y"))

    def test_first_call_for_a_role_returns_none_as_the_previous_value(self):
        mm = _FakeMemoryManager()
        previous = record_output(mm, "proximity_buffer", "layer_1", "Buffer")
        self.assertIsNone(previous)

    def test_second_call_for_the_same_role_returns_the_first_as_previous(self):
        mm = _FakeMemoryManager()
        record_output(mm, "proximity_buffer", "layer_1", "Buffer v1", properties={"color": "#ff0000"})
        previous = record_output(mm, "proximity_buffer", "layer_2", "Buffer v2", properties={"color": "#00ff00"})
        self.assertEqual(previous["layer_id"], "layer_1")
        self.assertEqual(previous["properties"]["color"], "#ff0000")
        # and the new call is now what's recalled going forward
        self.assertEqual(recall_output(mm, "proximity_buffer")["layer_id"], "layer_2")

    def test_missing_style_profile_and_properties_default_sensibly(self):
        mm = _FakeMemoryManager()
        record_output(mm, "proximity_buffer", "layer_1", "Buffer")
        recalled = recall_output(mm, "proximity_buffer")
        self.assertIsNone(recalled["style_profile"])
        self.assertEqual(recalled["properties"], {})


if __name__ == "__main__":
    unittest.main()
