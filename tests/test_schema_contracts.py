# -*- coding: utf-8 -*-
"""Tests for agent/schema_contracts.py -- machine-readable dataset schema
contracts closing point 5 of
docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md.

Uses plain fake field/feature/layer objects (not QGIS mocks) for the same
reason dataset_status.py's tests do: the validator is deliberately
duck-typed on fields()/getFeatures(), so it's directly unit-testable
without a live QGIS install. Real contract JSON files
(validators/contracts/health_facilities.json, admin2.json) are read from disk
as-is -- not mocked -- so a change to those files that breaks the contract
shape would actually fail these tests, not just a stale copy of them."""
import unittest
from unittest.mock import patch

from cartogen_ai.core.validators.schema_contracts import list_contracts, validate_layer_schema


class FakeField:
    def __init__(self, name, qvariant_type=None, type_name="String"):
        self._name = name
        self._qvariant_type = qvariant_type
        self._type_name = type_name

    def type(self):
        return self._qvariant_type

    def typeName(self):
        return self._type_name


class FakeFields:
    def __init__(self, fields):
        self._fields = fields

    def names(self):
        return [f._name for f in self._fields]

    def indexFromName(self, name):
        for i, f in enumerate(self._fields):
            if f._name == name:
                return i
        return -1

    def field(self, idx):
        return self._fields[idx]


class FakeFeature:
    def __init__(self, attrs):
        self._attrs = attrs

    def attribute(self, name):
        return self._attrs.get(name)


class FakeLayer:
    def __init__(self, fields, features=None):
        self._fields = FakeFields(fields)
        self._features = features or []

    def fields(self):
        return self._fields

    def getFeatures(self):
        return self._features


class TestListContracts(unittest.TestCase):
    def test_finds_the_two_real_contract_files(self):
        contracts = list_contracts()
        self.assertIn("admin2", contracts)
        self.assertIn("health_facilities", contracts)


class TestValidateLayerSchemaBasics(unittest.TestCase):
    def test_unknown_contract_name_is_an_error(self):
        layer = FakeLayer([FakeField("anything")])
        result = validate_layer_schema(layer, "not_a_real_contract")
        self.assertIn("error", result)

    def test_non_layer_is_an_error(self):
        result = validate_layer_schema(object(), "admin2")
        self.assertIn("error", result)

    def test_admin2_contract_passes_with_matching_lowercase_field_names(self):
        layer = FakeLayer([
            FakeField("admin2_pcode"),
            FakeField("admin2_name"),
            FakeField("admin1_pcode"),
        ])
        result = validate_layer_schema(layer, "admin2")
        self.assertTrue(result["passed"])
        self.assertEqual(result["missing_fields"], [])

    def test_admin2_contract_matches_case_insensitively_via_aliases(self):
        # Real COD-AB downloads use upper-case field names like ADM2_PCODE --
        # the contract's alias list, not just its first-listed name, must
        # match these case-insensitively.
        layer = FakeLayer([
            FakeField("ADM2_PCODE"),
            FakeField("ADM2_EN"),
            FakeField("ADM1_PCODE"),
        ])
        result = validate_layer_schema(layer, "admin2")
        self.assertTrue(result["passed"])

    def test_admin2_contract_reports_missing_field(self):
        layer = FakeLayer([FakeField("admin2_pcode"), FakeField("admin2_name")])
        result = validate_layer_schema(layer, "admin2")
        self.assertFalse(result["passed"])
        self.assertEqual(result["missing_fields"], ["admin1_pcode"])

    def test_health_facilities_contract_reports_all_missing_on_empty_layer(self):
        layer = FakeLayer([])
        result = validate_layer_schema(layer, "health_facilities")
        self.assertFalse(result["passed"])
        self.assertEqual(len(result["missing_fields"]), 3)


class TestValidateLayerSchemaTypeChecking(unittest.TestCase):
    @patch("cartogen_ai.core.validators.schema_contracts.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.validators.schema_contracts.QVariant", create=True)
    def test_type_mismatch_is_reported(self, mock_qvariant):
        mock_qvariant.String = "QV_STRING"
        layer = FakeLayer([
            FakeField("admin2_pcode", qvariant_type="QV_INT", type_name="Integer"),
            FakeField("admin2_name", qvariant_type="QV_STRING"),
            FakeField("admin1_pcode", qvariant_type="QV_STRING"),
        ])
        result = validate_layer_schema(layer, "admin2")
        self.assertFalse(result["passed"])
        self.assertEqual(len(result["type_mismatches"]), 1)
        self.assertEqual(result["type_mismatches"][0]["field"], "admin2_pcode")

    @patch("cartogen_ai.core.validators.schema_contracts.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.validators.schema_contracts.QVariant", create=True)
    def test_matching_types_pass(self, mock_qvariant):
        mock_qvariant.String = "QV_STRING"
        layer = FakeLayer([
            FakeField("admin2_pcode", qvariant_type="QV_STRING"),
            FakeField("admin2_name", qvariant_type="QV_STRING"),
            FakeField("admin1_pcode", qvariant_type="QV_STRING"),
        ])
        result = validate_layer_schema(layer, "admin2")
        self.assertTrue(result["passed"])
        self.assertEqual(result["type_mismatches"], [])

    def test_type_checking_skipped_when_qgis_unavailable(self):
        # QGIS_AVAILABLE is False in this dev environment by default (no
        # qgis.PyQt import) -- a field-presence-only check must still work
        # and must not crash trying to resolve a QVariant type name.
        layer = FakeLayer([
            FakeField("admin2_pcode"),
            FakeField("admin2_name"),
            FakeField("admin1_pcode"),
        ])
        result = validate_layer_schema(layer, "admin2")
        self.assertTrue(result["passed"])
        self.assertEqual(result["type_mismatches"], [])


class TestValidateLayerSchemaAllowedValues(unittest.TestCase):
    def _facilities_layer(self, facility_types):
        fields = [
            FakeField("facility_name"),
            FakeField("facility_type"),
            FakeField("admin2_pcode"),
        ]
        features = [
            FakeFeature({"facility_name": f"Facility {i}", "facility_type": ftype, "admin2_pcode": "YE1201"})
            for i, ftype in enumerate(facility_types)
        ]
        return FakeLayer(fields, features)

    def test_all_values_in_domain_passes(self):
        layer = self._facilities_layer(["Hospital", "Health Post", "Mobile Clinic"])
        result = validate_layer_schema(layer, "health_facilities")
        self.assertTrue(result["passed"])
        self.assertEqual(result["value_violations"], [])

    def test_out_of_domain_value_is_reported(self):
        layer = self._facilities_layer(["Hospital", "Pharmacy", "Pharmacy"])
        result = validate_layer_schema(layer, "health_facilities")
        self.assertFalse(result["passed"])
        self.assertEqual(len(result["value_violations"]), 1)
        violation = result["value_violations"][0]
        self.assertEqual(violation["field"], "facility_type")
        self.assertEqual(violation["bad_count"], 2)
        self.assertIn("Pharmacy", violation["example_values"])

    def test_null_values_are_not_flagged_as_violations(self):
        layer = self._facilities_layer(["Hospital", None])
        result = validate_layer_schema(layer, "health_facilities")
        self.assertTrue(result["passed"])


if __name__ == "__main__":
    unittest.main()
