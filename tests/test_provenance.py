# -*- coding: utf-8 -*-
"""Tests for agent/provenance.py -- the deterministic provenance record
closing point 17 of docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md.

Uses the same plain fake layer object as tests/test_dataset_status.py
(customProperty/setCustomProperty storage, a name()) since
build_provenance_record is deliberately duck-typed the same way. lineage.py
itself gates get_layer_lineage on module-level QGIS_AVAILABLE (unlike
dataset_status.py -- see that module's own "Unlike lineage.py" comment),
so exercising real lineage data through a fake layer means patching
cartogen_ai.core.agent.lineage.QGIS_AVAILABLE True for that one call, the
same way schema_contract/pcode_depth gate tests patch the modules whose
real behavior they need to exercise."""
import unittest
from unittest.mock import patch

from cartogen_ai.core.agent.provenance import build_provenance_record
from cartogen_ai.core.agent.lineage import tag_layer_lineage
from cartogen_ai.core.models.dataset_status import set_initial_status


class FakeLayer:
    def __init__(self, name="test_layer"):
        self._name = name
        self._props = {}

    def name(self):
        return self._name

    def customProperty(self, key, default=""):
        return self._props.get(key, default)

    def setCustomProperty(self, key, value):
        self._props[key] = value


class TestBuildProvenanceRecordBasics(unittest.TestCase):
    def test_none_layer_is_an_error(self):
        result = build_provenance_record(None)
        self.assertIn("error", result)

    def test_object_without_name_is_an_error(self):
        result = build_provenance_record(object())
        self.assertIn("error", result)

    def test_untracked_layer_has_empty_lineage_and_default_qa_status(self):
        layer = FakeLayer("districts")
        result = build_provenance_record(layer)
        self.assertEqual(result["layer_name"], "districts")
        self.assertIn("generated_at", result)
        self.assertEqual(result["qa_status"], {"status": None, "history": [], "checks": {}})
        # lineage.QGIS_AVAILABLE is real (unpatched) here -- False in this
        # dev environment -- so get_layer_lineage always returns [] by its
        # own design, same as it would for any layer in production without
        # a live QGIS session.
        self.assertEqual(result["lineage"], [])

    def test_qgis_version_is_none_when_qgis_unavailable(self):
        result = build_provenance_record(FakeLayer())
        self.assertIsNone(result["qgis_version"])

    @patch("cartogen_ai.core.agent.provenance.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.provenance.Qgis", create=True)
    def test_qgis_version_is_read_when_available(self, mock_qgis):
        mock_qgis.QGIS_VERSION = "3.34.5-Prizren"
        result = build_provenance_record(FakeLayer())
        self.assertEqual(result["qgis_version"], "3.34.5-Prizren")


class TestBuildProvenanceRecordReflectsRealData(unittest.TestCase):
    @patch("cartogen_ai.core.agent.lineage.QGIS_AVAILABLE", True)
    def test_reflects_tracked_lineage_history(self):
        layer = FakeLayer("districts")
        tag_layer_lineage(layer, "fetch_hdx_admin_boundaries", {"iso3": "YEM"})
        tag_layer_lineage(layer, "diagnose_topology", {"min_area": 10}, source_layers=["districts"])

        result = build_provenance_record(layer)

        self.assertEqual(len(result["lineage"]), 2)
        self.assertEqual(result["lineage"][0]["tool"], "fetch_hdx_admin_boundaries")
        self.assertEqual(result["lineage"][1]["tool"], "diagnose_topology")
        self.assertEqual(result["lineage"][1]["sources"], ["districts"])

    def test_reflects_tracked_qa_status(self):
        layer = FakeLayer("districts")
        set_initial_status(layer, status="VALIDATED", note="geometry checked manually")

        result = build_provenance_record(layer)

        self.assertEqual(result["qa_status"]["status"], "VALIDATED")
        self.assertEqual(len(result["qa_status"]["history"]), 1)

    @patch("cartogen_ai.core.agent.lineage.QGIS_AVAILABLE", True)
    def test_reflects_both_lineage_and_qa_status_together(self):
        layer = FakeLayer("districts")
        tag_layer_lineage(layer, "fetch_hdx_admin_boundaries", {"iso3": "YEM"})
        set_initial_status(layer, status="INGESTED")

        result = build_provenance_record(layer)

        self.assertEqual(len(result["lineage"]), 1)
        self.assertEqual(result["qa_status"]["status"], "INGESTED")


if __name__ == "__main__":
    unittest.main()
