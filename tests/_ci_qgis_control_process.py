# -*- coding: utf-8 -*-
"""CI-only diagnostic, added 2026-09-20/21 per external review: isolates whether the
post-test "Segmentation fault (core dumped)" seen in qgis-live-tests is a QGIS/Qt
interpreter-shutdown issue in the CI image itself, independent of this repo's code --
or whether it's actually caused by something in this plugin's own test/teardown path.

Boots a real QgsApplication, creates and tears down a couple of plain Qt widgets (no
cartogen_ai import at all -- not even on sys.path), then explicitly calls exitQgis()
before process exit. If THIS also segfaults with the same signature (exit 139 +
"Segmentation fault"), that's real evidence the crash is environment-level, not a
plugin regression. If it does NOT segfault, that's real evidence pointing back at this
repo's own test/teardown code, and the CI waiver for the real test step should not be
trusted without further investigation.

Not a unittest module -- deliberately run as a standalone script by
.github/workflows/tests.yml's own "Minimal QGIS-only crash-isolation control" step."""
import sys

from qgis.core import QgsApplication
from qgis.PyQt.QtWidgets import QMainWindow, QDockWidget, QTextEdit
from qgis.PyQt.QtTest import QTest

app = QgsApplication([], False)
app.initQgis()

win = QMainWindow()
dock = QDockWidget("control", win)
edit = QTextEdit()
edit.setPlainText("control process -- no plugin code involved")
dock.setWidget(edit)
win.addDockWidget(1, dock)
win.show()
QTest.qWait(50)
dock.close()
win.close()

print("CONTROL PROCESS: widgets created and closed OK")

# The explicit teardown this diagnostic exists to test -- see module docstring.
app.exitQgis()

print("CONTROL PROCESS: exitQgis() completed OK")
sys.exit(0)
