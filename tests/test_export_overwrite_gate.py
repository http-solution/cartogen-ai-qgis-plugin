# -*- coding: utf-8 -*-
"""Replacing a file the plugin did not write needs the user's confirmation (rc17 hand test A6, 2026-10-06)."""
import os
import tempfile
import unittest

from cartogen_ai.core.agent.tools import export_tools as et


class TestOverwritePreview(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "points.csv")
        et._WRITTEN_THIS_SESSION.clear()

    def test_a_missing_file_needs_no_question(self):
        self.assertIsNone(et.overwrite_preview("export_to_csv", {"layer_name": "L"}, self.path))

    def test_an_existing_file_the_session_did_not_write_asks_first(self):
        open(self.path, "w").write("old")
        res = et.overwrite_preview("export_to_csv", {"layer_name": "L", "output_path": self.path}, self.path)
        self.assertEqual(res["status"], "PREVIEW_REQUIRED")
        self.assertTrue(res["is_destructive"])
        self.assertTrue(res["arguments"]["confirmed"])
        self.assertEqual(res["arguments"]["layer_name"], "L")
        self.assertIn(self.path, res["message"])

    def test_an_empty_placeholder_file_needs_no_question(self):
        open(self.path, "w").close()
        self.assertIsNone(et.overwrite_preview("export_to_csv", {}, self.path))

    def test_a_file_this_session_wrote_is_replaced_without_a_question(self):
        open(self.path, "w").write("mine")
        et.remember_written(self.path)
        self.assertIsNone(et.overwrite_preview("export_to_csv", {}, self.path))

    def test_a_file_edited_after_the_plugin_wrote_it_asks_again(self):
        open(self.path, "w").write("mine")
        et.remember_written(self.path)
        open(self.path, "w").write("mine, then edited by the user")
        self.assertEqual(et.overwrite_preview("export_to_csv", {}, self.path)["status"], "PREVIEW_REQUIRED")

    def test_a_path_without_an_extension_checks_the_files_a_driver_would_create(self):
        base = os.path.join(self.dir, "roads")
        open(base + ".shp", "w").write("existing shapefile")
        res = et.overwrite_preview("export_layer", {"layer_name": "L"}, base)
        self.assertIsNotNone(res)
        self.assertIn("roads.shp", res["message"])

    def test_the_tools_accept_the_confirmed_flag_so_the_apply_button_can_run_them(self):
        import inspect
        for fn in (et.export_to_csv, et.export_layer):
            self.assertIn("confirmed", inspect.signature(fn).parameters)


if __name__ == "__main__":
    unittest.main()
