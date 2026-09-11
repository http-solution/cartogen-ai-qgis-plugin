# -*- coding: utf-8 -*-
"""Tests for agent/data_export.py -- GDPR review findings F7/F8
(docs/GDPR_COMPLIANCE_REVIEW.docx). Pure Python/JSON, no qgis import at
all, so fully testable without any QGIS_AVAILABLE guard."""
import json
import os
import tempfile
import unittest

from cartogen_ai.core.agent.data_export import build_export_document, write_export_document


class TestBuildExportDocument(unittest.TestCase):
    def test_assembles_all_three_sources(self):
        doc = build_export_document(
            project_notes={"study_area": "Damascus Region"},
            global_notes={"pref:units": "metric"},
            chat_history=[{"role": "user", "content": "hi", "ts": "2026-01-01T00:00:00"}],
        )
        self.assertEqual(doc["project_memory"], {"study_area": "Damascus Region"})
        self.assertEqual(doc["global_memory"], {"pref:units": "metric"})
        self.assertEqual(len(doc["chat_history"]), 1)
        self.assertEqual(doc["export_format_version"], 1)
        self.assertIn("exported_at", doc)

    def test_handles_none_inputs_without_raising(self):
        doc = build_export_document(None, None, None)
        self.assertEqual(doc["project_memory"], {})
        self.assertEqual(doc["global_memory"], {})
        self.assertEqual(doc["chat_history"], [])

    def test_does_not_mutate_caller_dicts(self):
        project_notes = {"a": "1"}
        doc = build_export_document(project_notes, {}, [])
        doc["project_memory"]["b"] = "2"
        self.assertNotIn("b", project_notes)


class TestWriteExportDocument(unittest.TestCase):
    def test_writes_real_json_file(self):
        doc = {"export_format_version": 1, "project_memory": {"k": "v"}}
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "export.json")
            ok = write_export_document(doc, path)
            self.assertTrue(ok)
            with open(path, encoding="utf-8") as f:
                loaded = json.load(f)
            self.assertEqual(loaded, doc)

    def test_returns_false_on_write_failure_not_raise(self):
        # A directory that doesn't exist -- open() will fail, must be caught.
        bad_path = os.path.join(tempfile.gettempdir(), "cartogen_nonexistent_dir_xyz", "export.json")
        ok = write_export_document({"a": 1}, bad_path)
        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
