"""DEF-9: the evidence collector could not rely on QGIS's messageReceived signal to see the plugin's log lines (a live QGIS 4.2.2 run delivered nothing through any
form that carries the text). The plugin's own logger now keeps the most recent lines in memory, redacted exactly like the lines it sends to QGIS, and the
collector reads them at snap() time."""
import sys
import time
import unittest
from pathlib import Path

from cartogen_ai.core import logger

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import collect_evidence as ce  # noqa: E402


class TestRecentLines(unittest.TestCase):
    def setUp(self):
        logger._RECENT.clear()

    def test_each_level_is_remembered_with_tag_and_text(self):
        logger.log_info("an info line", tag="Agent")
        logger.log_warning("a warning line", tag="Tools")
        logger.log_error("an error line")
        got = [(level, tag, message) for _t, level, tag, message in logger.recent_lines()]
        self.assertEqual(got, [("INFO", "Agent", "an info line"), ("WARNING", "Tools", "a warning line"), ("CRITICAL", "CartogenAI", "an error line")])

    def test_a_secret_is_redacted_in_the_remembered_line_too(self):
        logger.log_info("calling with api_key=sk-or-v1-abcdefghijklmnop1234 now")
        text = logger.recent_lines()[-1][3]
        self.assertNotIn("abcdefghijklmnop1234", text)
        self.assertIn("***REDACTED***", text)

    def test_only_the_latest_lines_are_kept(self):
        for n in range(logger._RECENT.maxlen + 50):
            logger.log_info(f"line {n}")
        lines = logger.recent_lines()
        self.assertEqual(len(lines), logger._RECENT.maxlen)
        self.assertEqual(lines[-1][3], f"line {logger._RECENT.maxlen + 49}")

    def test_since_keeps_only_newer_lines(self):
        logger.log_info("before")
        cut = time.time() + 0.001
        time.sleep(0.01)
        logger.log_info("after")
        self.assertEqual([m for _t, _l, _g, m in logger.recent_lines(since=cut)], ["after"])

    def test_recording_never_breaks_logging(self):
        saved = logger._RECENT
        try:
            logger._RECENT = None                      # a broken buffer must not stop the line going to QGIS or stderr
            logger.log_info("still works")
        finally:
            logger._RECENT = saved


class TestCollectorReadsThePluginLines(unittest.TestCase):
    def setUp(self):
        logger._RECENT.clear()

    def test_the_collector_returns_the_plugin_lines_since_setup(self):
        logger.log_info("old line")
        since = time.time() + 0.001
        time.sleep(0.01)
        logger.log_info("model_call outcome=ok", tag="Agent")
        text = ce._plugin_lines(since)
        self.assertEqual(len(text), 1)
        self.assertIn("[Agent] INFO model_call outcome=ok", text[0])

    def test_with_no_lines_the_log_file_says_so_instead_of_staying_empty(self):
        self.assertIn("no log line", ce._log_file_text([], connected_forms=0).lower())
        self.assertIn("2 signal", ce._log_file_text([], connected_forms=2))


if __name__ == "__main__":
    unittest.main()
