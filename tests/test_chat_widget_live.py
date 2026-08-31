# -*- coding: utf-8 -*-
"""Headless functional test of the chat send path against REAL Qt widgets.

Every other check in this repo's test suite proves the wiring exists and the
pure logic behind it is correct: they run with QGIS_AVAILABLE mocked False, so
they never touch a real Qt widget. None of them prove the Qt signal wiring
actually fires when a person clicks a button in the running dock -- that is a
different failure mode, and this module is what checks it.

This closes that gap without a live QGIS session: it boots a real
QgsApplication, instantiates the real CartogenAiDockWidget / ChatTabWidget
classes (not mocks), drives them with QTest.mouseClick on the actual buttons,
and checks the actual panel visibility and actual chat log contents. A fake
agent (_FakeAgent below) stands in only for the network call inside
agent.run() -- everything from the click to that boundary is the real code.

Requires real qgis.core + qgis.PyQt bindings, unlike the rest of this suite.
Skips itself entirely when those bindings are not importable -- that is
expected and correct in a plain dev environment (this file's own module-level
try/except is the guard, mirrored in @unittest.skipUnless below so a bare
`python -m unittest` run reports it as skipped rather than erroring). Run it
from an OSGeo4W/QGIS Python (see docs/RELEASE_SMOKE_TEST.md) to actually
exercise it: `python -m unittest tests.test_chat_widget_live -v`.

Found and fixed by this test, before it existed to catch it: _dispatch_message
had a `if analysis is None: analysis = self._pending_analysis` fallback left
over from an earlier revision of the send path. Every call site now passes
its own analysis explicitly -- including _send_preview_original(), which
passes None ON PURPOSE to mean "skip the register's enrichment entirely" (the
escape hatch for when the matched task is simply wrong). The fallback
silently overrode that: clicking "Send my wording only" would look like it
worked, then re-apply the very enrichment -- and the very output contract --
the user had just opted out of. No test against the pure logic could have
caught this, because the pure logic was never wrong; only this one call
site's default was. See ui/chat_tab_widget.py's _dispatch_message for the fix.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from qgis.core import QgsApplication
    from qgis.PyQt.QtCore import Qt, QEventLoop, QTimer
    from qgis.PyQt.QtTest import QTest
    QGIS_LIVE_AVAILABLE = True
except ImportError:
    QGIS_LIVE_AVAILABLE = False

_APP = None


def _boot_qgis():
    global _APP
    if _APP is None:
        _APP = QgsApplication([b"livetest"], False)
        QgsApplication.setPrefixPath("/usr", True)
        _APP.initQgis()
    return _APP


def _pump(ms=4000, until=None):
    """Runs the real Qt event loop so QgsTask's background-thread finish
    signal actually gets delivered to the main thread, the same way it would
    in a running QGIS process. Returns as soon as `until()` is true, or after
    the timeout -- whichever first, so a hang shows up as a failed assertion
    rather than the test itself hanging forever."""
    loop = QEventLoop()
    elapsed = [0]
    step = 25

    def tick():
        elapsed[0] += step
        if (until and until()) or elapsed[0] >= ms:
            loop.quit()

    timer = QTimer()
    timer.timeout.connect(tick)
    timer.start(step)
    loop.exec()
    timer.stop()
    if until is not None:
        assert until(), "condition never became true within %dms" % ms


class _FakeClient:
    """Stands in for the network call inside agent.run(). Scripted per test:
    a list of response dicts, consumed in order; a call past the end of the
    script is itself a signal the code looped further than expected."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = 0

    def complete(self, messages, tools=None, max_tokens=None, **kw):
        self.calls += 1
        if not self.script:
            return {"message": {"role": "assistant", "content": "(no more script)"}}
        return self.script.pop(0)


class _FakeAgent:
    """Minimal stand-in for agent.py's real Agent, matching the exact shape
    task_runner.AgentQgsTask calls: run(user_text, map_context, should_stop,
    tool_step_callback) -> str. Real TOOL_REGISTRY tool names are reported
    through tool_step_callback so agent/output_router.satisfied() sees real
    names, the same as the live agent does via agent.py's tool-call loop."""

    def __init__(self, script):
        self.client = _FakeClient(script)
        self.conversation_history = []
        self.executed_tools = []

    def run(self, user_text, map_context=None, should_stop=None, tool_step_callback=None):
        self.conversation_history.append({"role": "user", "content": user_text})
        result = self.client.complete([{"role": "user", "content": user_text}])
        msg = result.get("message", {})
        for tool_name in msg.get("tool_calls", []):
            self.executed_tools.append(tool_name)
            if tool_step_callback:
                tool_step_callback(tool_name, "done", None)
        text = msg.get("content") or ""
        self.conversation_history.append({"role": "assistant", "content": text})
        return text

    def get_session_usage_text(self):
        return None


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "needs real qgis.core/qgis.PyQt bindings -- run from an OSGeo4W/QGIS Python")
class TestChatWidgetLive(unittest.TestCase):
    """Each test gets its own dock -- QDockWidget construction is cheap and
    this keeps one test's state (e.g. an open panel) from leaking into the
    next, the same isolation unittest.TestCase.setUp would give per method."""

    @classmethod
    def setUpClass(cls):
        _boot_qgis()
        from cartogen_ai.core.ui.dock_widget import CartogenAiDockWidget
        cls.DockCls = CartogenAiDockWidget

    def _make_dock(self, agent):
        """Qt's isVisible() reflects ancestor visibility, not just a widget's
        own setVisible() flag -- an un-shown top-level dock leaves every
        child reporting isVisible()==False even after the real code calls
        setVisible(True) on it. A real QGIS session always shows the dock, so
        .show() here is what makes this test's checks match what a user
        actually sees, not a workaround for the plugin."""
        dock = self.DockCls(agent_provider=lambda: agent)
        dock.show()
        self.addCleanup(dock.close)
        return dock

    @staticmethod
    def _chat_text(ct):
        return ct.chat_browser.toPlainText()

    # --------------------------------------------------------- Scenario 1 --

    def test_requirement_panel_blocks_and_gates_continue(self):
        agent = _FakeAgent(script=[])
        dock = self._make_dock(agent)
        ct = dock.chat_tab_widget

        # hazard_type has no safe default (SLOT_DEFAULTS) -- guessing which
        # hazard produces confidently wrong humanitarian output, so this must
        # stop rather than send.
        ct.input_edit.setPlainText("map population affected by a hazard")
        self.assertFalse(ct.requirement_panel.isVisible())
        QTest.mouseClick(ct.send_btn, Qt.MouseButton.LeftButton)

        self.assertTrue(ct.requirement_panel.isVisible(),
                        "hazard_type is unresolvable -- should have stopped")
        self.assertFalse(ct.requirement_continue_btn.isEnabled(),
                         "Continue must stay disabled while something is unresolvable")
        self.assertEqual(agent.client.calls, 0, "must not have sent anything to the model yet")

    # --------------------------------------------------------- Scenario 2 --

    def test_preview_panel_shows_real_prompt_and_send_dispatches_it(self):
        agent = _FakeAgent(script=[
            {"message": {"role": "assistant", "content": "Loaded 3 facility layers.",
                         "tool_calls": ["add_layer_from_path", "apply_categorized_style"]}},
        ])
        dock = self._make_dock(agent)
        ct = dock.chat_tab_widget

        ct.input_edit.setPlainText("map health facilities")
        QTest.mouseClick(ct.send_btn, Qt.MouseButton.LeftButton)

        self.assertTrue(ct.preview_panel.isVisible(),
                        "a matched task with preview enabled (the default) must show the preview")
        shown = ct.preview_prompt.toPlainText()
        self.assertIn("map health facilities", shown,
                      "the preview must show the real composed prompt, not a placeholder")
        self.assertEqual(agent.client.calls, 0, "must not have sent anything while the preview is up")

        QTest.mouseClick(ct.preview_send_btn, Qt.MouseButton.LeftButton)
        _pump(until=lambda: agent.client.calls >= 1)

        self.assertFalse(ct.preview_panel.isVisible())
        self.assertEqual(agent.client.calls, 1, "clicking Send this must be what actually dispatches the call")
        log = self._chat_text(ct)
        self.assertIn("map health facilities", log, "the user's own message must land in the chat log")
        self.assertIn("Loaded 3 facility layers", log, "the agent's real response must land in the chat log")

    def test_preview_panel_locks_input_box_against_edits(self):
        """Regression test for the P0 bug fixed 2026-08-31: nothing previously
        stopped a user from editing the input box while the preview panel was
        open, and Send this / Send my wording only both acted on a stale text
        snapshot regardless -- an edit made here was silently discarded with
        no warning. input_edit.setReadOnly(True) while the panel is open is
        the fix; this drives a REAL keystroke (QTest.keyClicks), not a
        programmatic setPlainText, to prove the box is genuinely locked for a
        user, not just that the code happens to use the snapshot."""
        agent = _FakeAgent(script=[
            {"message": {"role": "assistant", "content": "Loaded 3 facility layers.", "tool_calls": []}},
        ])
        dock = self._make_dock(agent)
        ct = dock.chat_tab_widget

        ct.input_edit.setPlainText("map health facilities")
        QTest.mouseClick(ct.send_btn, Qt.MouseButton.LeftButton)
        self.assertTrue(ct.preview_panel.isVisible())
        self.assertTrue(ct.input_edit.isReadOnly(), "input box must be locked while the preview is open")

        before = ct.input_edit.toPlainText()
        QTest.keyClicks(ct.input_edit, " EDITED")
        self.assertEqual(ct.input_edit.toPlainText(), before,
                          "a real keystroke must not change the box while it's read-only")

        QTest.mouseClick(ct.preview_send_btn, Qt.MouseButton.LeftButton)
        _pump(until=lambda: agent.client.calls >= 1)

        self.assertFalse(ct.input_edit.isReadOnly(), "must unlock again once the panel closes")
        log = self._chat_text(ct)
        self.assertIn("map health facilities", log)
        self.assertNotIn("EDITED", log, "the stale-edit text must never reach the sent message")

    def test_send_my_wording_only_skips_enrichment_and_its_contract(self):
        """Regression test for the bug this file's docstring describes:
        _dispatch_message(text, None) must actually mean no contract, not
        fall back to the pending enriched analysis."""
        agent = _FakeAgent(script=[
            {"message": {"role": "assistant", "content": "OK.", "tool_calls": []}},
        ])
        dock = self._make_dock(agent)
        ct = dock.chat_tab_widget

        ct.input_edit.setPlainText("map health facilities")
        QTest.mouseClick(ct.send_btn, Qt.MouseButton.LeftButton)
        self.assertTrue(ct.preview_panel.isVisible())

        QTest.mouseClick(ct.preview_original_btn, Qt.MouseButton.LeftButton)
        _pump(500)

        self.assertEqual(agent.client.calls, 1,
                         "'Send my wording only' must dispatch exactly once, with no contract "
                         "follow-up -- the whole point of the button is to opt OUT of the "
                         "register's enrichment, contract included")
        self.assertFalse(ct.preview_panel.isVisible())

    # --------------------------------------------------------- Scenario 3 --

    def test_output_contract_followup_fires_exactly_once(self):
        """Turn 1: the model answers in prose for a dashboard-contract
        request, never calling generate_html_dashboard. The real
        _enforce_output_contract() must notice and send exactly one
        follow-up. Turn 2 (the follow-up): the model still doesn't call the
        renderer -- the real code must NOT send a third turn, and must say
        so in the chat rather than silently giving up or looping."""
        agent = _FakeAgent(script=[
            {"message": {"role": "assistant", "content": "Here is a summary of displacement by district.",
                         "tool_calls": ["fetch_geoboundaries"]}},
            {"message": {"role": "assistant", "content": "Understood, still just a summary.",
                         "tool_calls": []}},
        ])
        dock = self._make_dock(agent)
        ct = dock.chat_tab_widget

        ct.input_edit.setPlainText("build me a dashboard of displacement by district")
        QTest.mouseClick(ct.send_btn, Qt.MouseButton.LeftButton)
        self.assertTrue(ct.preview_panel.isVisible())
        QTest.mouseClick(ct.preview_send_btn, Qt.MouseButton.LeftButton)

        _pump(until=lambda: agent.client.calls >= 2)  # first turn + the one follow-up
        _pump(500)  # let the follow-up's on_complete/chat emit finish landing

        self.assertEqual(agent.client.calls, 2,
                         "expected exactly one follow-up call (2 total), got %d -- either the "
                         "contract check never fired, or it looped" % agent.client.calls)
        log = self._chat_text(ct)
        self.assertIn("generate_html_dashboard", log,
                      "the follow-up instruction must name the missing renderer")
        self.assertTrue("did not run" in log or "Asking for it now" in log,
                        "the chat must disclose that the renderer had not run, not just silently retry")

    def test_output_contract_satisfied_on_first_turn_needs_no_followup(self):
        agent = _FakeAgent(script=[
            {"message": {"role": "assistant", "content": "Dashboard ready.",
                         "tool_calls": ["fetch_geoboundaries", "generate_html_dashboard"]}},
        ])
        dock = self._make_dock(agent)
        ct = dock.chat_tab_widget

        ct.input_edit.setPlainText("build me a dashboard of displacement by district")
        QTest.mouseClick(ct.send_btn, Qt.MouseButton.LeftButton)
        QTest.mouseClick(ct.preview_send_btn, Qt.MouseButton.LeftButton)
        _pump(until=lambda: agent.client.calls >= 1)
        _pump(500)

        self.assertEqual(agent.client.calls, 1,
                         "the renderer ran on turn 1 -- no follow-up should ever be sent")


if __name__ == "__main__":
    unittest.main()
