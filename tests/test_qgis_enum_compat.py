# -*- coding: utf-8 -*-
"""Tests for agent/tools/_qgis_enum_compat.py -- the 2026-09-04 fix for
TASK-0008 (the ~15-site unscoped-native-QGIS-enum risk flagged by the
incomplete/mockup-code audit, see docs/MASTER_TASK_REGISTRY.md and
docs/BUG_TRACKER.md BUG-2026-09-02-3). Pure Python, no QGIS needed --
resolve_qgis_enum only ever calls getattr on whatever class it's handed."""
import unittest
from cartogen_ai.core.agent.tools._qgis_enum_compat import resolve_qgis_enum


class _ScopedOnly:
    """Stands in for a QGIS 4.x/Qt6-style class: the member only exists
    nested under a named sub-enum."""
    class Mode:
        Jenks = "scoped-jenks"


class _FlatOnly:
    """Stands in for a QGIS 3.x/Qt5-style class: the member is flat on the
    class itself, no nested sub-enum at all."""
    Jenks = "flat-jenks"


class _Both:
    """A class exposing both forms (e.g. a QGIS build that keeps a
    deprecated flat alias alongside the new scoped one) -- the scoped form
    must win."""
    class Mode:
        Jenks = "scoped-jenks"
    Jenks = "flat-jenks"


class _Neither:
    pass


class TestResolveQgisEnum(unittest.TestCase):
    def test_prefers_scoped_form_when_present(self):
        self.assertEqual(resolve_qgis_enum(_ScopedOnly, "Mode", "Jenks"), "scoped-jenks")

    def test_falls_back_to_flat_form_when_no_nested_enum(self):
        self.assertEqual(resolve_qgis_enum(_FlatOnly, "Mode", "Jenks"), "flat-jenks")

    def test_prefers_scoped_over_flat_when_both_exist(self):
        self.assertEqual(resolve_qgis_enum(_Both, "Mode", "Jenks"), "scoped-jenks")

    def test_returns_none_when_neither_form_exists(self):
        self.assertIsNone(resolve_qgis_enum(_Neither, "Mode", "Jenks"))

    def test_falls_back_to_flat_when_nested_enum_exists_but_member_missing(self):
        class WrongNestedMember:
            class Mode:
                Quantile = "scoped-quantile"
            Jenks = "flat-jenks"
        # "Mode" exists but has no "Jenks" -- must not silently return None,
        # must still try the flat form.
        self.assertEqual(resolve_qgis_enum(WrongNestedMember, "Mode", "Jenks"), "flat-jenks")


if __name__ == "__main__":
    unittest.main()
