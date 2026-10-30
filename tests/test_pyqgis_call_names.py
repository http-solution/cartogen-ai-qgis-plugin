"""API-name ratchet: a call to a camelCase method that is neither in the QGIS 4.2 Python API nor on the reviewed Qt/other list fails the build.

Why (2026-10-16): checking the plugin against the QGIS 4.2.3 developer reference found five calls to methods that do not exist
(QgsMapCanvas.previousExtentsAvailable/nextExtentsAvailable, QgsGeometry.isGeomValid, QgsNetworkAccessManager.fallbackProxySettings,
QgsPointDisplacementRenderer.setCircleRadiusSymbol). Three of them sat under a mock that accepts any attribute (the unit test passed) or a
contextlib.suppress (proxy detection silently never worked), and CI has no canvas, so nothing ever failed. This test cannot prove a call is
valid on the object it is made on; it catches the commonest slip, a method name that does not exist anywhere.

tests/fixtures/pyqgis_4_2_names.txt holds the method, attribute, property and class names of the QGIS 4.2 Python API (names only, taken from the
developer reference built from qgis.org/pyqgis/4.2). If a new call is a Qt (not QGIS) method, add it to QT_AND_OTHER with a word on what it is."""
import ast
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Reviewed 2026-10-16 (setToolButtonStyle added 2026-10-28: QToolButton.setToolButtonStyle, the Settings collapsible heading; pointSizeF, setPointSizeF, setCurrentItem, setFixedWidth and setHorizontalScrollBarPolicy added 2026-10-30: QFont, QListWidget and QWidget methods used by the Connections window): every name here is a Qt (widgets, network, text, undo stack, date) method, not a QGIS one.
QT_AND_OTHER = frozenset({'hsvSaturation', 'pointSizeF', 'setPointSizeF', 'setCurrentItem', 'setFixedWidth', 'setHorizontalScrollBarPolicy', 'pixelColor', 'sceneBoundingRect', 'setPixelSize', 'addItems', 'addQueryItem', 'addStretch', 'blockSignals', 'bytesAvailable', 'canRedo', 'canUndo', 'characterCount', 'childFrames', 'currentData', 'currentThread', 'findData', 'findText', 'fromLocalFile', 'getOpenFileName', 'getSaveFileName', 'hasQuery', 'insertBlock', 'insertHtml', 'insertWidget', 'isFloating', 'isMetered', 'loadDefaultBackend', 'moveCursor', 'movePosition', 'paintRectPixels', 'primaryScreen', 'processEvents', 'queryItemValue', 'readAll', 'redoText', 'removeSelectedText', 'rootFrame', 'setAllowedAreas', 'setContentsMargins', 'setCurrentText', 'setEchoMode', 'setExclusive', 'setFixedHeight', 'setFocus', 'setFrameShape', 'setMaxLength', 'setMaximumHeight', 'setObjectName', 'setOpenExternalLinks', 'setOpenLinks', 'setPlainText', 'setRawHeader', 'setReadBufferSize', 'setSingleShot', 'setTabChangesFocus', 'setToolButtonStyle', 'setTransferTimeout', 'setWidgetResizable', 'setWindowTitle', 'setWordWrap', 'singleShot', 'takeAt', 'toLocalFile', 'toPyDate', 'undoText', 'verticalScrollBar'})


def _qgis_names():
    with open(os.path.join(ROOT, "tests", "fixtures", "pyqgis_4_2_names.txt"), encoding="utf-8") as fh:
        return {line.strip() for line in fh if line.strip()}


def _called_camel_case_names():
    found = {}
    for folder, _dirs, files in os.walk(os.path.join(ROOT, "src")):
        for name in files:
            if not name.endswith(".py"):
                continue
            path = os.path.join(folder, name)
            with open(path, encoding="utf-8") as fh:
                tree = ast.parse(fh.read())
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and re.match(r"^[a-z]+[A-Z]\w*$", node.func.attr):
                    found.setdefault(node.func.attr, f"{os.path.relpath(path, ROOT)}:{node.lineno}")
    return found


class TestPyqgisCallNames(unittest.TestCase):
    def test_the_name_list_is_the_real_one(self):
        names = _qgis_names()
        self.assertGreater(len(names), 15000)
        for known in ("isGeosValid", "zoomToPreviousExtent", "fallbackProxy", "setExtrusionHeight", "setClamping"):
            self.assertIn(known, names)
        for gone in ("isGeomValid", "previousExtentsAvailable", "nextExtentsAvailable", "fallbackProxySettings", "setCircleRadiusSymbol"):
            self.assertNotIn(gone, names)

    def test_no_call_to_a_method_that_exists_nowhere(self):
        names = _qgis_names()
        unknown = {k: v for k, v in _called_camel_case_names().items() if k not in names and k not in QT_AND_OTHER}
        self.assertEqual(unknown, {}, "\n".join(f"{k}  first seen at {v}" for k, v in sorted(unknown.items())))


if __name__ == "__main__":
    unittest.main()
