"""The CI crash-isolation control script must use Qt6 enums: it passed the int 1 to addDockWidget, which raised TypeError on every QGIS 4 run, so the
control never reached its exit check (found 2026-10-24 in a CI log). Checked by reading the source, since the script needs QGIS."""
import ast
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestControlProcessScript(unittest.TestCase):
    def test_add_dock_widget_gets_the_enum_not_an_int(self):
        with open(os.path.join(ROOT, "tests", "_ci_qgis_control_process.py"), encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "addDockWidget"]
        self.assertTrue(calls)
        for call in calls:
            self.assertNotIsInstance(call.args[0], ast.Constant, "addDockWidget needs Qt.DockWidgetArea.<Area>, not a bare number")


if __name__ == "__main__":
    unittest.main()
