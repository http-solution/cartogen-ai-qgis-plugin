"""pyproject.toml must list the runtime JSON the code opens next to itself (audit F30, #166).

A real wheel build/install is not run by this test (too slow for the unit suite). It WAS done by hand on 2026-10-06 (pip wheel, then
a clean venv: the task register and both contracts load); this test only checks that every declared package-data pattern matches an
existing file, that the two known resources are declared, and that the wheel metadata matches the plugin's version and dependencies."""
import glob
import os
import unittest

try:
    import tomllib
except ImportError:  # pragma: no cover - Python < 3.11
    tomllib = None

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@unittest.skipIf(tomllib is None, "tomllib needs Python 3.11+")
class TestPackageData(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(ROOT, "pyproject.toml"), "rb") as fh:
            self.cfg = tomllib.load(fh)

    def test_runtime_json_is_declared_and_exists(self):
        data = self.cfg["tool"]["setuptools"]["package-data"]
        self.assertIn("task_register.json", data["cartogen_ai.core.agent"])
        self.assertIn("contracts/*.json", data["cartogen_ai.core.validators"])
        # "cartogen_ai.core" = ["*.md"] predates this and matches nothing; not this test's concern.
        for package in ("cartogen_ai.core.agent", "cartogen_ai.core.validators"):
            patterns = data[package]
            base = os.path.join(ROOT, "src", *package.split("."))
            for pattern in patterns:
                self.assertTrue(glob.glob(os.path.join(base, pattern)), f"{package}: {pattern} matches nothing")

    def test_python_floor_matches_lint_and_type_targets(self):
        self.assertEqual(self.cfg["project"]["requires-python"], ">=3.10")
        self.assertEqual(self.cfg["tool"]["ruff"]["target-version"], "py310")
        self.assertEqual(self.cfg["tool"]["mypy"]["python_version"], "3.10")


class TestWheelMetadataMatchesThePlugin(unittest.TestCase):
    """pyproject.toml said 1.16.0-rc12 for seven releases because its comment said "kept in sync by hand". A wheel built from it
    would have claimed to be rc12 (audit F30 / #166 re-check, 2026-10-06)."""

    def _read(self, name):
        import os
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, name), encoding="utf-8") as fh:
            return fh.read()

    def test_pyproject_version_equals_metadata_version(self):
        import re
        meta = re.search(r"^version=(\S+)", self._read("metadata.txt"), re.M).group(1)
        proj = re.search(r'^version\s*=\s*"([^"]+)"', self._read("pyproject.toml"), re.M).group(1)
        self.assertEqual(proj, meta)

    def test_the_wheel_declares_requests_and_ships_the_runtime_json(self):
        text = self._read("pyproject.toml")
        self.assertIn('dependencies = ["requests"]', text)
        self.assertIn('"cartogen_ai.core.agent" = ["task_register.json"]', text)
        self.assertIn('"cartogen_ai.core.validators" = ["contracts/*.json"]', text)
