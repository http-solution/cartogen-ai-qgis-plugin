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
silently overrode that: clicking "Send as typed instead" (labeled "Send my
wording only" at the time this bug was found -- see the UI/chat redesign
workstream, 2026-09-12, for the rename) would look like it
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
    from qgis.PyQt.QtCore import Qt, QEventLoop, QTimer, QUrl
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
    """Minimal stand-in for agent_orchestrator.py's real Agent, matching the exact shape
    task_runner.AgentQgsTask calls: run(user_text, map_context, should_stop,
    tool_step_callback) -> str. Real TOOL_REGISTRY tool names are reported
    through tool_step_callback so agent/output_router.satisfied() sees real
    names, the same as the live agent does via agent_orchestrator.py's tool-call loop."""

    def __init__(self, script):
        self.client = _FakeClient(script)
        self.conversation_history = []
        self.executed_tools = []
        # Real AgentTaskManager (not a mock) -- the confirmation-gate tests below need
        # real PREVIEW_READY/add_task behavior, not a MagicMock that would silently
        # accept any attribute access without exercising the real logic under test.
        from cartogen_ai.core.agent.task_manager import AgentTaskManager
        from cartogen_ai.core.agent.memory import SpatialMemoryManager
        self.task_manager = AgentTaskManager()
        # tasks_tab_widget.py's sync_with_agent() reads agent.memory_manager right after
        # agent.task_manager once a real task_manager is present (previously that whole
        # branch was unreachable here since _FakeAgent had no task_manager at all) -- a
        # real, empty SpatialMemoryManager satisfies that the same way a real Agent would.
        self.memory_manager = SpatialMemoryManager()
        # Records every _real_execute_tool call this fake agent receives, so a test can
        # assert the confirmation gate called (or did NOT call) it without a real tool.
        self.real_execute_tool_calls = []

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

    def _real_execute_tool(self, name, arguments, user_confirmed=False):
        self.real_execute_tool_calls.append((name, arguments, user_confirmed))
        return {"success": True, "layer_name": arguments.get("layer_name", "")}

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

    def setUp(self):
        # The full transcript is now saved by default and lives in the shared
        # QgsProject.instance(), so an earlier test's turns would otherwise be
        # restored into this test's fresh dock (CI run for PR #107: the welcome
        # message was replaced by "Restored previous conversation").
        from cartogen_ai.core.agent.chat_persistence import clear_saved_chat_history
        clear_saved_chat_history()

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

    @staticmethod
    def _reply(ct, text):
        """Types text into the real input box and presses the real Send button --
        used for both a fresh message and a typed reply to an in-chat question
        (requirement gate or prompt preview), since both are just "type, hit Send"
        from the user's side."""
        ct.input_edit.setPlainText(text)
        QTest.mouseClick(ct.send_btn, Qt.MouseButton.LeftButton)

    # --------------------------------------------------------- Scenario 1 --

    def test_requirement_question_asked_in_chat_not_a_boxed_panel(self):
        """2026-09-13: replaced a separate QGroupBox("One more detail needed")
        panel (with locked input + two buttons) with the question posted as a
        normal chat message, per direct user feedback that the panel read as
        a foreign popup disconnected from the conversation. This confirms the
        question lands in the chat log and the input box stays fully live."""
        agent = _FakeAgent(script=[])
        dock = self._make_dock(agent)
        ct = dock.chat_tab_widget

        # hazard_type has no safe default (SLOT_DEFAULTS) -- guessing which
        # hazard produces confidently wrong humanitarian output, so this must
        # stop rather than send.
        ct.input_edit.setPlainText("map population affected by a hazard")
        self.assertFalse(ct._awaiting_requirement_reply)
        QTest.mouseClick(ct.send_btn, Qt.MouseButton.LeftButton)

        self.assertTrue(ct._awaiting_requirement_reply,
                        "hazard_type is unresolvable -- should be waiting on the user's reply")
        log = self._chat_text(ct)
        self.assertIn("hazard", log.lower(),
                      "the clarifying question must appear as a real chat message, not a hidden panel")
        # Real live report, 2026-09-15: "the first message i sent on the chat was not showing
        # in the chat box" -- the message that TRIGGERED this gate must itself be echoed as
        # its own bubble, before the AI's question, not silently dropped.
        user_pos = log.find("map population affected by a hazard")
        # Search for the AI label starting AFTER the user's own message, not from the top of
        # the log -- the welcome message (_populate_initial_chat) also renders a "Cartogen "
        # label, and now correctly appears in the log itself (see the 2026-09-16 fix for "the
        # welcome message from Cartogen AI is not showing"), so a plain log.find("Cartogen ")
        # would match that instead of the gate's own question bubble this test cares about.
        cartogen_bubble_pos = log.find("Cartogen ", user_pos)
        self.assertNotEqual(user_pos, -1, "the user's own triggering message must appear in the log")
        self.assertNotEqual(cartogen_bubble_pos, -1, "the AI's reply bubble must also be present")
        self.assertLess(user_pos, cartogen_bubble_pos,
            "the user's message must be echoed before the AI's own question bubble")
        self.assertFalse(ct.input_edit.isReadOnly(),
                         "the input box must stay live -- answering is just typing a normal reply")
        self.assertEqual(agent.client.calls, 0, "must not have sent anything to the model yet")

    def test_a_still_unresolved_requirement_is_asked_at_most_twice(self):
        """rc10 smoke test: the same clarification came back three times and each repeated reply grew the request. One
        follow-up round is allowed (a slot the first reply left open); after that the request goes on to the preview."""
        agent = _FakeAgent(script=[{"message": {"role": "assistant", "content": "ok"}}])
        dock = self._make_dock(agent)
        ct = dock.chat_tab_widget
        self._reply(ct, "map population affected by a hazard")
        self.assertTrue(ct._awaiting_requirement_reply)                      # round 1
        self._reply(ct, "something that names no hazard at all")
        self.assertTrue(ct._awaiting_requirement_reply)                      # round 2: still unresolved, one follow-up
        self._reply(ct, "still nothing about a hazard")
        self.assertFalse(ct._awaiting_requirement_reply, "a third question must not be asked")
        self.assertTrue(ct._awaiting_preview_reply, "it proceeds to the normal preview with the default stated")

    def test_requirement_reply_merges_into_original_request(self):
        """The user's plain-typed reply ("flood") to the in-chat question above
        must be treated as answering it, not as an unrelated new message --
        merged into the original request text so the previously-missing
        hazard_type slot now resolves (task_matcher's regex evidence check
        matches "flood" literally) and the turn can proceed."""
        # tool_calls includes export_to_csv -- the merged request's own output contract
        # (task 3.15, "analysis" kind) needs one of field_statistics/export_to_csv to be
        # satisfied on the first turn, or output_router fires a real second followup call
        # (see test_output_contract_followup_fires_exactly_once) and agent.client.calls
        # would be 2, unrelated to what this test is actually checking.
        agent = _FakeAgent(script=[
            {"message": {"role": "assistant", "content": "Mapped flood-affected population.",
                         "tool_calls": ["fetch_worldpop_population", "export_to_csv"]}},
        ])
        dock = self._make_dock(agent)
        ct = dock.chat_tab_widget

        self._reply(ct, "map population affected by a hazard")
        self.assertTrue(ct._awaiting_requirement_reply)

        self._reply(ct, "flood")

        # Real-session report, 2026-09-13: "some of my text i sent in the chat is not
        # showing" -- the literal reply must be echoed into the chat log immediately,
        # not silently swallowed into the merge.
        self.assertIn("flood", self._chat_text(ct).lower(),
                      "the user's own reply must appear in the chat log as its own message")

        self.assertFalse(ct._awaiting_requirement_reply,
                         "answering the only unresolvable slot should clear the pending state")
        self.assertTrue(ct._awaiting_preview_reply,
                        "a now-resolved, matched task with preview enabled (the default) should "
                        "proceed to the normal preview step, exactly like any fresh, already-"
                        "complete request would")
        shown = self._chat_text(ct)
        self.assertIn("flood", shown.lower(),
                      "the composed prompt must carry the answer forward, not just the original text")

        self._reply(ct, "yes")
        _pump(until=lambda: agent.client.calls >= 1)
        self.assertEqual(agent.client.calls, 1,
                         "the merged, now-answerable request must actually reach the agent")

    def test_multi_round_clarification_shows_every_reply_in_chat(self):
        """Real-session report, 2026-09-13: after the single-reply fix above, a request
        needing TWO unresolvable slots (facility_type AND sector, task 12.09) still lost
        the user's first reply -- _ask_requirement_in_chat's second question replaced it
        with no trace the first answer was ever seen. Both replies must show up as their
        own chat messages, in order, even though neither slot has a safe default and the
        gate genuinely has to ask twice."""
        agent = _FakeAgent(script=[])
        dock = self._make_dock(agent)
        ct = dock.chat_tab_widget

        self._reply(ct, "map services for at-risk children")
        self.assertTrue(ct._awaiting_requirement_reply)
        first_question_log = self._chat_text(ct)
        self.assertIn("facility", first_question_log.lower())

        # Answers facility_type only ("clinics") -- sector is still missing, so this
        # must ask again rather than proceeding.
        self._reply(ct, "clinics")
        self.assertIn("clinics", self._chat_text(ct).lower(),
                      "the first reply must be visible in the chat log")
        self.assertTrue(ct._awaiting_requirement_reply,
                        "sector is still unresolved -- the gate must ask again, not proceed")

        # Answers the second question ("protection") -- now both slots are resolved.
        self._reply(ct, "protection")
        log = self._chat_text(ct)
        self.assertIn("protection", log.lower(),
                      "the second reply must ALSO be visible -- not just the first")
        self.assertIn("clinics", log.lower(),
                      "the first reply must still be visible after the second round")
        self.assertFalse(ct._awaiting_requirement_reply,
                         "both slots are now resolved -- the pending state must clear")
        self.assertEqual(agent.client.calls, 0,
                         "still must not have sent anything to the model yet (this next step "
                         "would be gated by the in-chat preview question, not exercised by this test)")

    # --------------------------------------------------------- Scenario 2 --

    def test_preview_question_shows_real_prompt_and_confirm_reply_dispatches_it(self):
        agent = _FakeAgent(script=[
            {"message": {"role": "assistant", "content": "Loaded 3 facility layers.",
                         "tool_calls": ["add_layer_from_path", "apply_categorized_style"]}},
        ])
        dock = self._make_dock(agent)
        ct = dock.chat_tab_widget

        self._reply(ct, "map health facilities")

        self.assertTrue(ct._awaiting_preview_reply,
                        "a matched task with preview enabled (the default) must ask in chat")
        shown = self._chat_text(ct)
        self.assertIn("map health facilities", shown,
                      "the chat message must show the real composed prompt, not a placeholder")
        self.assertEqual(agent.client.calls, 0, "must not have sent anything while awaiting the reply")

        self._reply(ct, "yes")
        _pump(until=lambda: agent.client.calls >= 1)

        self.assertFalse(ct._awaiting_preview_reply)
        self.assertEqual(agent.client.calls, 1, "a confirming reply must be what actually dispatches the call")
        log = self._chat_text(ct)
        self.assertIn("map health facilities", log, "the user's own message must land in the chat log")
        self.assertIn("Loaded 3 facility layers", log, "the agent's real response must land in the chat log")

    def test_original_message_is_echoed_as_its_own_bubble_before_the_preview_question(self):
        """Real live report, 2026-09-15: "the first message i sent on the chat was not
        showing in the chat box" -- confirmed live (separate repro): the triggering message
        was never shown as a distinct "You" bubble at all before this fix, only ever quoted
        back secondhand inside the AI's own "Message sent as you: ..." text. Checks the
        precise ordering (echoed BEFORE the AI's question, not just present somewhere in the
        log eventually) and that confirming doesn't show the exact same text a second time,
        verbatim, as if the user had retyped it."""
        agent = _FakeAgent(script=[
            {"message": {"role": "assistant", "content": "Loaded 3 facility layers.", "tool_calls": []}},
        ])
        dock = self._make_dock(agent)
        ct = dock.chat_tab_widget

        self._reply(ct, "map health facilities")

        log_before_reply = self._chat_text(ct)
        user_pos = log_before_reply.find("map health facilities")
        ai_question_pos = log_before_reply.find("Why this prompt")
        self.assertNotEqual(user_pos, -1, "the user's own message must appear in the log at all")
        self.assertLess(user_pos, ai_question_pos,
            "the user's message must be echoed BEFORE the AI's preview question, not only "
            "quoted back inside it afterward")

        self._reply(ct, "yes")
        _pump(until=lambda: agent.client.calls >= 1)

        log_after = self._chat_text(ct)
        occurrences = log_after.count("map health facilities")
        # Appears: once as the upfront echo, once more inside the composed "Message sent as
        # you: ..." block the AI's own question quotes -- never a THIRD time as if dispatch
        # re-echoed the identical raw text again on confirm.
        self.assertEqual(occurrences, 2,
            f"expected 'map health facilities' exactly twice (upfront echo + the AI's own "
            f"quote of it), found {occurrences} -- confirming must not re-echo the same raw "
            f"text a second time as its own new bubble")

    def test_preview_reply_variants_are_interpreted_correctly(self):
        """The free-text reply resolves a genuine 3-way choice (confirmed with the user as the
        design, 2026-09-15): an affirmative word sends the composed prompt, a cancel word
        abandons it with no dispatch, and anything else is sent exactly as typed (the free-text
        equivalent of the old 'Send as typed instead' button) -- checked here as three separate,
        independent turns."""
        agent = _FakeAgent(script=[
            {"message": {"role": "assistant", "content": "Loaded 3 facility layers.", "tool_calls": []}},
            {"message": {"role": "assistant", "content": "OK.", "tool_calls": []}},
        ])
        dock = self._make_dock(agent)
        ct = dock.chat_tab_widget

        # Cancel: no dispatch, an acknowledgment lands in the chat, state clears.
        self._reply(ct, "map health facilities")
        self.assertTrue(ct._awaiting_preview_reply)
        self._reply(ct, "cancel")
        self.assertFalse(ct._awaiting_preview_reply)
        self.assertEqual(agent.client.calls, 0, "cancelling must not dispatch anything")
        self.assertIn("cancelled", self._chat_text(ct).lower())

        # Edit fallback: an unrecognized reply is sent exactly as typed, no enrichment/contract.
        self._reply(ct, "map health facilities")
        self.assertTrue(ct._awaiting_preview_reply)
        self._reply(ct, "just show me clinics instead")
        _pump(until=lambda: agent.client.calls >= 1)
        self.assertEqual(agent.client.calls, 1,
                         "an unrecognized reply must dispatch exactly once, with no contract "
                         "follow-up -- the whole point is opting OUT of the register's "
                         "enrichment, contract included")
        self.assertIn("just show me clinics instead", self._chat_text(ct).lower())

    # Both boxed-panel-growth-reclamps-a-floating-dock tests that used to live here were
    # deleted, not adapted, 2026-09-16: their entire premise (a QGroupBox that becomes visible
    # and forces the dock's minimum size to grow, needing a proactive re-clamp outside the
    # normal resizeEvent path) no longer applies now that the refinement panel -- the last
    # remaining boxed panel -- was itself converted to an in-chat exchange (see
    # _show_refinement_in_chat in chat_tab_widget.py and the design-proposal comment where
    # the old QGroupBox construction used to be). chat_tab_widget.py's own now-dead
    # _clamp_dock_after_panel_change wrapper was removed with it, for the same reason
    # test_preview_panel_locks_input_box_against_edits was deleted rather than adapted when
    # the preview panel was converted earlier: the premise being tested is gone, not just the
    # widget. dock_widget.py's own _clamp_to_screen_if_floating (the underlying resizeEvent
    # guard, 2026-09-12) is untouched and still runs on every real resize.

    def test_welcome_starter_prompt_click_fills_input_box_not_send(self):
        """Design proposal, 2026-09-16 (Dateline Dock artifact): the welcome message's starter
        prompts are cartogen://starter/{index} links (render_welcome_html); clicking one must
        fill the input box for the user to review/edit, never dispatch a turn on its own."""
        agent = _FakeAgent(script=[])
        dock = self._make_dock(agent)
        ct = dock.chat_tab_widget

        log = self._chat_text(ct)
        self.assertIn("Monitor", log)
        self.assertIn(ct._starter_prompts[0], log)

        ct._on_step_anchor_clicked(QUrl("cartogen://starter/1"))
        self.assertEqual(ct.input_edit.toPlainText(), ct._starter_prompts[1])
        self.assertEqual(agent.client.calls, 0, "clicking a starter must never itself dispatch a turn")

    def test_escape_clears_the_input_box(self):
        """Part B §9 UX verification, 2026-09-20: live-probed with a real QTest.keyClick
        before this fix existed and found Escape did nothing at all -- typed text survived
        unchanged. Deliberately narrow: only clears whatever's currently typed, doesn't
        touch an in-flight request or any pending requirement/preview-reply state (see
        ChatInputEdit.keyPressEvent's own comment for why those are out of scope here)."""
        agent = _FakeAgent(script=[])
        dock = self._make_dock(agent)
        ct = dock.chat_tab_widget

        ct.input_edit.setPlainText("some half-typed text")
        QTest.keyClick(ct.input_edit, Qt.Key.Key_Escape)
        self.assertEqual(ct.input_edit.toPlainText(), "")

    def test_tab_key_advances_focus_past_the_input_box(self):
        """Part B §9 UX verification, 2026-09-20: live-probed before this fix and found Tab
        pressed inside the input box just inserted a literal tab character (QTextEdit's own
        default) -- a genuine keyboard-navigation dead end, since nothing after the input
        (send_btn, stop_btn, everything else in the dock) was reachable by Tab at all.
        setTabChangesFocus(True) is Qt's own built-in switch for this; this test confirms
        it actually takes effect on the real widget, not just that the property was set."""
        agent = _FakeAgent(script=[])
        dock = self._make_dock(agent)
        dock.activateWindow()
        dock.raise_()
        QTest.qWaitForWindowActive(dock)
        ct = dock.chat_tab_widget

        ct.input_edit.setFocus()
        QTest.qWait(20)
        self.assertIs(QgsApplication.focusWidget(), ct.input_edit)
        QTest.keyClick(ct.input_edit, Qt.Key.Key_Tab)
        QTest.qWait(20)
        self.assertIsNot(
            QgsApplication.focusWidget(), ct.input_edit,
            "Tab from the input box must move focus onward, not insert a tab character",
        )

    def test_refinement_recommendation_click_fills_input_box_not_send(self):
        """Design proposal, 2026-09-16 (Dateline Dock artifact), real live report: "the
        recommendation text as button style like the welcome message" -- the refinement
        panel (a boxed QGroupBox) was converted to in-chat cards the same way the requirement
        gate and prompt preview already were. Exercises _show_refinement_in_chat/
        _on_refinement_card_clicked directly (bypassing the network-call scaffolding, same
        precedent the tests this replaces used for the old boxed panel)."""
        agent = _FakeAgent(script=[])
        dock = self._make_dock(agent)
        ct = dock.chat_tab_widget

        recommendations = [
            {"id": "A", "label": "Clearer", "refined_prompt": "Map health facilities in admin2.",
             "rationale": "States the admin level explicitly."},
            {"id": "B", "label": "Detailed", "refined_prompt": "Map and style health facilities by type.",
             "rationale": "Adds styling."},
        ]
        ct._show_refinement_in_chat(recommendations)
        log = self._chat_text(ct)
        self.assertIn("Suggested rewordings", log)
        self.assertIn("Map health facilities in admin2.", log)

        ct._on_step_anchor_clicked(QUrl("cartogen://refine/1"))
        self.assertEqual(ct.input_edit.toPlainText(), "Map and style health facilities by type.")
        self.assertEqual(agent.client.calls, 0, "clicking a recommendation must never itself dispatch a turn")

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

        self._reply(ct, "build me a dashboard of displacement by district")
        self.assertTrue(ct._awaiting_preview_reply)
        self._reply(ct, "yes")

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

        self._reply(ct, "build me a dashboard of displacement by district")
        self._reply(ct, "yes")
        _pump(until=lambda: agent.client.calls >= 1)
        _pump(500)

        self.assertEqual(agent.client.calls, 1,
                         "the renderer ran on turn 1 -- no follow-up should ever be sent")

    def test_cancel_active_task_reaches_a_real_scheduled_task(self):
        """QGIS-002, 2026-09-13 audit: plugin_main.py's unload() used to never reach an
        in-flight AgentQgsTask at all -- a user unloading/reloading the plugin mid-request
        left it running against a dock widget scheduled for deletion, the direct trigger
        for QGIS-001's finished()-callback crash. cancel_active_task() (now called from
        unload()) is the fix; this drives it against a REAL scheduled QgsTask, not a mock,
        confirming it actually reaches the task's own isCanceled() flag."""
        agent = _FakeAgent(script=[
            {"message": {"role": "assistant", "content": "done", "tool_calls": []}},
        ])
        dock = self._make_dock(agent)
        ct = dock.chat_tab_widget

        # Bypasses the requirement/preview gates entirely -- this test is about the
        # scheduled-task/cancel mechanism, not the send pipeline those other tests cover.
        ct._dispatch_message("plain test message", None)

        self.assertIsNotNone(ct._active_task, "a real task must have been scheduled")
        task = ct._active_task
        self.assertFalse(task.isCanceled())

        ct.cancel_active_task()

        self.assertTrue(task.isCanceled(), "cancel_active_task() must reach the real QgsTask")
        _pump(until=lambda: ct._active_task is None)

    def test_cancel_active_task_is_a_safe_no_op_with_nothing_running(self):
        agent = _FakeAgent(script=[])
        dock = self._make_dock(agent)
        ct = dock.chat_tab_widget
        self.assertIsNone(ct._active_task)
        ct.cancel_active_task()  # must not raise

    def test_attach_file_reads_and_analyzes_off_the_main_thread(self):
        """PERF-005, 2026-09-13 audit: read_attached_file (pypdf/docx/pandas parsing) used
        to run synchronously on the Qt main thread inside attach_file(), before the
        background analysis thread was even started. It now runs inside that same
        background thread (_read_and_analyze_file) instead. This drives that method the
        same way attach_file() itself does -- a real background thread, a real file on
        disk -- confirming the whole path (disk read -> attached-paths bookkeeping ->
        agent.run() -> chat log) still works end to end after the move."""
        import threading
        import tempfile

        agent = _FakeAgent(script=[
            {"message": {"role": "assistant", "content": "This looks like a plain text note."}},
        ])
        dock = self._make_dock(agent)
        ct = dock.chat_tab_widget

        fd, path = tempfile.mkstemp(suffix=".txt")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write("hello from a test attachment")

            thread = threading.Thread(
                target=ct._read_and_analyze_file, args=(agent, "note.txt", path), daemon=True
            )
            thread.start()
            _pump(until=lambda: "plain text note" in self._chat_text(ct))

            self.assertIn(path, ct._attached_paths,
                         "successful read must still register the path for the next message")
            self.assertFalse(thread.is_alive())
        finally:
            os.remove(path)

    def _attach_under_gate(self, base_url, mode="enforce", strict=True, reply="Analyzed."):
        """Drives the real attachment path (_read_and_analyze_file on a real background
        thread, a real file on disk) with the cloud-provider egress gate set in real
        QgsSettings. Returns (agent, chat_text, attached_paths, file_path)."""
        import tempfile
        import threading
        from qgis.core import QgsSettings
        from cartogen_ai.infrastructure.settings_keys import (
            SETTINGS_EGRESS_GATE_MODE, SETTINGS_EGRESS_GATE_STRICT,
        )
        settings = QgsSettings()
        settings.setValue(SETTINGS_EGRESS_GATE_MODE, mode)
        settings.setValue(SETTINGS_EGRESS_GATE_STRICT, strict)
        self.addCleanup(settings.remove, SETTINGS_EGRESS_GATE_MODE)
        self.addCleanup(settings.remove, SETTINGS_EGRESS_GATE_STRICT)

        agent = _FakeAgent(script=[{"message": {"role": "assistant", "content": reply}}])
        agent.client.base_url = base_url
        dock = self._make_dock(agent)
        ct = dock.chat_tab_widget
        fd, path = tempfile.mkstemp(suffix=".txt")
        self.addCleanup(os.remove, path)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write("household_id,name" + chr(10) + "1,Example Person")
        thread = threading.Thread(target=ct._read_and_analyze_file,
                                  args=(agent, "households.txt", path), daemon=True)
        thread.start()
        _pump(until=lambda: not thread.is_alive())
        return agent, self._chat_text(ct), list(ct._attached_paths), path

    def test_egress_gate_blocks_an_attachment_on_a_cloud_provider_in_strict_mode(self):
        """Cloud-provider egress gate (docs/OLLAMA_ENFORCEMENT_GATE_SCOPE_2026-09-24.md):
        analyze_file is the one place an attached file's content leaves the machine. In strict
        enforce mode on a cloud endpoint it must never reach the provider, and must not be queued
        for the next message either."""
        agent, chat, attached, path = self._attach_under_gate("https://api.openai.com/v1/chat/completions")
        self.assertEqual(agent.client.calls, 0, "the file's content must not be sent anywhere")
        self.assertIn("Not sent: households.txt", chat)
        self.assertNotIn(path, attached, "a blocked file must not ride along with the next message")

    def test_egress_gate_lets_an_attachment_through_on_a_local_provider(self):
        agent, chat, attached, path = self._attach_under_gate("http://127.0.0.1:11434/v1/chat/completions")
        self.assertEqual(agent.client.calls, 1)
        self.assertIn("Analyzed.", chat)
        self.assertIn(path, attached)

    def test_egress_gate_does_not_touch_attachments_outside_strict_mode(self):
        agent, chat, _, _ = self._attach_under_gate("https://api.openai.com/v1", strict=False)
        self.assertEqual(agent.client.calls, 1)
        self.assertNotIn("Not sent", chat)

    def test_egress_gate_off_by_default_leaves_attachments_unchanged(self):
        agent, chat, _, _ = self._attach_under_gate("https://api.openai.com/v1", mode="off")
        self.assertEqual(agent.client.calls, 1)
        self.assertIn("Analyzed.", chat)

    def test_attachment_disclosure_note_names_the_active_hosted_provider(self):
        """API-007, 2026-09-14 audit: attach_file() must tell the user, at the moment of
        attachment, which provider the file's content is about to be sent to."""
        from qgis.core import QgsSettings
        agent = _FakeAgent(script=[])
        dock = self._make_dock(agent)
        ct = dock.chat_tab_widget

        settings = QgsSettings()
        original = settings.value("cartogen_ai/provider", "openrouter")
        try:
            settings.setValue("cartogen_ai/provider", "gemini")
            note = ct._attachment_disclosure_note()
            self.assertIn("Gemini", note)
            self.assertIn("sent to", note)
        finally:
            settings.setValue("cartogen_ai/provider", original)

    # --------------------------------------------- destructive-action confirm gate --

    def test_chat_typed_confirm_resolves_pending_destructive_action_directly(self):
        """Real live report, 2026-09-16: a user typed "Confirm" in chat to approve a
        field_calculator preview. That reply used to re-enter the normal tool-calling
        LLM turn, with no structured way for the model to know what was pending -- it
        fabricated a "Confirmed" narrative without ever calling field_calculator, so the
        approved edit silently never happened. Now a plain confirm reply must resolve
        directly against pending_tool/pending_args, the exact same deterministic path
        the Activity tab's own Confirm button uses (tasks_tab_widget.py's
        _confirm_selected_task) -- never through client.complete() at all."""
        agent = _FakeAgent(script=[{"message": {"role": "assistant", "content": "should not be reached"}}])
        dock = self._make_dock(agent)
        ct = dock.chat_tab_widget

        agent.task_manager.create_plan("Severity index", ["Calculate severity"])
        task = agent.task_manager.tasks[0]
        agent.task_manager.set_task_preview(task["id"], code_snippet="field_calculator(...)",
                                             rationale="test", is_destructive=True)
        task["pending_tool"] = "field_calculator"
        task["pending_args"] = {"layer_name": "GDACS Disaster Alerts - Yemen",
                                 "new_field": "severity", "expression": "2"}

        self._reply(ct, "Confirm")

        self.assertEqual(agent.real_execute_tool_calls,
                          [("field_calculator", task["pending_args"], True)])
        self.assertEqual(agent.client.calls, 0,
                          "a plain confirm reply must never go through the LLM loop")
        self.assertEqual(agent.task_manager.tasks[0]["status"], "DONE")
        log = self._chat_text(ct)
        self.assertIn("Confirmed & Executed", log)

    def test_chat_typed_cancel_resolves_pending_destructive_action_without_executing(self):
        agent = _FakeAgent(script=[{"message": {"role": "assistant", "content": "should not be reached"}}])
        dock = self._make_dock(agent)
        ct = dock.chat_tab_widget

        agent.task_manager.create_plan("Severity index", ["Calculate severity"])
        task = agent.task_manager.tasks[0]
        agent.task_manager.set_task_preview(task["id"], code_snippet="field_calculator(...)",
                                             rationale="test", is_destructive=True)
        task["pending_tool"] = "field_calculator"
        task["pending_args"] = {"layer_name": "GDACS Disaster Alerts - Yemen"}

        self._reply(ct, "cancel")

        self.assertEqual(agent.real_execute_tool_calls, [],
                          "a cancel reply must never execute the pending tool")
        self.assertEqual(agent.client.calls, 0)
        self.assertEqual(agent.task_manager.tasks[0]["status"], "FAILED")
        log = self._chat_text(ct)
        self.assertIn("Cancelled", log)

    def test_a_casual_yes_does_not_confirm_a_pending_destructive_action(self):
        """rc7 smoke test 2026-09-30 (F16): the router vocabulary ("yes", "ok", "sure") used to
        also resolve a pending destructive gate, so a casual reply to something else could
        confirm load_project / field_calculator / the cloud-data override."""
        agent = _FakeAgent(script=[{"message": {"role": "assistant", "content": "an ordinary reply"}}])
        dock = self._make_dock(agent)
        ct = dock.chat_tab_widget

        agent.task_manager.create_plan("Severity index", ["Calculate severity"])
        task = agent.task_manager.tasks[0]
        agent.task_manager.set_task_preview(task["id"], code_snippet="field_calculator(...)",
                                             rationale="test", is_destructive=True)
        task["pending_tool"] = "field_calculator"
        task["pending_args"] = {"layer_name": "GDACS Disaster Alerts - Yemen"}

        self._reply(ct, "yes")

        self.assertEqual(agent.real_execute_tool_calls, [],
                          "a casual 'yes' must never execute a pending destructive action")
        self.assertEqual(agent.task_manager.tasks[0]["status"], "PREVIEW_READY")

    def test_a_stale_preview_cannot_be_confirmed_by_typing(self):
        agent = _FakeAgent(script=[{"message": {"role": "assistant", "content": "should not be reached"}}])
        dock = self._make_dock(agent)
        ct = dock.chat_tab_widget

        agent.task_manager.create_plan("Severity index", ["Calculate severity"])
        task = agent.task_manager.tasks[0]
        agent.task_manager.set_task_preview(task["id"], code_snippet="field_calculator(...)",
                                             rationale="test", is_destructive=True)
        task["pending_tool"] = "field_calculator"
        task["pending_args"] = {"layer_name": "GDACS Disaster Alerts - Yemen"}
        task["updated_at"] = "2020-01-01T00:00:00+00:00"

        self._reply(ct, "Confirm")

        self.assertEqual(agent.real_execute_tool_calls, [])
        self.assertIn("Activity tab", self._chat_text(ct))

    def test_a_pending_gate_does_not_hijack_an_unrelated_new_message(self):
        """Only an exact confirm/cancel-shaped reply resolves the gate -- anything else
        (a genuinely new request) must fall through to the normal send path, so a stale
        PREVIEW_READY task from an earlier turn can never swallow unrelated messages."""
        agent = _FakeAgent(script=[{"message": {"role": "assistant", "content": "ok, mapped it"}}])
        dock = self._make_dock(agent)
        ct = dock.chat_tab_widget

        agent.task_manager.create_plan("Severity index", ["Calculate severity"])
        task = agent.task_manager.tasks[0]
        agent.task_manager.set_task_preview(task["id"], code_snippet="field_calculator(...)",
                                             rationale="test", is_destructive=True)
        task["pending_tool"] = "field_calculator"
        task["pending_args"] = {"layer_name": "X"}

        self._reply(ct, "map health facilities in Aleppo")

        # Whatever the normal send path does with this new, unrelated message (dispatch,
        # show a prompt preview, ask a requirement question) is out of scope here -- the
        # only thing under test is that the confirmation gate itself was NOT triggered.
        self.assertEqual(agent.real_execute_tool_calls, [])
        self.assertEqual(agent.task_manager.tasks[0]["status"], "PREVIEW_READY",
                          "an unrelated message must not disturb the still-pending gate")

    # ------------------------------------------ inline safety-gate card (Phase 2) --

    def test_safety_gate_card_is_posted_after_a_turn_leaves_a_task_pending(self):
        """Broadsheet redesign Phase 2: once a turn completes and a task is left
        PREVIEW_READY with pending_tool set, the inline card (render_safety_gate_html)
        must appear in the chat log with real, clickable confirm/cancel links -- not just
        the model's own free-text description of the gate."""
        agent = _FakeAgent(script=[
            {"message": {"role": "assistant", "content": "I've staged the severity field for review."}},
        ])
        dock = self._make_dock(agent)
        ct = dock.chat_tab_widget

        agent.task_manager.create_plan("Severity index", ["Calculate severity"])
        task = agent.task_manager.tasks[0]
        agent.task_manager.set_task_preview(task["id"], code_snippet="field_calculator(...)",
                                             rationale="Adds a numeric severity field.",
                                             is_destructive=True)
        task["pending_tool"] = "field_calculator"
        task["pending_args"] = {"layer_name": "GDACS Disaster Alerts - Yemen", "new_field": "severity"}

        ct._dispatch_message("calculate severity", None)
        _pump(until=lambda: agent.client.calls >= 1)
        _pump(500)

        log = self._chat_text(ct)
        self.assertIn("CONFIRMATION REQUIRED", log)
        self.assertIn("GDACS Disaster Alerts - Yemen", log)
        html = ct.chat_browser.toHtml()
        self.assertIn(f'cartogen://confirm/{task["id"]}', html)
        self.assertIn(f'cartogen://cancel/{task["id"]}', html)

    def test_safety_gate_card_confirm_link_click_resolves_directly(self):
        agent = _FakeAgent(script=[])
        dock = self._make_dock(agent)
        ct = dock.chat_tab_widget

        agent.task_manager.create_plan("Severity index", ["Calculate severity"])
        task = agent.task_manager.tasks[0]
        agent.task_manager.set_task_preview(task["id"], code_snippet="field_calculator(...)",
                                             rationale="test", is_destructive=True)
        task["pending_tool"] = "field_calculator"
        task["pending_args"] = {"layer_name": "X", "new_field": "severity"}
        ct._show_safety_gate_in_chat(agent)

        ct._on_step_anchor_clicked(QUrl(f'cartogen://confirm/{task["id"]}'))

        self.assertEqual(agent.real_execute_tool_calls,
                          [("field_calculator", task["pending_args"], True)])
        self.assertEqual(agent.client.calls, 0,
                          "clicking the card's link must never go through the LLM loop")
        self.assertEqual(agent.task_manager.tasks[0]["status"], "DONE")
        self.assertIn("Confirmed & Executed", self._chat_text(ct))

    def test_safety_gate_card_cancel_link_click_does_not_execute(self):
        agent = _FakeAgent(script=[])
        dock = self._make_dock(agent)
        ct = dock.chat_tab_widget

        agent.task_manager.create_plan("Severity index", ["Calculate severity"])
        task = agent.task_manager.tasks[0]
        agent.task_manager.set_task_preview(task["id"], code_snippet="field_calculator(...)",
                                             rationale="test", is_destructive=True)
        task["pending_tool"] = "field_calculator"
        task["pending_args"] = {"layer_name": "X"}
        ct._show_safety_gate_in_chat(agent)

        ct._on_step_anchor_clicked(QUrl(f'cartogen://cancel/{task["id"]}'))

        self.assertEqual(agent.real_execute_tool_calls, [])
        self.assertEqual(agent.task_manager.tasks[0]["status"], "FAILED")
        self.assertIn("Cancelled", self._chat_text(ct))

    def test_safety_gate_card_not_reposted_while_the_same_task_is_still_pending(self):
        agent = _FakeAgent(script=[])
        dock = self._make_dock(agent)
        ct = dock.chat_tab_widget

        agent.task_manager.create_plan("Severity index", ["Calculate severity"])
        task = agent.task_manager.tasks[0]
        agent.task_manager.set_task_preview(task["id"], code_snippet="field_calculator(...)",
                                             rationale="test", is_destructive=True)
        task["pending_tool"] = "field_calculator"
        task["pending_args"] = {"layer_name": "X"}

        ct._show_safety_gate_in_chat(agent)
        ct._show_safety_gate_in_chat(agent)

        html = ct.chat_browser.toHtml()
        self.assertEqual(html.count(f'cartogen://confirm/{task["id"]}'), 1,
                          "the same still-pending task's card must only be posted once")

    def test_attachment_disclosure_note_is_accurate_for_local_ollama(self):
        from qgis.core import QgsSettings
        agent = _FakeAgent(script=[])
        dock = self._make_dock(agent)
        ct = dock.chat_tab_widget

        settings = QgsSettings()
        original = settings.value("cartogen_ai/provider", "openrouter")
        try:
            settings.setValue("cartogen_ai/provider", "ollama")
            note = ct._attachment_disclosure_note()
            self.assertIn("local", note.lower())
            self.assertNotIn("will be sent to", note)
        finally:
            settings.setValue("cartogen_ai/provider", original)

    # ------------------------------------------ single-scroll dock (Phase 1) --

    def test_no_tabs_the_dock_hosts_one_continuous_scroll(self):
        """Broadsheet redesign Phase 1 (mockup 1k): the old Chat/Activity QTabWidget
        split is gone -- ChatTabWidget is the dock's only content. Task/plan progress
        (2026-09-17 second pass) no longer lives in a separate docked widget at all --
        it's a block inside ChatTabWidget's own chat_browser, so there's no sibling
        widget left to assert the presence of here."""
        agent = _FakeAgent(script=[])
        dock = self._make_dock(agent)
        self.assertFalse(hasattr(dock, "tab_widget"))
        self.assertFalse(hasattr(dock, "tasks_tab_widget"))
        self.assertFalse(hasattr(dock.chat_tab_widget, "plan_strip"))

    def test_plan_card_flags_a_pending_confirmation_in_chat(self):
        agent = _FakeAgent(script=[])
        dock = self._make_dock(agent)
        ct = dock.chat_tab_widget

        agent.task_manager.create_plan("Severity index", ["Calculate severity"])
        task = agent.task_manager.tasks[0]
        agent.task_manager.set_task_preview(task["id"], code_snippet="field_calculator(...)",
                                             rationale="test", is_destructive=True)
        task["pending_tool"] = "field_calculator"
        task["pending_args"] = {"layer_name": "X"}
        ct._on_live_plan_updated(agent.task_manager.get_plan())

        self.assertIn("needs you", ct.chat_browser.toHtml())

    def test_plan_card_absent_when_no_plan_is_active(self):
        agent = _FakeAgent(script=[])
        dock = self._make_dock(agent)
        ct = dock.chat_tab_widget
        ct._on_live_plan_updated(agent.task_manager.get_plan())
        self.assertIsNone(ct._plan_block)

    def test_plan_card_renders_once_a_plan_exists(self):
        agent = _FakeAgent(script=[])
        dock = self._make_dock(agent)
        ct = dock.chat_tab_widget
        agent.task_manager.create_plan("A plan", ["Step one"])
        ct._on_live_plan_updated(agent.task_manager.get_plan())
        self.assertIsNotNone(ct._plan_block)
        self.assertIn("Step one", ct.chat_browser.toPlainText())

    def test_plan_card_updates_in_place_not_appended_again(self):
        """A second plan_updated for the SAME plan title must edit the existing card's
        tracked span, not append a second copy -- otherwise every tool-call tick during a
        long-running plan would spam the chat log with duplicate cards."""
        agent = _FakeAgent(script=[])
        dock = self._make_dock(agent)
        ct = dock.chat_tab_widget
        agent.task_manager.create_plan("A plan", ["Step one", "Step two"])
        ct._on_live_plan_updated(agent.task_manager.get_plan())
        first_block = ct._plan_block
        agent.task_manager.tasks[0]["status"] = "DONE"
        ct._on_live_plan_updated(agent.task_manager.get_plan())
        self.assertIs(ct._plan_block, first_block)
        self.assertEqual(ct.chat_browser.toPlainText().count("Step one"), 1)

    def test_new_plan_title_appends_a_fresh_card_leaving_the_old_one_in_scrollback(self):
        agent = _FakeAgent(script=[])
        dock = self._make_dock(agent)
        ct = dock.chat_tab_widget
        agent.task_manager.create_plan("First plan", ["Alpha"])
        ct._on_live_plan_updated(agent.task_manager.get_plan())
        agent.task_manager.clear_plan()
        agent.task_manager.create_plan("Second plan", ["Beta"])
        ct._on_live_plan_updated(agent.task_manager.get_plan())
        text = ct.chat_browser.toPlainText()
        self.assertIn("Alpha", text)
        self.assertIn("Beta", text)

    def test_scrolling_up_is_not_undone_by_later_layout_changes(self):
        """rc11 smoke test: the chat felt stuck at the last message. A user who scrolled up must stay where they are when
        the document grows; a user at the bottom keeps following new content."""
        from qgis.PyQt.QtCore import QAbstractSlider
        from qgis.PyQt.QtWidgets import QApplication
        agent = _FakeAgent(script=[])
        dock = self._make_dock(agent)
        ct = dock.chat_tab_widget
        for i in range(40):
            ct.chat_browser.append("line %d<br><br><br>" % i)
        QApplication.processEvents()
        sb = ct.chat_browser.verticalScrollBar()
        self.assertGreater(sb.maximum(), 0)
        ct._scroll_to_bottom()
        QApplication.processEvents()
        self.assertEqual(sb.value(), sb.maximum())
        # a user scroll up: the position moves, then the slider reports the action
        sb.setValue(0)
        sb.actionTriggered.emit(QAbstractSlider.SliderAction.SliderToMinimum)
        QApplication.processEvents()
        for i in range(20):
            ct.chat_browser.append("more %d<br><br><br>" % i)
        QApplication.processEvents()
        self.assertEqual(sb.value(), 0, "document growth pulled a scrolled-up user back to the bottom")
        # a new message always brings the view back to the end
        ct._scroll_to_bottom()
        QApplication.processEvents()
        self.assertEqual(sb.value(), sb.maximum())

    def test_task_inspector_dialog_confirm_resolves_via_the_shared_method(self):
        """task_inspector_dialog.py must route through the SAME
        _resolve_pending_confirmation the chat-typed reply and the safety-gate card's
        links already use -- not a fourth, separately-duplicated confirm implementation."""
        from cartogen_ai.core.ui.task_inspector_dialog import CartogenAiTaskInspectorDialog

        agent = _FakeAgent(script=[])
        dock = self._make_dock(agent)
        agent.task_manager.create_plan("Severity index", ["Calculate severity"])
        task = agent.task_manager.tasks[0]
        agent.task_manager.set_task_preview(task["id"], code_snippet="field_calculator(...)",
                                             rationale="test", is_destructive=True)
        task["pending_tool"] = "field_calculator"
        task["pending_args"] = {"layer_name": "X"}

        dialog = CartogenAiTaskInspectorDialog(dock, task)
        self.assertTrue(dialog.confirm_btn.isEnabled())
        dialog._confirm()

        self.assertEqual(agent.real_execute_tool_calls, [("field_calculator", {"layer_name": "X"}, True)])
        self.assertEqual(agent.task_manager.tasks[0]["status"], "DONE")

    def test_task_inspector_dialog_read_only_disables_all_actions(self):
        from cartogen_ai.core.ui.task_inspector_dialog import CartogenAiTaskInspectorDialog

        agent = _FakeAgent(script=[])
        dock = self._make_dock(agent)
        task = {"id": "1", "status": "PREVIEW_READY", "pending_tool": "field_calculator",
                "pending_args": {}, "rationale": "", "code_snippet": ""}

        dialog = CartogenAiTaskInspectorDialog(dock, task, read_only=True)
        self.assertFalse(dialog.confirm_btn.isEnabled())
        self.assertFalse(dialog.cancel_task_btn.isEnabled())
        self.assertFalse(dialog.edit_task_btn.isEnabled())

    def test_memory_dialog_populates_from_the_live_agent(self):
        from cartogen_ai.core.ui.memory_dialog import CartogenAiMemoryDialog

        agent = _FakeAgent(script=[])
        dock = self._make_dock(agent)
        agent.memory_manager.store_project_note("preferred_crs", "EPSG:32638")

        dialog = CartogenAiMemoryDialog(dock)
        self.addCleanup(dialog.close)

        self.assertIn("EPSG:32638", dialog.memory_browser.toPlainText())

    def test_memory_dialog_clear_saved_chat_deletes_the_stored_transcript(self):
        """F25 option B: a default-on store needs a way out. The button asks first, then deletes the
        project's saved conversation (full transcript + window), and declining deletes nothing."""
        from unittest.mock import patch
        from qgis.core import QgsProject
        from qgis.PyQt.QtWidgets import QMessageBox
        from cartogen_ai.core.agent import chat_persistence as cp
        from cartogen_ai.core.ui.memory_dialog import CartogenAiMemoryDialog

        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        dock = self._make_dock(_FakeAgent(script=[]))
        cp.save_chat_transcript([{"role": "user", "content": "q"}, {"role": "assistant", "content": "a"}])
        self.assertEqual(len(cp.load_chat_transcript()), 2)

        dialog = CartogenAiMemoryDialog(dock)
        self.addCleanup(dialog.close)
        self.assertTrue(hasattr(dialog, "clear_saved_chat_btn"))

        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.No), \
                patch.object(QMessageBox, "information"):
            dialog._clear_saved_chat_clicked()
        self.assertEqual(len(cp.load_chat_transcript()), 2, "declining must delete nothing")

        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes), \
                patch.object(QMessageBox, "information"):
            dialog._clear_saved_chat_clicked()
        self.assertEqual(cp.load_chat_transcript(), [])

    def test_memory_button_opens_a_dialog(self):
        """The header's Memory button (dock_widget.py's open_memory) must exist and use
        the "notes" icon -- confirms icons.py's new template renders without raising."""
        agent = _FakeAgent(script=[])
        dock = self._make_dock(agent)
        self.assertTrue(hasattr(dock, "memory_btn"))
        self.assertFalse(dock.memory_btn.icon().isNull())

    # ------------------------------------------ layer context picker (Phase 3) --

    def test_layer_context_picker_defaults_sensitive_layers_unchecked(self):
        from cartogen_ai.core.ui.layer_context_picker_dialog import LayerContextPickerDialog

        layers = [
            {"name": "Health Facilities", "type": "VectorLayer", "feature_count": 8},
            {"name": "Beneficiary Registry", "type": "VectorLayer", "feature_count": 40},
        ]
        sensitivity = {"Beneficiary Registry": "SENSITIVE"}
        dialog = LayerContextPickerDialog(
            layers, selection={}, sensitivity_lookup=lambda name: sensitivity.get(name))
        self.addCleanup(dialog.close)

        self.assertTrue(dialog._checkboxes["Health Facilities"].isChecked())
        self.assertFalse(dialog._checkboxes["Beneficiary Registry"].isChecked())

    def test_layer_context_picker_a_prior_choice_wins_over_the_sensitivity_default(self):
        from cartogen_ai.core.ui.layer_context_picker_dialog import LayerContextPickerDialog

        layers = [{"name": "Beneficiary Registry", "type": "VectorLayer", "feature_count": 40}]
        # A layer with a real sensitivity level would default unchecked -- but the user
        # already explicitly re-checked it once before, and reopening the dialog must
        # not silently forget that.
        dialog = LayerContextPickerDialog(
            layers, selection={"Beneficiary Registry": True},
            sensitivity_lookup=lambda name: "SENSITIVE")
        self.addCleanup(dialog.close)

        self.assertTrue(dialog._checkboxes["Beneficiary Registry"].isChecked())

    def test_layer_context_picker_result_selection_reflects_unchecking(self):
        from cartogen_ai.core.ui.layer_context_picker_dialog import LayerContextPickerDialog

        layers = [{"name": "Health Facilities", "type": "VectorLayer", "feature_count": 8}]
        dialog = LayerContextPickerDialog(layers, selection={}, sensitivity_lookup=lambda name: None)
        self.addCleanup(dialog.close)
        dialog._checkboxes["Health Facilities"].setChecked(False)

        self.assertEqual(dialog.result_selection(), {"Health Facilities": False})

    def test_dispatch_message_filters_map_context_by_the_saved_selection(self):
        """End-to-end: a layer unchecked via the picker must actually be absent from
        the map_context run_agent_task receives -- not just filtered in isolation."""
        from unittest.mock import patch

        agent = _FakeAgent(script=[{"message": {"role": "assistant", "content": "ok"}}])
        dock = self._make_dock(agent)
        ct = dock.chat_tab_widget
        ct._layer_context_selection = {"Beneficiary Registry": False}

        fake_ctx = {
            "project_title": "P", "layer_count": 2,
            "layers": [{"name": "Health Facilities"}, {"name": "Beneficiary Registry"}],
        }
        captured = {}
        real_run_agent_task = None
        from cartogen_ai.core.services import task_runner as task_runner_mod
        real_run_agent_task = task_runner_mod.run_agent_task

        def _spy_run_agent_task(**kwargs):
            captured["map_context"] = kwargs.get("map_context")
            return real_run_agent_task(**kwargs)

        with patch("cartogen_ai.core.agent.map_context.get_map_context_summary", return_value=fake_ctx), \
             patch.object(task_runner_mod, "run_agent_task", side_effect=_spy_run_agent_task):
            ct._dispatch_message("plain test message", None)

        names = [layer["name"] for layer in captured["map_context"]["layers"]]
        self.assertEqual(names, ["Health Facilities"])


def _user_bubbles(log, text):
    """How many times `text` appears as the user's own bubble ("You · <time>" line, then the
    text) -- not counting the preview card quoting it under "Message sent as you:"."""
    lines = log.splitlines()
    return sum(1 for i in range(1, len(lines))
               if lines[i].strip() == text and lines[i - 1].startswith("You ·"))


_TRAVEL_Q = "Health facilities beyond one hour's travel 3999682,3756232"


def _geofabrik_fixture(folder):
    """Tiny shapefiles in the Geofabrik 'free' schema (column names checked against the real
    Jordan extract, 2026-09-25): 4 roads (2 drivable, a footway and a flight of steps that must be left out), 3 point POIs (a hospital, a clinic and a pharmacy that
    must be left out) and 1 hospital mapped as a building outline."""
    from qgis.core import (QgsFeature, QgsField, QgsFields, QgsGeometry, QgsProject,
                           QgsCoordinateReferenceSystem, QgsVectorFileWriter, QgsWkbTypes)
    from qgis.PyQt.QtCore import QMetaType
    crs = QgsCoordinateReferenceSystem("EPSG:4326")

    def write(stem, wkb, cols, rows):
        fields = QgsFields()
        for c in cols:
            fields.append(QgsField(c, QMetaType.Type.QString))
        opts = QgsVectorFileWriter.SaveVectorOptions()
        opts.driverName = "ESRI Shapefile"
        path = os.path.join(folder, stem + ".shp")
        w = QgsVectorFileWriter.create(path, fields, wkb, crs, QgsProject.instance().transformContext(), opts)
        for wkt, attrs in rows:
            f = QgsFeature(fields)
            f.setGeometry(QgsGeometry.fromWkt(wkt))
            f.setAttributes(attrs)
            w.addFeature(f)
        del w
        return path

    return {
        "gis_osm_roads_free_1": write("gis_osm_roads_free_1", QgsWkbTypes.Type.LineString,
                                      ["osm_id", "fclass", "oneway", "maxspeed"],
                                      [("LINESTRING(35.90 31.95, 35.92 31.96)", ["1", "primary", "B", "60"]),
                                       ("LINESTRING(35.92 31.96, 35.94 31.97)", ["2", "residential", "F", "0"]),
                                       # not drivable: must be left out of the routing network
                                       ("LINESTRING(35.93 31.96, 35.931 31.961)", ["3", "footway", "B", "0"]),
                                       ("LINESTRING(35.94 31.97, 35.941 31.971)", ["4", "steps", "B", "0"])]),
        "gis_osm_pois_free_1": write("gis_osm_pois_free_1", QgsWkbTypes.Type.Point,
                                     ["osm_id", "fclass", "name"],
                                     [("POINT(35.91 31.95)", ["10", "hospital", "Point Hospital"]),
                                      ("POINT(35.93 31.96)", ["11", "clinic", "Clinic"]),
                                      ("POINT(35.93 31.97)", ["12", "pharmacy", "Pharmacy"])]),
        "gis_osm_pois_a_free_1": write("gis_osm_pois_a_free_1", QgsWkbTypes.Type.Polygon,
                                       ["osm_id", "fclass", "name"],
                                       [("POLYGON((35.95 31.95, 35.96 31.95, 35.96 31.96, 35.95 31.96, 35.95 31.95))",
                                         ["20", "hospital", "Outline Hospital"])]),
    }


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "needs real qgis.core/qgis.PyQt bindings -- run from an OSGeo4W/QGIS Python")
class TestLocalDataOfferLive(unittest.TestCase):
    """The local-data download/online decision (agent/local_data_sources.py,
    agent/local_data_loader.py), driven through the real dock: real send button, real QgsTask
    for the background probe/download, real layers added to QgsProject. Only Geofabrik itself
    is replaced (by the fixture above and the connectivity/resolve_region patches below).

    Rewritten 2026-09-28 for the silent-smart-default redesign (live-reported: "download /
    online is just used for critical actions not a routine task"): a background probe now
    decides silently whenever the connection is good and the extract is a known, reasonable
    size -- these tests mock `probe_connectivity` explicitly rather than relying on the
    live-QGIS CI runner's own real network access, so `online_ok` is always deterministic.
    Every scenario now needs a resolvable location up front (`_canvas_center` mocked, or -- as
    for `_TRAVEL_Q`, which has no decimal point so `extract_coordinate_pair` doesn't match it --
    falls through to it), since the probe+resolve step runs before any interruption can happen
    at all, unlike the old design where the very first question needed no location yet."""

    @classmethod
    def setUpClass(cls):
        _boot_qgis()
        from cartogen_ai.core.ui.dock_widget import CartogenAiDockWidget
        cls.DockCls = CartogenAiDockWidget

    def setUp(self):
        import shutil
        import tempfile
        from unittest.mock import patch
        from qgis.core import QgsProject
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        self.tmp = tempfile.mkdtemp(prefix="cg_localdata_live_")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        p = patch("cartogen_ai.core.agent.local_data_loader.data_dir", return_value=self.tmp)
        p.start()
        self.addCleanup(p.stop)

    def _dock(self):
        agent = _FakeAgent(script=[])
        dock = self.DockCls(agent_provider=lambda: agent)
        dock.show()
        self.addCleanup(dock.close)
        return dock.chat_tab_widget, agent

    def test_good_connection_and_reasonable_size_downloads_silently_with_no_question(self):
        # The routine case this redesign exists for: no "reply download or online" interruption
        # at all, just an informational note once the download finishes.
        from unittest.mock import patch
        from qgis.core import QgsProject, QgsWkbTypes
        ct, agent = self._dock()
        region = {"id": "jordan", "name": "Jordan", "shp_url": "https://example.invalid/x.zip",
                  "size_bytes": 30_000_000}
        shp = _geofabrik_fixture(self.tmp)
        with patch.object(type(ct), "_canvas_center", return_value=(35.93, 31.95)), \
             patch("cartogen_ai.core.agent.local_data_loader.probe_connectivity", return_value=True), \
             patch("cartogen_ai.core.agent.local_data_loader.resolve_region", return_value=region), \
             patch("cartogen_ai.core.agent.local_data_loader.download_and_extract",
                   return_value={"shapefiles": shp, "zip_path": os.path.join(self.tmp, "x.zip"),
                                 "region": region}):
            TestChatWidgetLive._reply(ct, _TRAVEL_Q)
            _pump(8000, until=lambda: ct._awaiting_preview_reply)

        self.assertFalse(ct._awaiting_local_data_reply, "never interrupted -- downloaded silently")
        roads = QgsProject.instance().mapLayersByName("OSM Roads (Jordan)")
        health = QgsProject.instance().mapLayersByName("Health Facilities (OSM, Jordan)")
        self.assertEqual(len(roads), 1)
        self.assertEqual(roads[0].geometryType(), QgsWkbTypes.GeometryType.LineGeometry)
        self.assertEqual(roads[0].featureCount(), 2)          # the footway and the steps are left out
        self.assertEqual(sorted(f["fclass"] for f in roads[0].getFeatures()), ["primary", "residential"])
        self.assertEqual(len(health), 1)
        names = sorted(f["name"] for f in health[0].getFeatures())
        self.assertEqual(names, ["Clinic", "Outline Hospital", "Point Hospital"],
                         "outline hospitals included as points; pharmacies left out")
        self.assertTrue(health[0].source().split("|")[0].endswith(".gpkg"), "kept as a file, not in memory")
        log = ct.chat_browser.toPlainText()
        self.assertIn("Added to the project from Geofabrik", log)
        self.assertIn("footpaths, steps and cycleways left out", log)
        self.assertEqual(_user_bubbles(log, _TRAVEL_Q), 1)
        self.assertEqual(agent.client.calls, 0, "the preview is waiting; nothing sent yet")

    def test_a_large_extract_asks_with_its_size_as_a_single_round_trip(self):
        from unittest.mock import patch
        ct, _ = self._dock()
        region = {"id": "germany", "name": "Germany", "shp_url": "https://example.invalid/x.zip",
                  "size_bytes": 4_300_000_000}
        with patch.object(type(ct), "_canvas_center", return_value=(10.0, 51.0)), \
             patch("cartogen_ai.core.agent.local_data_loader.probe_connectivity", return_value=True), \
             patch("cartogen_ai.core.agent.local_data_loader.resolve_region", return_value=region), \
             patch("cartogen_ai.core.agent.local_data_loader.download_and_extract") as dl:
            TestChatWidgetLive._reply(ct, _TRAVEL_Q)
            _pump(8000, until=lambda: ct._awaiting_local_data_reply)
            log = ct.chat_browser.toPlainText()
            self.assertIn("4300 MB", log)
            # toPlainText() strips href targets, keeping only the chip's visible label --
            # toHtml() is what actually shows the markdown link survived rendering as a
            # clickable chip rather than literal "cartogen://action/..." text in the bubble.
            self.assertIn("cartogen://action/", ct.chat_browser.toHtml(),
                           "offered as clickable chips, not free text only")
            dl.assert_not_called()
            TestChatWidgetLive._reply(ct, "online")
        self.assertTrue(ct._awaiting_preview_reply)
        dl.assert_not_called()

    def test_poor_connection_asks_even_for_a_small_extract(self):
        # Field/humanitarian context: a slow or offline connection must not be silently
        # guessed either way -- the user gets an explicit choice.
        from unittest.mock import patch
        ct, agent = self._dock()
        region = {"id": "jordan", "name": "Jordan", "shp_url": "https://example.invalid/x.zip",
                  "size_bytes": 30_000_000}
        with patch.object(type(ct), "_canvas_center", return_value=(35.93, 31.95)), \
             patch("cartogen_ai.core.agent.local_data_loader.probe_connectivity", return_value=False), \
             patch("cartogen_ai.core.agent.local_data_loader.resolve_region", return_value=region), \
             patch("cartogen_ai.core.agent.local_data_loader.download_and_extract") as dl:
            TestChatWidgetLive._reply(ct, _TRAVEL_Q)
            _pump(8000, until=lambda: ct._awaiting_local_data_reply)
            log = ct.chat_browser.toPlainText()
            self.assertIn("slow or unavailable", log)
            dl.assert_not_called()
            TestChatWidgetLive._reply(ct, "online")
        self.assertTrue(ct._awaiting_preview_reply)
        self.assertEqual(agent.client.calls, 0, "nothing goes to the model before the user answers")

    def test_online_continues_to_the_preview_and_is_not_asked_again(self):
        from unittest.mock import patch
        ct, agent = self._dock()
        # resolve_region is patched like its siblings: unpatched it does a real region-index lookup, which in CI can
        # outlast the 8 s pump (failed on 2 consecutive runs of PR #110 while passing on others -- network-dependent).
        region = {"id": "jordan", "name": "Jordan", "shp_url": "https://example.invalid/x.zip",
                  "size_bytes": 30_000_000}
        with patch.object(type(ct), "_canvas_center", return_value=(35.93, 31.95)), \
             patch("cartogen_ai.core.agent.local_data_loader.resolve_region", return_value=region), \
             patch("cartogen_ai.core.agent.local_data_loader.probe_connectivity", return_value=False):
            TestChatWidgetLive._reply(ct, _TRAVEL_Q)
            _pump(8000, until=lambda: ct._awaiting_local_data_reply)
            TestChatWidgetLive._reply(ct, "online")
            log = ct.chat_browser.toPlainText()
            self.assertFalse(ct._awaiting_local_data_reply)
            self.assertTrue(ct._awaiting_preview_reply, "the normal preview comes next")
            self.assertEqual(_user_bubbles(log, _TRAVEL_Q), 1, "resuming must not echo the request again")
            TestChatWidgetLive._reply(ct, "cancel")
            TestChatWidgetLive._reply(ct, _TRAVEL_Q)
            self.assertFalse(ct._awaiting_local_data_reply, "declined once -> not asked again this session")
        self.assertEqual(agent.client.calls, 0, "nothing goes to the model before the user answers")

    def test_stop_during_the_download_ends_the_request(self):
        import threading
        from unittest.mock import patch
        ct, agent = self._dock()
        region = {"id": "jordan", "name": "Jordan", "shp_url": "https://example.invalid/x.zip",
                  "size_bytes": 30_000_000}
        started = threading.Event()

        def slow(region_, dest, is_cancelled=None, progress=None):
            started.set()
            while not is_cancelled():
                threading.Event().wait(0.02)
            raise InterruptedError("Download cancelled")

        with patch.object(type(ct), "_canvas_center", return_value=(35.93, 31.95)), \
             patch("cartogen_ai.core.agent.local_data_loader.probe_connectivity", return_value=True), \
             patch("cartogen_ai.core.agent.local_data_loader.resolve_region", return_value=region), \
             patch("cartogen_ai.core.agent.local_data_loader.download_and_extract", side_effect=slow):
            TestChatWidgetLive._reply(ct, _TRAVEL_Q)
            _pump(8000, until=started.is_set)
            self.assertTrue(ct.stop_btn.isEnabled())
            QTest.mouseClick(ct.stop_btn, Qt.MouseButton.LeftButton)
            _pump(8000, until=lambda: "Stopped." in ct.chat_browser.toPlainText())
        self.assertFalse(ct._awaiting_preview_reply, "Stop means stop, not continue online")
        self.assertTrue(ct.send_btn.isEnabled())
        self.assertEqual(agent.client.calls, 0)


if __name__ == "__main__":
    unittest.main()
