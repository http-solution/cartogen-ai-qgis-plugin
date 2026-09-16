# -*- coding: utf-8 -*-
"""Tests for humanitarian_tools.py's _clip_to_field_width -- the same fix as
hazard_monitoring_tools.py's identically-named helper (see
tests/test_hazard_monitoring_tools.py::TestClipToFieldWidth for the full live-report
context), duplicated here per this codebase's existing per-file-helper convention. Pure
duck-typed fake, no qgis.core import needed."""
import unittest

from cartogen_ai.core.agent.tools import humanitarian_tools as ht


class _FakeField:
    def __init__(self, width):
        self._width = width

    def length(self):
        return self._width


class _FakeFields:
    def __init__(self, widths):
        self._widths = widths

    def field(self, name):
        return _FakeField(self._widths.get(name, 0))


class _FakeLayer:
    def __init__(self, widths):
        self._fields = _FakeFields(widths)

    def fields(self):
        return self._fields


class TestClipToFieldWidth(unittest.TestCase):
    def test_a_string_longer_than_the_field_width_is_clipped(self):
        layer = _FakeLayer({"description": 255})
        value = "x" * 500
        self.assertEqual(len(ht._clip_to_field_width(layer, "description", value)), 255)

    def test_a_string_within_the_field_width_is_untouched(self):
        layer = _FakeLayer({"name": 255})
        self.assertEqual(ht._clip_to_field_width(layer, "name", "Ar Ramadi Civilian Hospital"),
                          "Ar Ramadi Civilian Hospital")

    def test_a_zero_width_field_is_treated_as_unbounded(self):
        layer = _FakeLayer({"notes": 0})
        value = "x" * 1000
        self.assertEqual(ht._clip_to_field_width(layer, "notes", value), value)

    def test_a_non_string_value_passes_through_unchanged(self):
        layer = _FakeLayer({"count": 10})
        self.assertEqual(ht._clip_to_field_width(layer, "count", 42), 42)


if __name__ == "__main__":
    unittest.main()
