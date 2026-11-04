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
