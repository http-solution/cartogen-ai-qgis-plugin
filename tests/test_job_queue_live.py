# -*- coding: utf-8 -*-
"""Live-QGIS test of the job queue through the real dock: five pasted requests are proposed, confirmed, then run one at a time.
Written without hand-testing; the Docker QGIS run is the only execution evidence."""
import unittest

try:
    from qgis.PyQt.QtCore import Qt
    from qgis.PyQt.QtTest import QTest
    QGIS_LIVE_AVAILABLE = True
except ImportError:
    QGIS_LIVE_AVAILABLE = False


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "requires real QGIS")
class TestJobQueueLive(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests.test_chat_widget_live import _boot_qgis
        _boot_qgis()
        from cartogen_ai.core.ui.dock_widget import CartogenAiDockWidget
        cls.DockCls = CartogenAiDockWidget

    def setUp(self):
        from cartogen_ai.core.agent.chat_persistence import clear_saved_chat_history
        clear_saved_chat_history()

    def _dock(self, agent):
        dock = self.DockCls(agent_provider=lambda: agent)
        dock.show()
        self.addCleanup(dock.close)
        return dock.chat_tab_widget

    @staticmethod
    def _send(ct, text):
        ct.input_edit.setPlainText(text)
        QTest.mouseClick(ct.send_btn, Qt.MouseButton.LeftButton)

    def test_five_requests_are_proposed_then_run_one_at_a_time(self):
        from tests.fixtures.humanitarian_scenarios import SCEN
        from tests.test_chat_widget_live import _FakeAgent, _pump
        agent = _FakeAgent(script=[{"message": {"content": f"result {i}", "tool_calls": []}} for i in range(5)])
        ct = self._dock(agent)
        self._send(ct, "\n\n".join(SCEN.values()))
        self.assertTrue(ct._awaiting_job_queue_reply)
        self.assertEqual(len(ct._job_queue), 5)
        self.assertEqual(agent.client.calls, 0, "nothing was sent to the model yet")
        self.assertIn("5 separate requests", ct.chat_browser.toPlainText())

        self._send(ct, "run")
        _pump(15000, until=lambda: not ct._job_queue_running and ct._job_queue is None)
        sent = [m["content"] for m in agent.conversation_history if m["role"] == "user"]
        self.assertEqual(len(sent), 5, sent)
        self.assertTrue(sent[0].startswith("I need an urgent health access"))
        self.assertIn("All jobs finished", ct.chat_browser.toPlainText())

    def test_first_runs_only_the_first_job_and_cancel_runs_nothing(self):
        from tests.fixtures.humanitarian_scenarios import SCEN
        from tests.test_chat_widget_live import _FakeAgent, _pump
        agent = _FakeAgent(script=[{"message": {"content": "ok", "tool_calls": []}}])
        ct = self._dock(agent)
        self._send(ct, "\n\n".join(SCEN.values()))
        self._send(ct, "first")
        _pump(8000, until=lambda: ct._job_queue is None)
        self.assertEqual(len([m for m in agent.conversation_history if m["role"] == "user"]), 1)

        agent2 = _FakeAgent(script=[])
        ct2 = self._dock(agent2)
        self._send(ct2, "\n\n".join(SCEN.values()))
        self._send(ct2, "cancel")
        self.assertIsNone(ct2._job_queue)
        self.assertEqual(agent2.conversation_history, [])

    def test_a_single_request_is_never_held_back(self):
        from tests.fixtures.humanitarian_scenarios import SCEN
        from tests.test_chat_widget_live import _FakeAgent, _pump
        agent = _FakeAgent(script=[{"message": {"content": "ok", "tool_calls": []}}])
        ct = self._dock(agent)
        self._send(ct, SCEN["aden"])
        self.assertFalse(ct._awaiting_job_queue_reply)
        _pump(8000, until=lambda: bool(agent.conversation_history))
        self.assertTrue(agent.conversation_history)


if __name__ == "__main__":
    unittest.main()
