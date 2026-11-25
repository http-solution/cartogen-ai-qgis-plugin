"""Live check of the smoke card dock (tools/smoke_dock.py) on real QGIS/Qt: the buttons drive the session, a result click takes the evidence through the snapshot callback and writes the line, a result
before Start is refused, Skip works on a row never started, and a wrong QGIS version shows the warning. The real evidence collector (window.grab) needs a desktop and is not exercised here. Written without
a QGIS install: CI's first run is its first execution."""
import os
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

    def test_an_error_in_the_handler_never_escapes_and_the_verdict_is_kept(self):
        self.dock.start_button.click()
        self.dock._goto_unfinished = lambda start: (_ for _ in ()).throw(TypeError("<lambda>() missing 1 required positional argument: 'n'"))      # the error the owner saw
        self.dock.note.setText("kept")
        self.dock.buttons["PARTIAL"].click()                                # must not raise
        r = self.sc.load_results(self.tmp.name)["X1"]
        self.assertEqual((r["status"], r["note"]), ("PARTIAL", "kept"))
        self.assertIn("recorded", self.dock.status.text())
        self.assertIn("TypeError", (Path(self.tmp.name) / "dock_errors.txt").read_text(encoding="utf-8"))
        self.assertIsNone(self.session.current)

    def test_all_four_result_buttons_record_their_own_status(self):
        for status in ("PASS", "PARTIAL", "FAIL"):
            self.dock.combo.setCurrentIndex(0)
            self.session.current = None
            self.session.start("X1")
            self.dock.buttons[status].click()
            self.assertEqual(self.sc.load_results(self.tmp.name)["X1"]["status"], status)

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


    def test_a_screenshot_that_left_no_file_is_taken_from_inside_qgis_and_the_dock_is_told_the_truth(self):
        """2026-11-24: the PowerShell capture started (so it counted as done) but wrote nothing, and the dock still said 'saved'. Written without a QGIS install; CI's first run is its first execution."""
        smoke_dock = self.smoke_dock
        told = []
        path = os.path.join(self.tmp.name, "screens", "X1-shot.png")

        def fake_grab(target):
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "wb") as fh:
                fh.write(b"png")
            return True
        started = smoke_dock.capture_with_fallback(path, start=lambda _p: True, grab=fake_grab, schedule=lambda _ms, fn: fn(), done=lambda ok, how: told.append((ok, how)))
        self.assertTrue(started)
        self.assertTrue(os.path.isfile(path))
        self.assertEqual(told[0][0], True)
        self.assertIn("QGIS window picture", told[0][1])
        # when the screen capture did write the file, no fallback runs
        told.clear()
        called = []
        smoke_dock.capture_with_fallback(path, start=lambda _p: True, grab=lambda _p: called.append(1) or True, schedule=lambda _ms, fn: fn(), done=lambda ok, how: told.append((ok, how)))
        self.assertEqual(called, [])
        self.assertEqual(told[0], (True, "screen capture"))
        # and a failure is reported, not raised
        told.clear()
        os.remove(path)
        smoke_dock.capture_with_fallback(path, start=lambda _p: True, grab=lambda _p: (_ for _ in ()).throw(RuntimeError("x")), schedule=lambda _ms, fn: fn(), done=lambda ok, how: told.append((ok, how)))
        self.assertFalse(told[0][0])


if __name__ == "__main__":
    unittest.main()
