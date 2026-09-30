# -*- coding: utf-8 -*-
"""The full chat transcript in a real QgsProject (F25 option B, owner decision 2026-09-30).

What offline tests cannot show: that QgsProject.writeEntry/readEntry hold the transcript, that it is saved
in and read back from a real .qgz, that it does NOT appear among the project variables (on QGIS 4 the
older custom-property helper writes there, and that list is shown to users), and that the on/off setting
and the default behave. Needs real qgis.core (skipped otherwise). Written without a QGIS install; its first
execution is CI."""
import os
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from qgis.core import QgsProject, QgsSettings
    QGIS_LIVE_AVAILABLE = True
except ImportError:
    QGIS_LIVE_AVAILABLE = False


def _boot_qgis():
    from tests.test_chat_widget_live import _boot_qgis as _shared_boot
    return _shared_boot()


def _turn(n):
    return [{"role": "user", "content": f"question {n}"}, {"role": "assistant", "content": f"answer {n}"}]


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "requires real QGIS")
class TestChatTranscriptInARealProject(unittest.TestCase):
    def setUp(self):
        _boot_qgis()
        from cartogen_ai.core.agent import chat_persistence as cp
        self.cp = cp
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        QgsSettings().remove(cp.PERSIST_SETTING_KEY)                  # the default must apply
        self.addCleanup(lambda: QgsSettings().remove(cp.PERSIST_SETTING_KEY))

    def test_the_default_is_on(self):
        self.assertTrue(self.cp.is_persist_enabled())

    def test_a_turn_is_stored_and_only_new_messages_are_appended_later(self):
        history = _turn(1)
        self.assertTrue(self.cp.save_chat_transcript(history, user_ts="2026-09-30T10:00:00"))
        history = history + _turn(2)
        self.assertTrue(self.cp.save_chat_transcript(history))
        stored = self.cp.load_chat_transcript()
        self.assertEqual([m["content"] for m in stored], ["question 1", "answer 1", "question 2", "answer 2"])
        self.assertEqual(stored[0]["ts"], "2026-09-30T10:00:00")

    def test_the_transcript_outlives_the_agents_ten_message_window(self):
        full = []
        for n in range(1, 13):                      # 24 messages, far more than the 10-message window
            full += _turn(n)
            self.cp.save_chat_transcript(full[-10:])   # what the agent would hold at that point
        stored = self.cp.load_chat_transcript()
        self.assertEqual(len(stored), 24)
        self.assertEqual(stored[0]["content"], "question 1")
        self.assertEqual(stored[-1]["content"], "answer 12")

    def test_it_survives_saving_and_reopening_the_project_file(self):
        self.cp.save_chat_transcript(_turn(1) + _turn(2))
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "p.qgz")
            self.assertTrue(QgsProject.instance().write(path))
            QgsProject.instance().clear()
            self.assertEqual(self.cp.load_chat_transcript(), [])
            self.assertTrue(QgsProject.instance().read(path))
            stored = self.cp.load_chat_transcript()
        self.assertEqual([m["content"] for m in stored],
                         ["question 1", "answer 1", "question 2", "answer 2"])

    def test_it_is_not_one_of_the_project_variables(self):
        self.cp.save_chat_transcript(_turn(1))
        self.assertNotIn(self.cp.TRANSCRIPT_KEY, QgsProject.instance().customVariables())
        self.assertFalse(any("question 1" in str(v) for v in QgsProject.instance().customVariables().values()))

    def test_turned_off_it_stores_nothing_new_but_keeps_what_is_there(self):
        self.cp.save_chat_transcript(_turn(1))
        QgsSettings().setValue(self.cp.PERSIST_SETTING_KEY, False)
        self.assertFalse(self.cp.is_persist_enabled())
        self.assertFalse(self.cp.save_chat_transcript(_turn(1) + _turn(2)))
        self.assertEqual(len(self.cp.load_chat_transcript()), 2)

    def test_clear_saved_chat_history_removes_the_transcript(self):
        self.cp.save_chat_transcript(_turn(1) + _turn(2))
        result = self.cp.clear_saved_chat_history()
        self.assertTrue(result["success"])
        self.assertEqual(result["removed"], 4)
        self.assertEqual(self.cp.load_chat_transcript(), [])

    def test_the_bounds_drop_oldest_first_and_the_export_reports_how_many(self):
        self.cp.save_chat_transcript(_turn(1))
        from unittest.mock import patch
        with patch.object(self.cp, "MAX_TRANSCRIPT_MESSAGES", 4):
            self.cp.save_chat_transcript(_turn(1) + _turn(2) + _turn(3))
        stored = self.cp.load_chat_transcript()
        self.assertEqual([m["content"] for m in stored], ["question 2", "answer 2", "question 3", "answer 3"])
        self.assertEqual(self.cp.describe_retention(10)["transcript_dropped"], 2)


if __name__ == "__main__":
    unittest.main()
