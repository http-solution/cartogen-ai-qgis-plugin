"""Tests for the release packaging rules in plugin_upload.py.

These exist because of a real near-miss: excluding the repo-root `tools/`
directory by bare name also matched src/cartogen_ai/core/agent/tools/, and the
built zip went from 63 source files to 44 -- a plugin whose agent had no tools
to call, with nothing in the build output saying so. The build script is a
plain module with no QGIS or Qt imports, so its rules can be checked directly.
"""
import pathlib
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
        for _r, d, _f in os.walk(os.path.join(ROOT, "src")):
            d[:] = [x for x in d if x != "__pycache__"]
            for x in d:
                self.src_dirs.add(x)

    def test_no_bare_name_exclusion_matches_a_directory_inside_src(self):
        clash = self.src_dirs & set(self.pu.EXCLUDE_DIRS)
        self.assertEqual(clash, set(),
                         f"EXCLUDE_DIRS entries {sorted(clash)} also name real packages under src/; "
                         "they belong in EXCLUDE_ROOT_ONLY_DIRS")

    def test_the_tools_package_is_specifically_protected(self):
        self.assertIn("tools", self.src_dirs)
        self.assertNotIn("tools", self.pu.EXCLUDE_DIRS)
        self.assertIn("tools", self.pu.EXCLUDE_ROOT_ONLY_DIRS)

    def test_no_source_file_matches_a_stray_file_pattern(self):
        import fnmatch
        offenders = []
        for r, d, f in os.walk(os.path.join(ROOT, "src")):
            d[:] = [x for x in d if x != "__pycache__"]
            offenders.extend(
                os.path.join(r, name) for name in f
                if any(fnmatch.fnmatch(name, pat) for pat in self.pu.EXCLUDE_FILE_PATTERNS))
        self.assertEqual(offenders, [], f"these would be dropped from the zip: {offenders}")

    def test_the_package_directory_is_not_the_import_name(self):
        """The zip's single top-level folder becomes the installed plugin
        directory. Naming it `cartogen_ai` would shadow the namespace package
        the plugin imports from."""
        self.assertEqual(self.pu.PACKAGE_DIR, "cartogen_ai_plugin")
        # plugins.qgis.org requires the top-level folder to be a valid Python identifier, and it must
        # not be the importable name "cartogen_ai" itself (would shadow src/cartogen_ai).
        self.assertTrue(self.pu.PACKAGE_DIR.isidentifier())
        self.assertNotEqual(self.pu.PACKAGE_DIR, "cartogen_ai")

    def test_staging_files_dropped_in_the_repo_root_never_ship(self):
        import fnmatch
        for name in ("_register_page.html", "_reg_compact.json", "_repo_snapshot.tgz"):
            self.assertTrue(
                any(fnmatch.fnmatch(name, p) for p in self.pu.EXCLUDE_FILE_PATTERNS),
                f"{name} would ship")


class TestBuilderMachineLeftoversAreNotPackaged(unittest.TestCase):
    """The rc17 zip rebuilt by hand from a working checkout (2026-10-06) carried .ruff_cache/, an egg-info directory and, from a git
    worktree, a .git pointer file. A clean CI checkout has none of them, so this guards the by-hand build."""

    def test_caches_and_worktree_pointer_are_excluded(self):
        pu = _load()
        self.assertIn(".ruff_cache", pu.EXCLUDE_DIRS)
        self.assertIn(".git", pu.EXCLUDE_FILES)
        self.assertNotIn(".ruff_cache", {x for _r, ds, _f in os.walk(os.path.join(ROOT, "src")) for x in ds})


if __name__ == "__main__":
    unittest.main()


class TestHiddenFilesAndInternalDocsStayOut(unittest.TestCase):
    """2026-10-11 audit: a by-hand build carried a 92 KB .coverage file (gitignored, so a clean CI checkout never has it) and the whole
    docs/ tree, ~70 dated smoke reports, triage notes, scope studies and trackers, none of which does anything in an installed plugin."""

    def test_any_dotfile_or_dot_directory_is_hidden(self):
        pu = _load()
        for name in (".coverage", ".env", ".gitignore", ".hypothesis", ".DS_Store"):
            self.assertTrue(pu.is_hidden(name), name)
        self.assertFalse(pu.is_hidden("metadata.txt"))

    def test_only_user_facing_docs_ship(self):
        pu = _load()
        for ok in ("docs/USER_GUIDE.md", "docs/README.md", "docs/TOOLS_REFERENCE.md", "docs/images/dock-panel.png", "plugin_main.py",
                   "src/cartogen_ai/core/release_notes.py"):
            self.assertTrue(pu.docs_entry_ships(ok), ok)
        for bad in ("docs/BUG_TRACKER.md", "docs/IMPLEMENTATION_TRACKER.md", "docs/RC22_LIVE_SMOKE_REPORT_2026-10-09.md",
                    "docs/archive/CARTOGEN_AI_PRD.md", "docs/audits/QGIS_PLUGIN_FINDINGS.md", "docs/route_optimization_prototype.py"):
            self.assertFalse(pu.docs_entry_ships(bad), bad)

    def test_nothing_in_the_source_reads_a_docs_file_at_runtime(self):
        """If this ever fails, the file it reads must be added to SHIPPED_DOCS or the feature breaks in an installed plugin."""
        pu = _load()
        offenders = []
        for r, d, f in os.walk(os.path.join(ROOT, "src")):
            d[:] = [x for x in d if x != "__pycache__"]
            for name in f:
                if name.endswith(".py"):
                    text = pathlib.Path(os.path.join(r, name)).read_text(encoding="utf-8")
                    if any(q + "docs" + q in text for q in ('"', "'")) and "os.path.join" in text:
                        offenders.append(name)
        self.assertEqual(offenders, [], f"{offenders} may read docs/ at runtime; shipped docs are {sorted(pu.SHIPPED_DOCS)}")


class TestStaleBuildTreeStaysOut(unittest.TestCase):
    """2026-10-03 external audit F-05: a setuptools build/lib copy of the plugin rode into the release zip."""

    def test_build_is_excluded_and_no_real_source_dir_is_called_build(self):
        pu = _load()
        self.assertIn("build", pu.EXCLUDE_DIRS)
        for r, d, _f in os.walk(os.path.join(ROOT, "src")):
            d[:] = [x for x in d if x != "__pycache__"]
            self.assertNotIn("build", d, r)


class TestZonalStatisticsImportModule(unittest.TestCase):
    """2026-10-03 external audit F-03: QgsZonalStatistics is in qgis.analysis; qgis.core raised ImportError on 4.2.2."""

    def test_no_module_imports_it_from_qgis_core(self):
        import re
        bad = []
        for r, _d, files in os.walk(os.path.join(ROOT, "src")):
            for name in files:
                if name.endswith(".py"):
                    text = pathlib.Path(os.path.join(r, name)).read_text(encoding="utf-8")
                    if re.search(r"from qgis\.core import[^\n]*QgsZonalStatistics", text):
                        bad.append(name)
        self.assertEqual(bad, [])
