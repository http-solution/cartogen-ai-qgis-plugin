"""Live check of the smoke card dock (tools/smoke_dock.py) on real QGIS/Qt: the buttons drive the session, a result click takes the evidence through the snapshot callback and writes the line, a result
before Start is refused, Skip works on a row never started, and a wrong QGIS version shows the warning. The real evidence collector (window.grab) needs a desktop and is not exercised here. Written without
a QGIS install: CI's first run is its first execution."""
import sys
import tempfile
import unittest
from pathlib import Path

try:
    from qgis.core import QgsProject  # noqa: F401
    LIVE = True
except ImportError:
    LIVE = False

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestSmokeDock(unittest.TestCase):
    def setUp(self):
        from tests.test_chat_widget_live import _boot_qgis
        _boot_qgis()
        import smoke_cards as sc
        import smoke_dock
        self.sc, self.smoke_dock = sc, smoke_dock
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cards = [{"id": "X1", "title": "one", "can_run": True, "why_not": "", "do": "Do a thing.", "expect": "", "pass_if": "", "starts_from": "", "also_capture": "",
                       "machine_checked_by": []},
                      {"id": "X2", "title": "two", "can_run": False, "why_not": "needs GeoDa", "do": "", "expect": "", "pass_if": "", "starts_from": "", "also_capture": "",
                       "machine_checked_by": []}]
        self.taken = []
        self.session = sc.Session(self.tmp.name, self.cards, lambda row, note: self.taken.append((row, note)))
        self.dock = smoke_dock.SmokeDock(self.session, self.cards, extra_shot=lambda name: self.taken.append(("shot", name)), qgis_version="4.2.3")
        self.addCleanup(self._destroy, self.dock)

    @staticmethod
    def _destroy(widget):
        """close() alone leaves the C++ widget alive until interpreter exit, and the CI job's shutdown crash is sensitive to what Qt objects exist then
        (see tests/_ci_run_live_tests.py): delete it now and let Qt run the deferred delete."""
        from qgis.PyQt.QtCore import QCoreApplication, QEvent
        widget.close()
        widget.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def test_start_then_pass_takes_evidence_and_writes_the_line_and_moves_on(self):
        self.assertIn("Do a thing.", self.dock.view.toPlainText())
        self.dock.buttons["PASS"].click()
        self.assertIn("press 'Start this row' first", self.dock.status.text())
        self.assertEqual(self.sc.load_results(self.tmp.name), {})
        self.dock.start_button.click()
        self.dock.note.setText("saw it")
        self.dock.buttons["PASS"].click()
        self.assertEqual(self.taken, [("X1", "saw it")])
        self.assertEqual(self.sc.load_results(self.tmp.name)["X1"]["status"], "PASS")
        self.assertEqual(self.dock.combo.currentText(), "X2")
        self.assertIn("NOT FOR THIS AGENT", self.dock.view.toPlainText())

    def test_skip_works_without_start_and_a_wrong_version_is_flagged(self):
        self.dock.combo.setCurrentIndex(1)
        self.dock.note.setText("human row")
        self.dock.buttons["SKIP"].click()
        self.assertEqual(self.sc.load_results(self.tmp.name)["X2"]["status"], "SKIP")
        self.assertNotIn("WARNING", self.dock.version.text())
        other = self.smoke_dock.SmokeDock(self.session, self.cards, qgis_version="4.2.2")
        self.addCleanup(self._destroy, other)
        self.assertIn("WARNING", other.version.text())

    def test_extra_screenshot_needs_a_started_row_and_a_name(self):
        self.dock.shot_button.click()
        self.assertEqual(self.taken, [])
        self.dock.start_button.click()
        self.dock.shot_name.setText("table")
        self.dock.shot_button.click()
        self.assertEqual(self.taken, [("shot", "X1-table")])


if __name__ == "__main__":
    unittest.main()
