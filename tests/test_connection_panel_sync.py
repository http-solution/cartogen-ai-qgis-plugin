"""Hand run 2026-11-04 (rows A2/A3): after 'Use this connection' + OK in the Connections window opened from Settings, the panel's dropdown still showed the old
connection. Offline guard on the wiring (the live behaviour is tests/test_connections_window_live.py, CI only): Settings announces a saved connection and the
dock refreshes its dropdown on that announcement, not only when Settings itself is accepted."""
import re
import unittest
from pathlib import Path

UI = Path(__file__).resolve().parents[1] / "src" / "cartogen_ai" / "core" / "ui"


class TestPanelFollowsAConnectionSavedFromSettings(unittest.TestCase):
    def test_settings_declares_and_emits_the_signal_only_after_an_accepted_connections_window(self):
        text = (UI / "settings_dialog.py").read_text(encoding="utf-8")
        self.assertIn("connection_saved = pyqtSignal()", text)
        body = text.split("def _open_connections(self):", 1)[1].split("\n    def ", 1)[0]
        self.assertRegex(body, r"if dialog\.exec\(\):[\s\S]*self\.connection_saved\.emit\(\)")
        self.assertEqual(body.count("connection_saved.emit"), 1)

    def test_the_dock_connects_the_signal_to_its_dropdown_refresh_before_showing_settings(self):
        text = (UI / "dock_widget.py").read_text(encoding="utf-8")
        body = text.split("def open_settings(self):", 1)[1].split("\n    def ", 1)[0]
        self.assertTrue(re.search(r"connection_saved\.connect\(self\._refresh_after_connection_change\)[\s\S]*dialog\.exec\(\)", body))


if __name__ == "__main__":
    unittest.main()
