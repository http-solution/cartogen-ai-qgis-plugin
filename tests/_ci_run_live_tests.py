# -*- coding: utf-8 -*-
"""CI-only test runner, added 2026-09-20/21 per external review: runs the same live-QGIS
test modules `python3 -m unittest tests.test_chat_widget_live tests.test_plugin_main_live
tests.test_network_units_live
tests.test_network_background_live
tests.test_network_clip_live`
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
import gc
import sys
import unittest

loader = unittest.TestLoader()
suite = unittest.TestSuite()
suite.addTests(loader.loadTestsFromName("tests.test_chat_widget_live"))
suite.addTests(loader.loadTestsFromName("tests.test_plugin_main_live"))
suite.addTests(loader.loadTestsFromName("tests.test_network_units_live"))
suite.addTests(loader.loadTestsFromName("tests.test_network_background_live"))
suite.addTests(loader.loadTestsFromName("tests.test_network_clip_live"))
suite.addTests(loader.loadTestsFromName("tests.test_rc8_live"))
suite.addTests(loader.loadTestsFromName("tests.test_facility_access_live"))
suite.addTests(loader.loadTestsFromName("tests.test_worldpop_clip_live"))
suite.addTests(loader.loadTestsFromName("tests.test_chat_transcript_live"))
suite.addTests(loader.loadTestsFromName("tests.test_rc9_live"))
suite.addTests(loader.loadTestsFromName("tests.test_routing_style_live"))
suite.addTests(loader.loadTestsFromName("tests.test_output_style_live"))
suite.addTests(loader.loadTestsFromName("tests.test_project_tidy_live"))
suite.addTests(loader.loadTestsFromName("tests.test_processing_provider_live"))
suite.addTests(loader.loadTestsFromName("tests.test_edit_session_live"))
suite.addTests(loader.loadTestsFromName("tests.test_barrier_tools_live"))
suite.addTests(loader.loadTestsFromName("tests.test_script_isolation_reconcile_live"))

runner = unittest.TextTestRunner(verbosity=2)
result = runner.run(suite)

# Diagnostic finding, 2026-09-21: exitQgis() alone (below) does NOT eliminate the
# post-"OK" crash -- reproduced independently on Windows/QGIS 4.2.2 local AND Linux
# CI, crashing between runner.run() returning and the exitQgis() call even being
# reached. Each of the ~40 test methods across these two modules creates a real
# QDockWidget (test_chat_widget_live.py's _make_dock) with addCleanup(dock.close) --
# .close() alone does not destroy the underlying C++ object, so ~40 live-but-closed
# widgets (each owning child QTimers, e.g. chat_tab_widget.py's
# _plan_spinner_timer) accumulate for the whole run and only get garbage-collected
# whenever Python's refcounting happens to drop the last reference -- potentially
# interleaved with the interpreter's own shutdown sequence, which is the likely
# trigger. Forcing collection AND pumping the Qt event loop HERE, while
# QApplication is still fully alive, makes any deferred deleteLater() cleanup
# actually run now instead of landing in that unsafe window.
# Second-review correction, 2026-09-21: both blocks below used to catch their own
# exception and only print it -- teardown_ok tracked nothing, so a real failure in
# either the cleanup pump or exitQgis() itself was invisible to the final exit code.
# For a process-stability gate, a teardown exception must fail the run, not just be
# logged -- this whole script exists to prove teardown completes cleanly, so an
# exception here IS the failure being tested for.
teardown_ok = True

try:
    from qgis.PyQt.QtCore import QCoreApplication, QEventLoop, QTimer
    gc.collect()
    if QCoreApplication.instance() is not None:
        loop = QEventLoop()
        QTimer.singleShot(300, loop.quit)
        loop.exec()
    gc.collect()
    print("Post-test gc.collect() + Qt event loop pump completed.")
except Exception as e:
    print(f"Post-test cleanup pump itself raised: {e!r}")
    teardown_ok = False

try:
    from qgis.core import QgsApplication
    app = QgsApplication.instance()
    if app is not None:
        print("Explicitly calling QgsApplication.exitQgis() before process exit...")
        app.exitQgis()
        print("exitQgis() returned normally.")
except Exception as e:
    print(f"exitQgis() teardown itself raised: {e!r}")
    teardown_ok = False

sys.exit(0 if (result.wasSuccessful() and teardown_ok) else 1)
