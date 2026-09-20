# -*- coding: utf-8 -*-
"""Tests for validators/pcode_validation.py -- P-code uniqueness and
parent/child hierarchy prefix-match checks closing point 6 of
docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md.

Uses plain fake field/feature/layer objects (not QGIS mocks), the same
convention as tests/test_schema_contracts.py: both checks are deliberately
duck-typed on fields()/getFeatures(), so they're directly unit-testable
without a live QGIS install."""
import unittest

from cartogen_ai.core.validators.pcode_validation import (
    check_pcode_uniqueness,
    check_pcode_hierarchy,
)


class FakeFields:
    def __init__(self, names):
        self._names = names

    def names(self):
        return self._names


class FakeFeature:
    def __init__(self, attrs, fid):
        self._attrs = attrs
        self._fid = fid

    def attribute(self, name):
        return self._attrs.get(name)

    def id(self):
        return self._fid


class FakeLayer:
    def __init__(self, field_names, rows):
        """rows: list of dicts of {field_name: value}; fid is the row index."""
        self._fields = FakeFields(field_names)
        self._features = [FakeFeature(row, i) for i, row in enumerate(rows)]

    def fields(self):
        return self._fields

    def getFeatures(self):
        return self._features


class NotALayer:
    """Has neither fields() nor getFeatures() -- e.g. a raster layer."""


class TestCheckPcodeUniquenessBasics(unittest.TestCase):
    def test_non_layer_is_an_error(self):
        result = check_pcode_uniqueness(NotALayer())
        self.assertIn("error", result)

    def test_none_layer_is_an_error(self):
        result = check_pcode_uniqueness(None)
        self.assertIn("error", result)

    def test_no_matching_field_and_no_explicit_field_is_an_error(self):
        layer = FakeLayer(["some_other_field"], [])
        result = check_pcode_uniqueness(layer)
        self.assertIn("error", result)

    def test_explicit_field_not_found_is_an_error(self):
        layer = FakeLayer(["admin2_pcode"], [])
        result = check_pcode_uniqueness(layer, pcode_field="not_a_real_field")
        self.assertIn("error", result)

    def test_all_unique_pcodes_pass(self):
        layer = FakeLayer(
            ["admin2_pcode"],
            [{"admin2_pcode": "YE1201"}, {"admin2_pcode": "YE1202"}, {"admin2_pcode": "YE1203"}],
        )
        result = check_pcode_uniqueness(layer)
        self.assertTrue(result["passed"])
        self.assertEqual(result["unique_pcodes"], 3)
        self.assertEqual(result["duplicate_pcodes"], {})

    def test_duplicate_pcodes_fail_and_are_reported(self):
        layer = FakeLayer(
            ["admin2_pcode"],
            [{"admin2_pcode": "YE1201"}, {"admin2_pcode": "YE1202"}, {"admin2_pcode": "YE1201"}],
        )
        result = check_pcode_uniqueness(layer)
        self.assertFalse(result["passed"])
        self.assertIn("YE1201", result["duplicate_pcodes"])
        self.assertEqual(result["duplicate_pcodes"]["YE1201"], [0, 2])

    def test_null_and_empty_pcodes_are_skipped_not_flagged_as_duplicates(self):
        layer = FakeLayer(
            ["admin2_pcode"],
            [{"admin2_pcode": "YE1201"}, {"admin2_pcode": None}, {"admin2_pcode": ""}],
        )
        result = check_pcode_uniqueness(layer)
        self.assertTrue(result["passed"])
        self.assertEqual(result["null_or_empty_pcodes"], 2)
        self.assertEqual(result["unique_pcodes"], 1)

    def test_matches_case_insensitively_via_alias_list(self):
        # Real COD-AB downloads use upper-case field names like ADM2_PCODE.
        layer = FakeLayer(["ADM2_PCODE"], [{"ADM2_PCODE": "YE1201"}])
        result = check_pcode_uniqueness(layer)
        self.assertEqual(result["pcode_field"], "ADM2_PCODE")
        self.assertTrue(result["passed"])

    def test_explicit_field_name_matches_case_insensitively(self):
        layer = FakeLayer(["Custom_PCode"], [{"Custom_PCode": "YE1201"}])
        result = check_pcode_uniqueness(layer, pcode_field="custom_pcode")
        self.assertEqual(result["pcode_field"], "Custom_PCode")
        self.assertTrue(result["passed"])


class TestCheckPcodeHierarchyBasics(unittest.TestCase):
    def test_non_layer_is_an_error(self):
        result = check_pcode_hierarchy(NotALayer())
        self.assertIn("error", result)

    def test_missing_both_fields_is_an_error(self):
        layer = FakeLayer(["some_other_field"], [])
        result = check_pcode_hierarchy(layer)
        self.assertIn("error", result)
        self.assertIsNone(result["child_pcode_field"])
        self.assertIsNone(result["parent_pcode_field"])

    def test_missing_parent_field_only_is_an_error(self):
        layer = FakeLayer(["admin2_pcode"], [])
        result = check_pcode_hierarchy(layer)
        self.assertIn("error", result)
        self.assertEqual(result["child_pcode_field"], "admin2_pcode")
        self.assertIsNone(result["parent_pcode_field"])

    def test_all_children_prefixed_by_parent_pass(self):
        layer = FakeLayer(
            ["admin2_pcode", "admin1_pcode"],
            [
                {"admin2_pcode": "YE1201", "admin1_pcode": "YE12"},
                {"admin2_pcode": "YE1202", "admin1_pcode": "YE12"},
            ],
        )
        result = check_pcode_hierarchy(layer)
        self.assertTrue(result["passed"])
        self.assertEqual(result["mismatches"], [])
        self.assertEqual(result["checked_features"], 2)

    def test_mismatched_prefix_fails_and_is_reported(self):
        layer = FakeLayer(
            ["admin2_pcode", "admin1_pcode"],
            [
                {"admin2_pcode": "YE1201", "admin1_pcode": "YE12"},
                {"admin2_pcode": "YE0902", "admin1_pcode": "YE12"},
            ],
        )
        result = check_pcode_hierarchy(layer)
        self.assertFalse(result["passed"])
        self.assertEqual(len(result["mismatches"]), 1)
        self.assertEqual(result["mismatches"][0]["child_pcode"], "YE0902")
        self.assertEqual(result["mismatches"][0]["parent_pcode"], "YE12")

    def test_rows_missing_either_value_are_skipped_not_flagged(self):
        layer = FakeLayer(
            ["admin2_pcode", "admin1_pcode"],
            [
                {"admin2_pcode": "YE1201", "admin1_pcode": "YE12"},
                {"admin2_pcode": None, "admin1_pcode": "YE12"},
                {"admin2_pcode": "YE1203", "admin1_pcode": None},
            ],
        )
        result = check_pcode_hierarchy(layer)
        self.assertTrue(result["passed"])
        self.assertEqual(result["checked_features"], 1)
        self.assertEqual(result["skipped_missing_values"], 2)

    def test_explicit_field_names_are_honored(self):
        layer = FakeLayer(
            ["child_code", "parent_code"],
            [{"child_code": "YE1201", "parent_code": "YE12"}],
        )
        result = check_pcode_hierarchy(
            layer, child_pcode_field="child_code", parent_pcode_field="parent_code"
        )
        self.assertTrue(result["passed"])
        self.assertEqual(result["child_pcode_field"], "child_code")
        self.assertEqual(result["parent_pcode_field"], "parent_code")


if __name__ == "__main__":
    unittest.main()
