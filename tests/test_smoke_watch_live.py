"""Live check of the evidence watcher (tools/smoke_watch.py) on real QGIS/Qt, in the CI live job: a new line in RESULTS_GUI.csv makes the watcher take the evidence for that row
exactly once, a screenshot that left no file is taken from inside QGIS and reported truthfully, and CARDS_FILLED.md carries the real folder. The evidence collector and the screen capture
are replaced by fakes here. Written without a QGIS install: CI's first run is its first execution."""
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
class TestSmokeWatch(unittest.TestCase):
    def setUp(self):
        from tests.test_chat_widget_live import _boot_qgis
        _boot_qgis()
        import smoke_cards as sc
        import smoke_watch
        self.sc, self.watch = sc, smoke_watch
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.snapped, self.pictures = [], []

    def _watcher(self):
        return self.watch.Watcher(self.tmp.name, lambda row, note: self.snapped.append((row, note)),
                                  capture=lambda path, done=None: self.pictures.append(path))

    def test_a_new_result_line_gets_its_evidence_once_and_existing_lines_are_left_alone(self):
        self.sc.append_result(self.tmp.name, {"row": "OLD", "status": "PASS", "note": "from an earlier session"})
        watcher = self._watcher()
        self.assertEqual(watcher.poll(), [])
        self.sc.append_result(self.tmp.name, {"row": "A1", "status": "PARTIAL", "note": "no page images"})
        self.assertEqual(watcher.poll(), ["A1"])
        self.assertEqual(self.snapped, [("A1", "no page images")])
        self.assertTrue(self.pictures[0].endswith(os.path.join("screens", "A1.png")))
        self.assertEqual(watcher.poll(), [])                                            # not again
        self.assertEqual(len(self.snapped), 1)

    def test_the_watcher_writes_a_heartbeat_so_a_running_timer_is_visible_in_the_log(self):
        watcher = self._watcher()
        for _ in range(self.watch.HEARTBEAT_POLLS):
            watcher.poll()
        self.assertIn("watcher alive", (Path(self.tmp.name) / "watcher.log").read_text(encoding="utf-8"))

    def test_a_line_written_under_a_short_id_gets_its_evidence_under_the_full_card_id(self):
        watcher = self.watch.Watcher(self.tmp.name, lambda row, note: self.snapped.append((row, note)), capture=lambda path, done=None: self.pictures.append(path),
                                     card_ids=["C6-identify-at-point", "C10-raster-inspection"])
        self.sc.append_result(self.tmp.name, {"row": "C6", "status": "PASS", "note": "ok"})
        self.assertEqual(watcher.poll(), ["C6-identify-at-point"])
        self.assertEqual(self.snapped[0][0], "C6-identify-at-point")
        self.assertTrue(self.pictures[0].endswith(os.path.join("screens", "C6-identify-at-point.png")))

    def test_a_failing_snapshot_is_logged_and_never_escapes(self):
        def boom(row, note):
            raise RuntimeError("layer table failed")
        watcher = self.watch.Watcher(self.tmp.name, boom, capture=lambda path, done=None: None)
        self.sc.append_result(self.tmp.name, {"row": "B1", "status": "PASS", "note": "x"})
        self.assertEqual(watcher.poll(), ["B1"])                                        # no exception
        self.assertIn("taking the evidence for B1", (Path(self.tmp.name) / "watcher.log").read_text(encoding="utf-8"))
        self.assertIn("RuntimeError", (Path(self.tmp.name) / "watcher_errors.txt").read_text(encoding="utf-8"))

    def test_a_screenshot_that_left_no_file_is_taken_from_inside_qgis_and_the_watcher_is_told_the_truth(self):
        told = []
        path = os.path.join(self.tmp.name, "screens", "X1-shot.png")

        def fake_grab(target):
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "wb") as fh:
                fh.write(b"png")
            return True
        started = self.watch.capture_with_fallback(path, start=lambda _p: True, grab=fake_grab, schedule=lambda _ms, fn: fn(), done=lambda ok, how: told.append((ok, how)))
        self.assertTrue(started)
        self.assertTrue(os.path.isfile(path))
        self.assertEqual(told[0][0], True)
        self.assertIn("QGIS window picture", told[0][1])
        told.clear()
        called = []
        self.watch.capture_with_fallback(path, start=lambda _p: True, grab=lambda _p: called.append(1) or True, schedule=lambda _ms, fn: fn(), done=lambda ok, how: told.append((ok, how)))
        self.assertEqual(called, [])                                                    # the screen capture wrote the file, so no fallback
        self.assertEqual(told[0], (True, "screen capture"))
        told.clear()
        os.remove(path)
        self.watch.capture_with_fallback(path, start=lambda _p: True, grab=lambda _p: (_ for _ in ()).throw(RuntimeError("x")), schedule=lambda _ms, fn: fn(), done=lambda ok, how: told.append((ok, how)))
        self.assertFalse(told[0][0])                                                    # reported, not raised


if __name__ == "__main__":
    unittest.main()
