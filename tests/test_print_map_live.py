"""print_map writes a real PDF in the QGIS image CI uses (rc48 hand test A22: every PDF export raised "QPdfWriter object has no attribute
layout" after creating the file). Written without a QGIS install: CI's first run is its first execution."""
import os
import tempfile
import unittest

try:
    from qgis.gui import QgsMapCanvas
    LIVE = True
except ImportError:
    LIVE = False


class _FakeIface:
    def __init__(self, canvas):
        self._canvas = canvas

    def mapCanvas(self):
        return self._canvas


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestPrintMapPdf(unittest.TestCase):
    def setUp(self):
        from tests.test_network_units_live import _boot
        why = _boot()
        if why:
            self.skipTest(why)
        from cartogen_ai.core.agent.tools import export_tools
        self.export_tools = export_tools
        self.canvas = QgsMapCanvas()
        self.canvas.resize(400, 300)
        self.original_iface = export_tools.iface
        export_tools.iface = _FakeIface(self.canvas)
        self.addCleanup(setattr, export_tools, "iface", self.original_iface)
        self.folder = tempfile.mkdtemp()

    def test_a_pdf_is_written_and_is_a_pdf(self):
        path = os.path.join(self.folder, "map.pdf")
        result = self.export_tools.print_map(output_path=path)
        print(f"PRINTMAPRESULT {result}")
        self.assertTrue(result.get("success"), result)
        with open(path, "rb") as fh:
            self.assertEqual(fh.read(5), b"%PDF-")


if __name__ == "__main__":
    unittest.main()
