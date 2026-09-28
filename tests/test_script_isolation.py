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

    def _windows_fixture(self, layout):
        """Builds a real temp directory tree and patches sys.prefix/
        base_prefix/exec_prefix/platform to point at it -- real filesystem
        fixtures instead of deep Path mocking, which the 2026-09-28 widened
        search (checking base_prefix/exec_prefix and an apps/Python3* child
        too, after a live-reported worker timeout traced to this lookup
        missing a real QGIS-for-Windows layout) made too awkward to mock
        faithfully. `layout` is a list of relative paths to create as empty
        files under a fresh temp dir, e.g. ["apps/Python312/python.exe"]."""
        import tempfile
        tmpdir = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, tmpdir, True)
        for rel in layout:
            full = os.path.join(tmpdir, rel)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            open(full, "w").close()
        return tmpdir

    def test_windows_finds_python_exe_directly_under_prefix(self):
        tmpdir = self._windows_fixture(["python.exe"])
        with patch.object(si.sys, "prefix", tmpdir),              patch.object(si.sys, "base_prefix", tmpdir),              patch.object(si.sys, "exec_prefix", tmpdir),              patch.object(si.sys, "platform", "win32"):
            result = si.find_python_interpreter()
        self.assertEqual(result, os.path.join(tmpdir, "python.exe"))

    def test_windows_finds_python_exe_under_an_apps_python3_child_dir(self):
        # The real gap the widened search (2026-09-28) closes: some QGIS-for-
        # Windows layouts put the bundled interpreter one level down from
        # sys.prefix, under apps\Python3XX\, not at the prefix root itself.
        tmpdir = self._windows_fixture(["apps/Python312/python.exe"])
        with patch.object(si.sys, "prefix", tmpdir),              patch.object(si.sys, "base_prefix", tmpdir),              patch.object(si.sys, "exec_prefix", tmpdir),              patch.object(si.sys, "platform", "win32"):
            result = si.find_python_interpreter()
        self.assertEqual(result, os.path.join(tmpdir, "apps", "Python312", "python.exe"))

    def test_windows_checks_base_prefix_and_exec_prefix_too(self):
        # sys.prefix alone can differ from base_prefix/exec_prefix under a
        # venv-like setup -- the interpreter can live under either.
        tmpdir = self._windows_fixture(["python.exe"])
        empty_dir = self._windows_fixture([])
        with patch.object(si.sys, "prefix", empty_dir),              patch.object(si.sys, "base_prefix", tmpdir),              patch.object(si.sys, "exec_prefix", empty_dir),              patch.object(si.sys, "platform", "win32"):
            result = si.find_python_interpreter()
        self.assertEqual(result, os.path.join(tmpdir, "python.exe"))

    def test_windows_falls_back_to_sys_executable_when_nothing_found(self):
        tmpdir = self._windows_fixture([])
        with patch.object(si.sys, "prefix", tmpdir),              patch.object(si.sys, "base_prefix", tmpdir),              patch.object(si.sys, "exec_prefix", tmpdir),              patch.object(si.sys, "platform", "win32"):
            result = si.find_python_interpreter()
        self.assertEqual(result, sys.executable)


class TestQgisBinaryRefusal(unittest.TestCase):
    """§ script_isolation.py's _QGIS_BINARY_BASENAMES / _ensure_started's fast
    refusal, added 2026-09-28 after a live-reported worker timeout traced to
    a wrong interpreter lookup silently spawning the QGIS binary itself
    instead of Python, which then hung for the full job timeout with no
    diagnostic at all."""

    def test_known_qgis_basenames_are_flagged(self):
        from pathlib import Path
        for name in si._QGIS_BINARY_BASENAMES:
            self.assertIn(Path(name).name, si._QGIS_BINARY_BASENAMES)

    def test_a_real_python_basename_is_not_flagged(self):
        from pathlib import Path
        for name in ("python.exe", "python3.exe", "python3", "python"):
            self.assertNotIn(Path(name).name, si._QGIS_BINARY_BASENAMES)


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
        with patch.object(si, "_plugin_parent_dir", return_value="/fake/src"),              patch.object(si, "_qgis_sys_path_entries", return_value=[]):
            env = si._build_worker_environment()
        self.assertIn("/fake/src", env.get("PYTHONPATH", ""))

    def test_prepends_plugin_parent_without_dropping_existing_pythonpath(self):
        with patch.object(si, "_plugin_parent_dir", return_value="/fake/src"),              patch.object(si, "_qgis_sys_path_entries", return_value=[]):
            with patch.dict(os.environ, {"PYTHONPATH": "/other/existing/path"}, clear=False):
                env = si._build_worker_environment()
        parts = env["PYTHONPATH"].split(os.pathsep)
        self.assertEqual(parts[0], "/fake/src")
        self.assertIn("/other/existing/path", parts)

    def test_includes_the_live_processs_own_sys_path_entries(self):
        # The real 2026-09-28 live report this closes: a CORRECTLY resolved real
        # Python interpreter (not the QGIS-binary misdetection _QGIS_BINARY_BASENAMES
        # guards against) still failed with "No module named 'qgis'", because the
        # qgis bindings directory was on THIS process's sys.path (added by QGIS's
        # own C++ bootstrap at embed time) but never exported as a PYTHONPATH env var
        # for a spawned subprocess to inherit.
        fake_qgis_dir = os.path.dirname(os.path.abspath(__file__))  # any real, existing dir
        with patch.object(si, "_plugin_parent_dir", return_value=None),              patch.object(si.sys, "path", [fake_qgis_dir, "", "/does/not/exist"]):
            env = si._build_worker_environment()
        self.assertIn(fake_qgis_dir, env.get("PYTHONPATH", "").split(os.pathsep))

    def test_deduplicates_pythonpath_entries(self):
        fake_dir = os.path.dirname(os.path.abspath(__file__))
        with patch.object(si, "_plugin_parent_dir", return_value=fake_dir),              patch.object(si.sys, "path", [fake_dir]):
            env = si._build_worker_environment()
        parts = env["PYTHONPATH"].split(os.pathsep)
        self.assertEqual(parts.count(fake_dir), 1)


class TestPluginParentDir(unittest.TestCase):
    def test_resolves_to_the_directory_containing_the_cartogen_ai_package(self):
        parent = si._plugin_parent_dir()
        self.assertIsNotNone(parent)
        self.assertTrue(os.path.isdir(os.path.join(parent, "cartogen_ai")))


class TestEnsureStartedRefusesQgisBinary(unittest.TestCase):
    """_ensure_started()'s fast-refusal branch never reaches subprocess.Popen at
    all for a QGIS-basename interpreter, so it's exercisable without a real
    QGIS process or spawning anything -- unlike the rest of _IsolationWorker,
    which is live-QGIS-only (tests/manual_isolation_bench/)."""

    def test_refuses_without_attempting_to_spawn(self):
        worker = si._IsolationWorker()
        with patch.object(si, "find_python_interpreter", return_value="/usr/bin/qgis-bin.exe"),              patch.object(si.subprocess, "Popen") as mock_popen:
            error = worker._ensure_started()
        self.assertIsNotNone(error)
        self.assertIn("QGIS application binary", error["error"])
        mock_popen.assert_not_called()

    def test_a_real_interpreter_name_is_not_refused_by_this_check(self):
        # Doesn't assert success (that needs a real spawnable interpreter --
        # live-QGIS-only) -- just that the basename check itself doesn't
        # reject a legitimate name before Popen is even attempted.
        worker = si._IsolationWorker()
        with patch.object(si, "find_python_interpreter", return_value="/usr/bin/python3"),              patch.object(si.subprocess, "Popen", side_effect=OSError("boom, not actually spawned")):
            error = worker._ensure_started()
        self.assertIsNotNone(error)
        self.assertNotIn("QGIS application binary", error["error"])


class TestEnsureStartedSuppressesConsoleWindow(unittest.TestCase):
    """Live-reported, 2026-09-28: a visible (blank) console window opened during the
    isolation call on real Windows QGIS -- stdin/stdout/stderr are already fully
    redirected to pipes, so Windows was allocating a console for the spawned python.exe
    purely because the parent (QGIS, a GUI app) has none of its own to inherit."""

    def test_popen_receives_a_creationflags_kwarg(self):
        worker = si._IsolationWorker()
        with patch.object(si, "find_python_interpreter", return_value="/usr/bin/python3"),              patch.object(si.subprocess, "Popen", side_effect=OSError("boom, not actually spawned")) as mock_popen:
            worker._ensure_started()
        self.assertIn("creationflags", mock_popen.call_args.kwargs)
        self.assertEqual(
            mock_popen.call_args.kwargs["creationflags"],
            getattr(si.subprocess, "CREATE_NO_WINDOW", 0),
        )

    def test_uses_the_real_windows_constant_when_present(self):
        # This machine is Linux (no CREATE_NO_WINDOW attribute at all), so simulate a
        # Windows subprocess module to prove the value threads through unchanged rather
        # than being hardcoded to 0.
        worker = si._IsolationWorker()
        with patch.object(si, "find_python_interpreter", return_value="/usr/bin/python3"),              patch.object(si.subprocess, "CREATE_NO_WINDOW", 0x08000000, create=True),              patch.object(si.subprocess, "Popen", side_effect=OSError("boom, not actually spawned")) as mock_popen:
            worker._ensure_started()
        self.assertEqual(mock_popen.call_args.kwargs["creationflags"], 0x08000000)


if __name__ == "__main__":
    unittest.main()
