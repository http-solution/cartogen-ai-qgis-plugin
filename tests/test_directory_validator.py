"""The plugins.qgis.org upload checks, applied to the zip plugin_upload.py builds.

Reimplements the rules of qgis/QGIS-Django `qgis-app/plugins/validator.py` (read 2026-10-11) that do not need the network, so a
package the directory would refuse fails here instead of at upload: path rules, forbidden directories, no .pyc, package-name regexes,
the required [general] metadata, a readable icon, LICENSE at the top of the package, and the author rule. The URL reachability check the
directory also makes is not repeated here (no network in CI).
"""
import configparser
import importlib.util
import io
import os
import unittest
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REQUIRED = ("name", "description", "version", "qgisMinimumVersion", "author", "email", "about", "tracker", "repository")
MAX_BYTES = 25_000_000


def _build():
    spec = importlib.util.spec_from_file_location("plugin_upload", os.path.join(ROOT, "plugin_upload.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.package_plugin()


class TestZipPassesTheDirectoryChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import contextlib
        with contextlib.redirect_stdout(io.StringIO()):
            cls.path = _build()
        cls.zip = zipfile.ZipFile(cls.path)
        cls.names = cls.zip.namelist()
        cls.package = cls.names[0].split("/")[0]

    @classmethod
    def tearDownClass(cls):
        cls.zip.close()

    def test_size_is_within_the_upload_limit(self):
        self.assertLessEqual(os.path.getsize(self.path), MAX_BYTES)

    def test_no_path_traversal_pyc_or_forbidden_directory(self):
        for name in self.names:
            self.assertNotIn("..", name)
            self.assertFalse(name.startswith(os.path.sep), name)
            self.assertNotIn(".pyc", name)
            parts = name.split("/")
            for forbidden in ("__MACOSX", ".git", "__pycache__"):
                self.assertNotIn(forbidden, parts, name)

    def test_archive_is_not_corrupt(self):
        self.assertIsNone(self.zip.testzip())

    def test_single_top_level_folder_with_a_pep8_name(self):
        self.assertEqual({n.split("/")[0] for n in self.names}, {self.package})
        self.assertRegex(self.package, r"^[a-z_][a-z0-9_]*$")
        self.assertRegex(self.package, r"^[A-Za-z][A-Za-z0-9-_]+$")

    def test_init_metadata_license_and_icon_are_present(self):
        for rel in ("__init__.py", "metadata.txt", "LICENSE"):
            self.assertIn(f"{self.package}/{rel}", self.names, rel)
        meta = self._metadata()
        self.assertIn(f"{self.package}/{meta['icon']}", self.names)

    def test_required_metadata_and_author_rule(self):
        meta = self._metadata()
        self.assertEqual([k for k in REQUIRED if not meta.get(k)], [])
        self.assertRegex(meta["author"], r"^[^/]+$")
        for key in ("tracker", "repository", "homepage"):
            self.assertRegex(meta[key], r"^https?://[^/\s]+", key)

    def test_version_is_the_one_in_metadata_and_pyproject(self):
        meta = self._metadata()
        with open(os.path.join(ROOT, "pyproject.toml"), encoding="utf-8") as fh:
            self.assertIn(f'version = "{meta["version"]}"', fh.read())
        self.assertIn(meta["version"], os.path.basename(self.path))

    def _metadata(self):
        parser = configparser.ConfigParser()
        parser.optionxform = str
        parser.read_file(io.StringIO(self.zip.read(f"{self.package}/metadata.txt").decode("utf-8")))
        return dict(parser.items("general"))


if __name__ == "__main__":
    unittest.main()
