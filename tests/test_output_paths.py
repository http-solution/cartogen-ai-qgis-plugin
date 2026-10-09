# -*- coding: utf-8 -*-
"""rc22 smoke test N3/N8/N9: a relative output_path is anchored to the project folder, never the process working directory."""
import os
import unittest

from cartogen_ai.core.agent.tools._paths import resolve_output_path


class TestResolveOutputPath(unittest.TestCase):
    def test_relative_path_goes_under_the_project_home(self):
        home = os.path.abspath(os.path.join(os.sep, "work", "proj"))
        self.assertEqual(resolve_output_path("outputs/smoke_layout.pdf", project_home=home),
                         os.path.normpath(os.path.join(home, "outputs", "smoke_layout.pdf")))

    def test_unsaved_project_uses_the_fallback_folder_not_the_cwd(self):
        fallback = os.path.abspath(os.path.join(os.sep, "profile", "exports"))
        out = resolve_output_path("a.csv", project_home="", fallback_dir=fallback)
        self.assertEqual(out, os.path.normpath(os.path.join(fallback, "a.csv")))
        self.assertNotEqual(os.path.dirname(out), os.getcwd())

    def test_absolute_path_is_kept(self):
        target = os.path.abspath(os.path.join(os.sep, "data", "x.gpkg"))
        self.assertEqual(resolve_output_path(target, project_home="/ignored"), target)

    def test_home_is_expanded_and_empty_is_unchanged(self):
        self.assertTrue(os.path.isabs(resolve_output_path("~/x.csv", project_home="/ignored")))
        self.assertEqual(resolve_output_path("", project_home="/p"), "")
        self.assertIsNone(resolve_output_path(None, project_home="/p"))

    def test_dotdot_is_normalised(self):
        home = os.path.abspath(os.path.join(os.sep, "work", "proj"))
        self.assertEqual(resolve_output_path("sub/../out.csv", project_home=home), os.path.normpath(os.path.join(home, "out.csv")))


if __name__ == "__main__":
    unittest.main()
