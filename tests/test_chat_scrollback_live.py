"""Live-QGIS tests for the bounded chat scrollback (ChatViewPresenter.trim_scrollback). Written without a local QGIS: CI's first run is their
first execution, so a failure here may be the test's assumption about Qt's document structure rather than the code."""
import unittest

try:
    from qgis.PyQt.QtGui import QTextCursor
    LIVE = True
except ImportError:
    LIVE = False


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestScrollbackTrim(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests.test_chat_widget_live import _boot_qgis
        _boot_qgis()
        from cartogen_ai.core.ui.dock_widget import CartogenAiDockWidget
        cls.DockCls = CartogenAiDockWidget

    def setUp(self):
        from cartogen_ai.core.agent.chat_persistence import clear_saved_chat_history
        from tests.test_chat_widget_live import _FakeAgent
        clear_saved_chat_history()
        self.agent = _FakeAgent(script=[])
        self.dock = self.DockCls(agent_provider=lambda: self.agent)
        self.dock.show()
        self.addCleanup(self.dock.close)
        self.ct = self.dock.chat_tab_widget

    def _fill(self, n):
        for i in range(n):
            self.ct.chat_browser.append(f'<table width="100%"><tr><td>message number {i}</td></tr></table>')

    def test_below_the_threshold_nothing_is_removed(self):
        self._fill(20)
        before = self.ct.chat_browser.toPlainText()
        self.assertEqual(self.ct.presenter.trim_scrollback(trim_above=100, keep=50), 0)
        self.assertEqual(self.ct.chat_browser.toPlainText(), before)

    def test_the_oldest_items_go_in_whole_and_the_newest_stay(self):
        self._fill(60)
        removed = self.ct.presenter.trim_scrollback(trim_above=40, keep=30)
        self.assertGreater(removed, 0)
        text = self.ct.chat_browser.toPlainText()
        self.assertIn("message number 59", text)
        self.assertNotIn("message number 0\n", text + "\n")
        self.assertLessEqual(len(self.ct.chat_browser.document().rootFrame().childFrames()), 40)
        for i in range(31, 60):                                     # the newest items are untouched and complete
            self.assertIn(f"message number {i}", text)

    def test_a_tracked_plan_card_still_points_at_its_text_after_a_trim(self):
        self._fill(30)
        self.agent.task_manager.create_plan("A plan", ["Step one"])
        self.ct._on_live_plan_updated(self.agent.task_manager.get_plan())
        self._fill(30)
        block = self.ct._plan_block
        self.assertIsNotNone(block)
        self.ct.presenter.trim_scrollback(trim_above=40, keep=35)
        self.assertIsNotNone(self.ct._plan_block)
        cursor = QTextCursor(self.ct.chat_browser.document())
        cursor.setPosition(self.ct._plan_block["start"])
        cursor.setPosition(self.ct._plan_block["end"], QTextCursor.MoveMode.KeepAnchor)
        self.assertIn("Step one", cursor.selection().toPlainText())

    def test_a_plan_card_that_was_trimmed_away_is_forgotten(self):
        self.agent.task_manager.create_plan("Old plan", ["Alpha"])
        self.ct._on_live_plan_updated(self.agent.task_manager.get_plan())
        self._fill(80)
        self.ct.presenter.trim_scrollback(trim_above=40, keep=20)
        self.assertIsNone(self.ct._plan_block)
        self.assertNotIn("Alpha", self.ct.chat_browser.toPlainText())


if __name__ == "__main__":
    unittest.main()
