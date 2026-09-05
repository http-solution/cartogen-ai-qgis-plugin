# -*- coding: utf-8 -*-
"""Tests for the release packaging rules in plugin_upload.py.

These exist because of a real near-miss: excluding the repo-root `tools/`
directory by bare name also matched src/cartogen_ai/core/agent/tools/, and the
built zip went from 63 source files to 44 -- a plugin whose agent had no tools
to call, with nothing in the build output saying so. The build script is a
plain module with no QGIS or Qt imports, so its rules can be checked directly.
"""
import importlib.util
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load():
    spec = importlib.util.spec_from_file_location(
        "plugin_upload", os.path.join(ROOT, "plugin_upload.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestExclusionsCannotSwallowRealSource(unittest.TestCase):
    def setUp(self):
        self.pu = _load()
        self.src_dirs = set()
        for r, d, _f in os.walk(os.path.join(ROOT, "src")):
            d[:] = [x for x in d if x != "__pycache__"]
            for x in d:
                self.src_dirs.add(x)

    def test_no_bare_name_exclusion_matches_a_directory_inside_src(self):
        clash = self.src_dirs & set(self.pu.EXCLUDE_DIRS)
        self.assertEqual(clash, set(),
                         "EXCLUDE_DIRS entries %s also name real packages under src/; "
                         "they belong in EXCLUDE_ROOT_ONLY_DIRS" % sorted(clash))

    def test_the_tools_package_is_specifically_protected(self):
        self.assertIn("tools", self.src_dirs)
        self.assertNotIn("tools", self.pu.EXCLUDE_DIRS)
        self.assertIn("tools", self.pu.EXCLUDE_ROOT_ONLY_DIRS)

    def test_no_source_file_matches_a_stray_file_pattern(self):
        import fnmatch
        offenders = []
        for r, d, f in os.walk(os.path.join(ROOT, "src")):
            d[:] = [x for x in d if x != "__pycache__"]
            for name in f:
                for pat in self.pu.EXCLUDE_FILE_PATTERNS:
                    if fnmatch.fnmatch(name, pat):
                        offenders.append(os.path.join(r, name))
        self.assertEqual(offenders, [], "these would be dropped from the zip: %s" % offenders)

    def test_the_package_directory_is_not_the_import_name(self):
        """The zip's single top-level folder becomes the installed plugin
        directory. Naming it `cartogen_ai` would shadow the namespace package
        the plugin imports from."""
        self.assertEqual(self.pu.PACKAGE_DIR, "cartogen-ai")

    def test_staging_files_dropped_in_the_repo_root_never_ship(self):
        import fnmatch
        for name in ("_register_page.html", "_reg_compact.json", "_repo_snapshot.tgz"):
            self.assertTrue(
                any(fnmatch.fnmatch(name, p) for p in self.pu.EXCLUDE_FILE_PATTERNS),
                "%s would ship" % name)


if __name__ == "__main__":
    unittest.main()
