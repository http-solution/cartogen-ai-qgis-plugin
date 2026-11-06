"""Hand run 2026-11-04 (row W13, Windows 11): the Help said 'Qt 6.11.0' while QGIS's own About window said 6.11.1. QT_VERSION_STR is the version PyQt was BUILT
against; QtCore.qVersion() is the Qt library the process is actually running. The Help line must report the second."""
import types
import unittest

from cartogen_ai.core import environment as env


def fake_qtcore(built, running=None):
    module = types.SimpleNamespace(QT_VERSION_STR=built)
    if running is not None:
        module.qVersion = lambda: running
    return module


class TestQtVersionIsTheRuntimeOne(unittest.TestCase):
    def test_the_running_library_wins_over_the_build_constant(self):
        self.assertEqual(env.qt_version_text(fake_qtcore("6.11.0", "6.11.1")), "6.11.1")

    def test_without_qversion_the_build_constant_is_used(self):
        self.assertEqual(env.qt_version_text(fake_qtcore("6.11.0")), "6.11.0")

    def test_a_qversion_that_fails_or_is_empty_falls_back(self):
        broken = fake_qtcore("6.8.1")
        broken.qVersion = lambda: (_ for _ in ()).throw(RuntimeError("no Qt"))
        self.assertEqual(env.qt_version_text(broken), "6.8.1")
        self.assertEqual(env.qt_version_text(fake_qtcore("6.8.1", "")), "6.8.1")

    def test_nothing_readable_is_empty_not_an_error(self):
        self.assertEqual(env.qt_version_text(types.SimpleNamespace()), "")


if __name__ == "__main__":
    unittest.main()


class TestTheBuiltVersionIsShownOnlyWhenItDiffers(unittest.TestCase):
    """Round 2 (2026-11-05, row W13): the Help said Qt 6.11.1 and the tester's console 6.11.0. When the running Qt and the PyQt build constant differ the line says so."""
    def test_the_built_version_is_read(self):
        self.assertEqual(env.qt_built_text(fake_qtcore("6.11.0", "6.11.1")), "6.11.0")
        self.assertEqual(env.qt_built_text(types.SimpleNamespace()), "")

    def test_describe_names_the_build_only_when_it_differs(self):
        base = {"os": "Windows", "os_release": "11", "arch": "AMD64", "python": "3.12.1", "qgis": "4.2.3", "qt": "6.11.1"}
        self.assertIn("Qt 6.11.1 (PyQt built with 6.11.0)", env.describe({**base, "qt_built": "6.11.0"}))
        self.assertNotIn("built with", env.describe(base))

    def test_detect_adds_the_key_only_on_a_difference(self):
        import sys
        from unittest.mock import patch
        for built, running, expect in (("6.11.0", "6.11.1", "6.11.0"), ("6.11.1", "6.11.1", None)):
            qtcore = fake_qtcore(built, running)
            pyqt = types.SimpleNamespace(QtCore=qtcore)
            with patch.dict(sys.modules, {"qgis": types.SimpleNamespace(PyQt=pyqt), "qgis.PyQt": pyqt, "qgis.PyQt.QtCore": qtcore}):
                self.assertEqual(env.detect().get("qt_built"), expect, (built, running))
