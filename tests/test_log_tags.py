"""PLAN-021 WP-C: every message lands in the ONE Log Messages tab, CartogenAI (no QGIS needed for the pure part)."""
import re
import unittest
from pathlib import Path

from cartogen_ai.core.logger import TAG, log_destination

SRC = Path(__file__).resolve().parents[1] / "src" / "cartogen_ai"


class TestOneLogTab(unittest.TestCase):
    def test_every_tag_goes_to_the_one_tab_and_a_component_leads_the_text(self):
        for tag in ("Agent", "Tools", "Providers", "CredentialManager", "ChatTabWidget", "UI", "layout_tools"):
            tab, text = log_destination(tag, "model_call call_index=0")
            self.assertEqual(tab, "CartogenAI")
            self.assertEqual(text, f"[{tag}] model_call call_index=0")

    def test_the_default_tag_adds_nothing_and_the_look_alike_spelling_is_folded_in(self):
        self.assertEqual(log_destination(TAG, "hello"), ("CartogenAI", "hello"))
        self.assertEqual(log_destination("CartogenAi", "hello"), ("CartogenAI", "hello"))      # the look-alike second tab of the 1.18.0 hand run

    def test_nothing_but_the_logger_talks_to_the_qgis_message_log(self):
        offenders = [str(p.relative_to(SRC)) for p in SRC.rglob("*.py")
                     if p.name != "logger.py" and re.search(r"QgsMessageLog\.logMessage\(", p.read_text(encoding="utf-8"))]
        self.assertEqual(offenders, [])

    def test_the_calls_that_reach_qgis_all_use_the_one_tab(self):
        """The same path as inside QGIS, with the message log replaced by a recorder."""
        from types import SimpleNamespace
        from unittest.mock import MagicMock, patch
        from cartogen_ai.core import logger
        recorder = MagicMock()
        levels = SimpleNamespace(Info="info", Warning="warning", Critical="critical")
        with patch.object(logger, "QGIS_LOG_AVAILABLE", True), patch.object(logger, "QgsMessageLog", recorder, create=True), \
                patch.object(logger, "Qgis", SimpleNamespace(MessageLevel=levels), create=True):
            logger.log_info("a", tag="Agent")
            logger.log_warning("b", tag="Providers")
            logger.log_error("c", tag="CartogenAi")
            logger.log_event("model_call", tag="Tools", call_index=0)
        tabs = {call.args[1] for call in recorder.logMessage.call_args_list}
        self.assertEqual(tabs, {"CartogenAI"})
        texts = [call.args[0] for call in recorder.logMessage.call_args_list]
        self.assertEqual(texts[0], "[Agent] a")
        self.assertEqual(texts[2], "c")
        self.assertTrue(texts[3].startswith("[Tools] model_call"))

    def test_the_usage_summary_still_reads_a_prefixed_line(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("summarize_usage_log", SRC.parents[1] / "tools" / "summarize_usage_log.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        line = "2026-10-25T10:00:00 [Agent] model_call call_index=0 model=m input_tokens=10 output_tokens=2 tool_count=3"
        self.assertEqual(module.parse([line])[0]["input_tokens"], 10)


if __name__ == "__main__":
    unittest.main()
