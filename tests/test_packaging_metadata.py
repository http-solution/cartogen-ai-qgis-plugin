"""pyproject.toml must list the runtime JSON the code opens next to itself (audit F30, #166).

A real wheel build/install is not exercised here (setuptools in this sandbox cannot build one); this only checks that every
declared package-data pattern matches an existing file and that the two known resources are declared."""
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
