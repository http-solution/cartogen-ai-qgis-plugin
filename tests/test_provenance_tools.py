# -*- coding: utf-8 -*-
"""Tests for agent/tools/provenance_tools.py -- the registered-tool
surface over agent/provenance.py (point 17 of
docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md).

Degrade-path tests run with no QGIS_AVAILABLE patch (matching this dev
environment's real state). Layer-lookup/delegation tests patch
QGIS_AVAILABLE True and QgsProject, following the same convention used in
tests/test_dataset_status_tools.py. write_provenance_sidecar's tests
write a real file to disk and clean it up in a finally block, the same
convention tests/test_export_tools.py already uses for generate_report's
real Desktop .docx writes -- there's nothing here that needs mocking the
filesystem itself, only QGIS layer lookup."""
import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from cartogen_ai.core.agent.tools.provenance_tools import (
    get_provenance_record,
    write_provenance_sidecar,
)


def _fake_layer(name="test_layer", source=""):
    layer = MagicMock()
    layer.name.return_value = name
    layer.source.return_value = source
    layer.customProperty.return_value = ""
    return layer


class TestDegradesGracefullyOutsideQgis(unittest.TestCase):
    def test_get_provenance_record_degrades(self):
        result = get_provenance_record("some_layer")
        self.assertIn("error", result)
        self.assertIn("QGIS not available", result["error"])

    def test_write_provenance_sidecar_degrades(self):
        result = write_provenance_sidecar("some_layer")
        self.assertIn("error", result)
        self.assertIn("QGIS not available", result["error"])


class TestLayerNotFound(unittest.TestCase):
    @patch("cartogen_ai.core.agent.tools.provenance_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.provenance_tools.QgsProject", create=True)
    def test_get_provenance_record_missing_layer(self, mock_project):
        mock_project.instance.return_value.mapLayersByName.return_value = []
        result = get_provenance_record("missing_layer")
        self.assertIn("error", result)
        self.assertIn("not found", result["error"])

    @patch("cartogen_ai.core.agent.tools.provenance_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.provenance_tools.QgsProject", create=True)
    def test_write_provenance_sidecar_missing_layer(self, mock_project):
        mock_project.instance.return_value.mapLayersByName.return_value = []
        result = write_provenance_sidecar("missing_layer")
        self.assertIn("error", result)
        self.assertIn("not found", result["error"])


class TestGetProvenanceRecordDelegates(unittest.TestCase):
    @patch("cartogen_ai.core.agent.tools.provenance_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.provenance_tools.QgsProject", create=True)
    def test_delegates_to_core_module(self, mock_project):
        layer = _fake_layer("districts")
        mock_project.instance.return_value.mapLayersByName.return_value = [layer]

        result = get_provenance_record("districts")

        self.assertTrue(result["success"])
        self.assertEqual(result["layer_name"], "districts")
        self.assertEqual(result["lineage"], [])
        self.assertEqual(result["qa_status"], {"status": None, "history": [], "checks": {}})


class TestWriteProvenanceSidecarExplicitPath(unittest.TestCase):
    @patch("cartogen_ai.core.agent.tools.provenance_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.provenance_tools.QgsProject", create=True)
    def test_writes_real_json_file_to_explicit_output_path(self, mock_project):
        layer = _fake_layer("districts")
        mock_project.instance.return_value.mapLayersByName.return_value = [layer]

        with tempfile.TemporaryDirectory() as tmp_dir:
            out_path = os.path.join(tmp_dir, "districts.provenance.json")
            result = write_provenance_sidecar("districts", output_path=out_path)

            self.assertTrue(result["success"])
            self.assertEqual(result["path"], out_path)
            self.assertNotIn("warning", result)
            self.assertTrue(os.path.isfile(out_path))
            with open(out_path, "r", encoding="utf-8") as f:
                on_disk = json.load(f)
            self.assertEqual(on_disk["layer_name"], "districts")


class TestWriteProvenanceSidecarPathDerivation(unittest.TestCase):
    @patch("cartogen_ai.core.agent.tools.provenance_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.provenance_tools.QgsProject", create=True)
    def test_sits_beside_a_real_on_disk_source(self, mock_project):
        with tempfile.TemporaryDirectory() as tmp_dir:
            source_path = os.path.join(tmp_dir, "districts.gpkg")
            with open(source_path, "w") as f:
                f.write("not a real geopackage, just needs to exist")

            layer = _fake_layer("districts", source=source_path)
            mock_project.instance.return_value.mapLayersByName.return_value = [layer]

            result = write_provenance_sidecar("districts")

            expected_path = f"{source_path}.provenance.json"
            self.assertTrue(result["success"])
            self.assertEqual(result["path"], expected_path)
            self.assertNotIn("warning", result)
            self.assertTrue(os.path.isfile(expected_path))

    @patch("cartogen_ai.core.agent.tools.provenance_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.provenance_tools.QgsProject", create=True)
    def test_strips_qgis_uri_suffix_before_checking_for_a_real_file(self, mock_project):
        with tempfile.TemporaryDirectory() as tmp_dir:
            source_path = os.path.join(tmp_dir, "admin.gpkg")
            with open(source_path, "w") as f:
                f.write("not a real geopackage, just needs to exist")

            layer = _fake_layer("admin2", source=f"{source_path}|layername=admin2")
            mock_project.instance.return_value.mapLayersByName.return_value = [layer]

            result = write_provenance_sidecar("admin2")

            expected_path = f"{source_path}.provenance.json"
            self.assertTrue(result["success"])
            self.assertEqual(result["path"], expected_path)
            self.assertNotIn("warning", result)

    @patch("cartogen_ai.core.agent.tools.provenance_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.provenance_tools.QgsProject", create=True)
    def test_falls_back_to_desktop_for_a_scratch_layer_with_no_real_source(self, mock_project):
        # A memory/scratch layer's source() looks like "memory?geometry=..."
        # -- never a real file on disk, so os.path.isfile on it is always
        # False. This exercises the real fallback path (Desktop, or home
        # when no Desktop directory exists -- same convention
        # tests/test_export_tools.py already uses for generate_report's
        # real Desktop .docx writes, and the same fallback-to-home logic
        # this dev sandbox itself needs since it has no Desktop folder).
        layer = _fake_layer("scratch_layer", source="memory?geometry=Point&crs=EPSG:4326")
        mock_project.instance.return_value.mapLayersByName.return_value = [layer]

        result = write_provenance_sidecar("scratch_layer")
        try:
            self.assertTrue(result["success"], result)
            self.assertIn("warning", result)
            self.assertTrue(result["path"].endswith("scratch_layer.provenance.json"))
            self.assertTrue(os.path.isfile(result["path"]))
        finally:
            if result.get("path") and os.path.isfile(result["path"]):
                os.remove(result["path"])


if __name__ == "__main__":
    unittest.main()
