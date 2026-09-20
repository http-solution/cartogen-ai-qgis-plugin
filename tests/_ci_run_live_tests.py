# -*- coding: utf-8 -*-
"""CI-only test runner, added 2026-09-20/21 per external review: runs the same live-QGIS
test modules `python3 -m unittest tests.test_chat_widget_live tests.test_plugin_main_live`
would, but as a script rather than unittest's own CLI entry point, so it can explicitly call
QgsApplication.exitQgis() and process.exit() itself BEFORE the interpreter's own implicit
shutdown -- unittest's CLI path never does this, leaving Qt/QGIS's C++ objects to be
destroyed by Python's own interpreter-exit machinery instead of an orderly exitQgis() call.
If explicit teardown here eliminates the post-test "Segmentation fault (core dumped)" seen
in CI, that's a real fix (this becomes the permanent way this job runs its live tests). If
it does NOT eliminate it, that's real evidence the crash is unrelated to teardown ordering.

Both outcomes are useful signal for .github/workflows/tests.yml's own segfault-waiver
step -- run tests/_ci_qgis_control_process.py alongside this to also test whether a
plugin-code-free QGIS session hits the same crash independent of anything here."""
import sys
import unittest

loader = unittest.TestLoader()
suite = unittest.TestSuite()
suite.addTests(loader.loadTestsFromName("tests.test_chat_widget_live"))
suite.addTests(loader.loadTestsFromName("tests.test_plugin_main_live"))

runner = unittest.TextTestRunner(verbosity=2)
result = runner.run(suite)

try:
    from qgis.core import QgsApplication
    app = QgsApplication.instance()
    if app is not None:
        print("Explicitly calling QgsApplication.exitQgis() before process exit...")
        app.exitQgis()
        print("exitQgis() returned normally.")
except Exception as e:
    print(f"exitQgis() teardown itself raised: {e!r}")

sys.exit(0 if result.wasSuccessful() else 1)
