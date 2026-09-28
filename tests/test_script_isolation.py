# -*- coding: utf-8 -*-
"""
Unit tests for agent/services/script_isolation.py's QGIS-free pure logic --
interpreter lookup and worker-environment construction. These run on the
plain `test` CI job (no QGIS needed, same as this module's own top-level
try/except ImportError guard). The actual subprocess round-trip against a
real QgsProject is live-QGIS-only and lives in
tests/manual_isolation_bench/ instead (matching the Phase 0 benchmark
harness's own convention -- see IMPLEMENTATION_TRACKER.md §1.11's Phase 1
build update for why a full subprocess-spawning test isn't in this suite).
"""
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

from cartogen_ai.core.agent.services import script_isolation as si


class TestFindPythonInterpreter(unittest.TestCase):
    def test_linux_uses_sys_executable_directly(self):
        """The Linux branch is live-verified against the real qgis/qgis Docker
        image this repo's CI pins (IMPLEMENTATION_TRACKER.md §1.11's Phase 1
        build note) -- sys.executable is already correct there, unlike Windows/
        macOS where it can be the QGIS binary itself."""
        with patch.object(si.sys, "platform", "linux"):
            with patch.object(si, "Path") as mock_path_cls:
                mock_path_cls.return_value.__truediv__ = lambda self, other: MagicMock(exists=lambda: False)
                result = si.find_python_interpreter()
        self.assertEqual(result, sys.executable)

    def test_conda_install_uses_python_shortcut(self):
        with patch.object(si.sys, "prefix", "/opt/conda/envs/qgis"):
            with patch("pathlib.Path.exists", return_value=True):
                result = si.find_python_interpreter()
        self.assertEqual(result, "python")

    def test_windows_finds_python_exe_next_to_prefix(self):
        fake_prefix = MagicMock()
        fake_conda_meta = MagicMock(exists=lambda: False)
        fake_prefix.__truediv__ = MagicMock(side_effect=lambda name: {
            "conda-meta": fake_conda_meta,
            "python.exe": MagicMock(exists=lambda: True, __str__=lambda self: r"C:\OSGeo4W\apps\Python312\python.exe"),
        }.get(name, MagicMock(exists=lambda: False)))

        with patch.object(si, "Path", return_value=fake_prefix):
            with patch.object(si.sys, "platform", "win32"):
                result = si.find_python_interpreter()
        self.assertEqual(result, r"C:\OSGeo4W\apps\Python312\python.exe")

    def test_windows_falls_back_to_sys_executable_when_nothing_found(self):
        fake_prefix = MagicMock()
        fake_prefix.__truediv__ = MagicMock(return_value=MagicMock(exists=lambda: False))

        with patch.object(si, "Path", return_value=fake_prefix):
            with patch.object(si.sys, "platform", "win32"):
                result = si.find_python_interpreter()
        self.assertEqual(result, sys.executable)


class TestBuildWorkerEnvironment(unittest.TestCase):
    def test_strips_unrelated_environment_variables(self):
        with patch.dict(os.environ, {"SOME_UNRELATED_SECRET": "shhh", "PATH": "/usr/bin"}, clear=False):
            env = si._build_worker_environment()
        self.assertNotIn("SOME_UNRELATED_SECRET", env)
        self.assertIn("PATH", env)

    def test_keeps_qgis_gdal_proj_prefixed_variables(self):
        with patch.dict(os.environ, {"QGIS_PREFIX_PATH": "/usr", "GDAL_DATA": "/usr/share/gdal", "PROJ_LIB": "/usr/share/proj"}, clear=False):
            env = si._build_worker_environment()
        self.assertEqual(env.get("QGIS_PREFIX_PATH"), "/usr")
        self.assertEqual(env.get("GDAL_DATA"), "/usr/share/gdal")
        self.assertEqual(env.get("PROJ_LIB"), "/usr/share/proj")

    def test_sets_offscreen_qt_platform_by_default(self):
        env = si._build_worker_environment()
        self.assertEqual(env.get("QT_QPA_PLATFORM"), "offscreen")

    def test_does_not_override_an_explicit_qt_platform(self):
        with patch.dict(os.environ, {"QT_QPA_PLATFORM": "xcb"}, clear=False):
            env = si._build_worker_environment()
        self.assertEqual(env.get("QT_QPA_PLATFORM"), "xcb")

    def test_adds_plugin_parent_to_pythonpath(self):
        with patch.object(si, "_plugin_parent_dir", return_value="/fake/src"):
            env = si._build_worker_environment()
        self.assertIn("/fake/src", env.get("PYTHONPATH", ""))

    def test_prepends_plugin_parent_without_dropping_existing_pythonpath(self):
        with patch.object(si, "_plugin_parent_dir", return_value="/fake/src"):
            with patch.dict(os.environ, {"PYTHONPATH": "/other/existing/path"}, clear=False):
                env = si._build_worker_environment()
        parts = env["PYTHONPATH"].split(os.pathsep)
        self.assertEqual(parts[0], "/fake/src")
        self.assertIn("/other/existing/path", parts)


class TestPluginParentDir(unittest.TestCase):
    def test_resolves_to_the_directory_containing_the_cartogen_ai_package(self):
        parent = si._plugin_parent_dir()
        self.assertIsNotNone(parent)
        self.assertTrue(os.path.isdir(os.path.join(parent, "cartogen_ai")))


if __name__ == "__main__":
    unittest.main()
