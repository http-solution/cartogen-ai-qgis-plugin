# -*- coding: utf-8 -*-
import unittest
from unittest.mock import MagicMock, patch
from cartogen_ai.core.agent.prompts import build_system_prompt
from cartogen_ai.core.agent.memory import SpatialMemoryManager
from cartogen_ai.core.agent.task_manager import AgentTaskManager
import cartogen_ai.core.agent.agent as agent_mod
from cartogen_ai.core.agent.transactions import TurnTransactionLog


class TestAgentRunner(unittest.TestCase):
    def test_dynamic_prompt_builder(self):
        tm = AgentTaskManager()
        tm.create_plan("Urban Growth Analysis", ["Load Landuse", "Calculate Centroids"])

        mm = SpatialMemoryManager()
        mm.store_project_note("city", "Damascus")

        prompt = build_system_prompt(task_manager=tm, memory_manager=mm)
        self.assertIn("Urban Growth Analysis", prompt)
        self.assertIn("Damascus", prompt)
        self.assertIn("AGENTIC TASK & MEMORY RULES", prompt)

    def test_system_prompt_includes_compact_registered_task_context(self):
        prompt = build_system_prompt(map_context={"task_directive": "Recognised task 01.01. Deliver: an HTML dashboard."})
        self.assertIn("REGISTERED TASK CONTEXT", prompt)
        self.assertIn("Recognised task 01.01", prompt)

class TestToolArgumentShapeValidation(unittest.TestCase):
    """A well-formed JSON document that isn't an object (a bare string, list, or number)
    parses successfully via json.loads -- it just isn't usable as kwargs. A double-JSON-
    encoded tool-call arguments string (the model's own arguments field is itself a
    JSON-encoded string, a known real-world LLM tool-calling quirk) hits exactly this
    shape: parsing it once yields a plain string, not the intended object. Without an
    explicit isinstance check, the next line's args.items() raises an uncaught
    "'str' object has no attribute 'items'" -- same bug class as the already-fixed
    usage-parsing crashes (extract_openai_style_usage), a different call site.
    Investigated as a candidate root cause for a real live report of an unexplained
    "'str' object has no attribute 'get'" crash after a real multi-tool-call Gemini
    turn; not confirmed as the exact site (no traceback was available), but a real,
    demonstrable gap in the same bug class regardless."""

    def _agent(self):
        agent = agent_mod.CartogenAi.__new__(agent_mod.CartogenAi)
        agent.task_manager = MagicMock()
        agent.memory_manager = MagicMock()
        return agent

    def test_real_execute_tool_rejects_double_encoded_string_arguments(self):
        agent = self._agent()
        # json.loads('"{\\"a\\": 1}"') -- a JSON string literal whose *content* looks like
        # an object -- decodes to the Python str '{"a": 1}', not a dict. Exactly the
        # double-encoding shape this guards against.
        double_encoded = '"{\\"layer_name\\": \\"X\\"}"'
        res = agent._real_execute_tool("get_layers", double_encoded)
        self.assertIn("error", res)
        self.assertIn("Invalid tool arguments", res["error"])
        self.assertIn("str", res["error"])

    def test_real_execute_tool_rejects_bare_list_arguments(self):
        agent = self._agent()
        res = agent._real_execute_tool("get_layers", "[1, 2, 3]")
        self.assertIn("error", res)
        self.assertIn("Invalid tool arguments", res["error"])

    def test_real_execute_tool_still_accepts_a_real_dict(self):
        agent = self._agent()
        # A real, working tool call must be completely unaffected by the new check.
        res = agent._real_execute_tool("get_layers", "{}")
        self.assertNotIn("Invalid tool arguments", str(res.get("error", "")))

    def test_execute_two_phase_tool_rejects_double_encoded_string_arguments(self):
        agent = self._agent()
        res = agent._execute_two_phase_tool("fetch_geoboundaries", '"{\\"iso3\\": \\"YEM\\"}"')
        self.assertIn("error", res)
        self.assertIn("Invalid tool arguments", res["error"])


class _FakeClient:
    """Returns one tool call, then a final answer -- just enough to exercise
    run()'s tool-calling loop once."""
    def __init__(self, tool_name="get_layers", tool_result=None):
        self.calls = 0
        self.tool_name = tool_name

    def complete(self, messages, tools=None):
        self.calls += 1
        if self.calls == 1:
            return {"message": {
                "role": "assistant", "content": None,
                "tool_calls": [{"id": "c1", "function": {"name": self.tool_name, "arguments": "{}"}}],
            }}
        return {"message": {"role": "assistant", "content": "All done."}}


def _make_bare_agent(client):
    agent = agent_mod.CartogenAi.__new__(agent_mod.CartogenAi)
    agent.client = client
    agent.conversation_history = []
    agent.task_manager = MagicMock()
    agent.task_manager.get_plan.return_value = None
    agent.memory_manager = MagicMock()
    agent._auto_model_provider = None
    # run() resets this unconditionally at the top of every call (point 20's
    # transaction log, see agent/transactions.py) -- a bare __new__()'d agent
    # needs one too, even though these tests patch _execute_tool itself and
    # never exercise the log's actual recording.
    agent._transaction_log = TurnTransactionLog()
    return agent


class TestToolStepCallback(unittest.TestCase):
    """agent.run()'s tool_step_callback is what lets the UI show live
    per-tool-call progress in chat (previously nothing was visible during a
    multi-tool-call turn) -- verified live against a real run() call, not
    just that the parameter exists."""

    def _run_with_tool_result(self, tool_result):
        client = _FakeClient()
        agent = _make_bare_agent(client)
        steps = []

        with patch.object(agent_mod.CartogenAi, "_apply_auto_model_selection", lambda self, q: None), \
             patch.object(agent_mod.CartogenAi, "_execute_tool", lambda self, name, args: tool_result), \
             patch("cartogen_ai.core.agent.agent.build_system_prompt", return_value="sys"), \
             patch("cartogen_ai.core.agent.agent.TOOLS_SCHEMA", []):
            final_text = agent.run("list my layers", tool_step_callback=lambda n, s, e: steps.append((n, s, e)))
        return final_text, steps

    def test_fires_running_then_done_on_success(self):
        final_text, steps = self._run_with_tool_result({"success": True, "layers": []})
        self.assertEqual(final_text, "All done.")
        self.assertEqual(steps, [("get_layers", "running", None), ("get_layers", "done", None)])

    def test_fires_running_then_failed_on_tool_error(self):
        final_text, steps = self._run_with_tool_result({"error": "Layer 'X' not found"})
        self.assertEqual(steps, [
            ("get_layers", "running", None),
            ("get_layers", "failed", "Layer 'X' not found"),
        ])

    def test_run_still_works_with_no_callback_given(self):
        # tool_step_callback is optional -- confirms the loop doesn't require it.
        client = _FakeClient()
        agent = _make_bare_agent(client)
        with patch.object(agent_mod.CartogenAi, "_apply_auto_model_selection", lambda self, q: None), \
             patch.object(agent_mod.CartogenAi, "_execute_tool", lambda self, name, args: {"success": True}), \
             patch("cartogen_ai.core.agent.agent.build_system_prompt", return_value="sys"), \
             patch("cartogen_ai.core.agent.agent.TOOLS_SCHEMA", []):
            final_text = agent.run("list my layers")
        self.assertEqual(final_text, "All done.")

    def test_a_broken_callback_does_not_break_the_agent_loop(self):
        # tool_step_callback is UI-side rendering -- a bug there must never
        # take down the actual agent turn.
        client = _FakeClient()
        agent = _make_bare_agent(client)

        def broken_callback(name, status, error):
            raise RuntimeError("UI rendering bug")

        with patch.object(agent_mod.CartogenAi, "_apply_auto_model_selection", lambda self, q: None), \
             patch.object(agent_mod.CartogenAi, "_execute_tool", lambda self, name, args: {"success": True}), \
             patch("cartogen_ai.core.agent.agent.build_system_prompt", return_value="sys"), \
             patch("cartogen_ai.core.agent.agent.TOOLS_SCHEMA", []):
            final_text = agent.run("list my layers", tool_step_callback=broken_callback)
        self.assertEqual(final_text, "All done.")



class _CapturingLoopingClient:
    """Always returns another tool call -- drives run() all the way to MAX_ITERATIONS, same
    failure-mode shape as test_new_tools.py's LoopingClient -- but also snapshots the `messages`
    list passed on every call, so pacing/compaction (2026-09-12, large-request rate-limit
    resilience) can be inspected directly rather than only checked via side effects."""
    def __init__(self, tool_name="get_layers"):
        self.calls = 0
        self.tool_name = tool_name
        self.messages_per_call = []

    def complete(self, messages, tools=None):
        self.calls += 1
        self.messages_per_call.append([dict(m) for m in messages])  # snapshot, not a live ref
        return {"message": {
            "role": "assistant", "content": None,
            "tool_calls": [{"id": f"c{self.calls}", "function": {"name": self.tool_name, "arguments": "{}"}}],
        }}


class TestPacingAndCompaction(unittest.TestCase):
    """Large/complex requests used to fire up to MAX_ITERATIONS API calls back-to-back with no
    pacing, and re-send every prior tool result in full on every call -- real risk of tripping a
    provider's rate limit or a context-length ceiling on a genuinely large task. See
    PACING_THRESHOLD_ITERATIONS/PACING_DELAY_SECONDS and MAX_FULL_TOOL_RESULTS_PER_TURN's own
    comments in agent.py."""

    def _run_looping(self, execute_tool_fn):
        client = _CapturingLoopingClient()
        agent = _make_bare_agent(client)
        with patch.object(agent_mod.CartogenAi, "_apply_auto_model_selection", lambda self, q: None), \
             patch.object(agent_mod.CartogenAi, "_execute_tool", execute_tool_fn), \
             patch("cartogen_ai.core.agent.agent.build_system_prompt", return_value="sys"), \
             patch("cartogen_ai.core.agent.agent.TOOLS_SCHEMA", []), \
             patch("cartogen_ai.core.agent.agent.time.sleep") as mock_sleep:
            agent.run("do something with many steps")
        return client, mock_sleep

    def test_no_pacing_delay_below_threshold_paces_above_it(self):
        client, mock_sleep = self._run_looping(lambda self, name, args: {"success": True})
        # PACING_THRESHOLD_ITERATIONS=3 -> iterations 0,1,2 get no delay; every iteration from 3
        # up to MAX_ITERATIONS-1 does -- a small/typical turn never reaches this at all.
        expected_pacing_calls = agent_mod.MAX_ITERATIONS - agent_mod.PACING_THRESHOLD_ITERATIONS
        self.assertEqual(mock_sleep.call_count, expected_pacing_calls)
        for call in mock_sleep.call_args_list:
            self.assertEqual(call.args[0], agent_mod.PACING_DELAY_SECONDS)

    def test_old_successful_tool_results_get_compacted_recent_ones_dont(self):
        client, _ = self._run_looping(lambda self, name, args: {"success": True})
        last_messages = client.messages_per_call[-1]
        tool_msgs = [m for m in last_messages if m.get("role") == "tool"]
        compacted = [m for m in tool_msgs if m["content"] == agent_mod._COMPACTED_TOOL_RESULT_PLACEHOLDER]
        full = [m for m in tool_msgs if m["content"] != agent_mod._COMPACTED_TOOL_RESULT_PLACEHOLDER]
        self.assertGreater(len(compacted), 0, "a 20-iteration turn should have compacted some old results")
        self.assertEqual(len(full), agent_mod.MAX_FULL_TOOL_RESULTS_PER_TURN)

    def test_compaction_survives_a_malformed_non_dict_history_entry(self):
        """Real live report, recurring across this whole session at every tool-call count
        tried (18, then 3, then 1): a bare "Error: 'str' object has no attribute 'get'" with
        no [API error] prefix, meaning it escaped run() as a raw exception rather than a
        normal returned error string -- and only ever on a turn that had at least one tool
        call, at any count. _compact_old_tool_results's `m.get("role")` assumed every message
        is a dict; a malformed non-dict entry anywhere in conversation_history (the exact
        mechanism that produces one was not conclusively identified by code reading alone) hit
        exactly that. Confirms run() no longer raises when conversation_history contains one,
        for a turn that does make a tool call (any turn without one never reaches
        _compact_old_tool_results at all, matching why this was never seen on a plain
        conversational turn)."""
        client = _CapturingLoopingClient()
        agent = _make_bare_agent(client)
        agent.conversation_history = ["a malformed history entry, not a {\"role\":...} dict"]
        with patch.object(agent_mod.CartogenAi, "_apply_auto_model_selection", lambda self, q: None), \
             patch.object(agent_mod.CartogenAi, "_execute_tool", lambda self, name, args: {"success": True}), \
             patch("cartogen_ai.core.agent.agent.build_system_prompt", return_value="sys"), \
             patch("cartogen_ai.core.agent.agent.TOOLS_SCHEMA", []), \
             patch("cartogen_ai.core.agent.agent.time.sleep"):
            final_text = agent.run("do something with a tool call")
        self.assertNotIn("has no attribute 'get'", final_text or "")

    def test_oversized_tool_result_compacted_immediately_not_only_after_8_calls(self):
        """Real live report, 2026-09-16: a Gemini 400 'input token count exceeds the maximum
        number of tokens allowed 1048576' after only 5 tool calls -- inspect_canvas_visually
        returns a full base64 PNG as its 'image_b64' field, easily hundreds of thousands of
        tokens on its own, and the count-based MAX_FULL_TOOL_RESULTS_PER_TURN window (8) never
        even got a chance to help. The new size-based rule should compact an oversized result
        as soon as a later tool call happens, not wait for 8 more tool calls first."""
        call_count = {"n": 0}
        huge_payload = "x" * (agent_mod._LARGE_TOOL_RESULT_CHAR_THRESHOLD + 5000)

        def fake_execute(self, name, args):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return {"success": True, "image_b64": huge_payload}
            return {"success": True}

        client, _ = self._run_looping(fake_execute)

        # The call immediately after the oversized result was produced -- the model must still
        # see it in full at least once, or the vision tool call was pointless.
        second_call_messages = client.messages_per_call[1]
        second_call_tool_msgs = [m for m in second_call_messages if m.get("role") == "tool"]
        self.assertIn(huge_payload, second_call_tool_msgs[0]["content"])

        # But well before 8 more tool calls have happened, it should already be compacted --
        # the old count-based rule alone would have kept it full until then.
        third_call_messages = client.messages_per_call[2]
        third_call_tool_msgs = [m for m in third_call_messages if m.get("role") == "tool"]
        self.assertEqual(third_call_tool_msgs[0]["content"], agent_mod._COMPACTED_TOOL_RESULT_PLACEHOLDER)

    def test_error_tool_result_never_compacted_even_once_old(self):
        call_count = {"n": 0}

        def fake_execute(self, name, args):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return {"error": "Layer not found"}
            return {"success": True}

        client, _ = self._run_looping(fake_execute)
        last_messages = client.messages_per_call[-1]
        tool_msgs = [m for m in last_messages if m.get("role") == "tool"]
        first_tool_msg = tool_msgs[0]
        # Well past MAX_FULL_TOOL_RESULTS_PER_TURN messages old by the end of a 20-iteration
        # turn -- would be compacted if it were a success, but errors are never compacted at
        # any age (the identical call chat_formatting.render_tool_steps_failure_details_html
        # makes for the same reason: failures are load-bearing, not droppable-because-old).
        self.assertIn("Layer not found", first_tool_msg["content"])
        self.assertNotEqual(first_tool_msg["content"], agent_mod._COMPACTED_TOOL_RESULT_PLACEHOLDER)


class TestExecuteToolTransactionRecording(unittest.TestCase):
    """_execute_tool (agent.py) wraps every tool call with a before/after
    live-layer-id snapshot and records it into self._transaction_log --
    point 20's transaction log (see agent/transactions.py). This exercises
    that wrapper directly, independent of run()'s loop."""

    def _make_agent(self):
        agent = agent_mod.CartogenAi.__new__(agent_mod.CartogenAi)
        agent._transaction_log = TurnTransactionLog()
        return agent

    def test_records_operation_type_and_result(self):
        agent = self._make_agent()
        with patch.object(agent_mod.CartogenAi, "_execute_tool_dispatch",
                           lambda self, name, args: {"success": True, "layers": []}), \
             patch.object(agent_mod.CartogenAi, "_live_layer_ids", lambda self: set()):
            result = agent._execute_tool("get_layers", "{}")

        self.assertEqual(result, {"success": True, "layers": []})
        entries = agent._transaction_log.summary()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["name"], "get_layers")
        self.assertEqual(entries[0]["operation_type"], "READ")
        self.assertTrue(entries[0]["success"])

    def test_new_layer_after_a_create_tool_is_recorded_as_undoable(self):
        agent = self._make_agent()
        layer_ids = iter([{"a"}, {"a", "b"}])  # before, then after
        with patch.object(agent_mod.CartogenAi, "_execute_tool_dispatch",
                           lambda self, name, args: {"success": True, "layer_name": "buf_1"}), \
             patch.object(agent_mod.CartogenAi, "_live_layer_ids", lambda self: next(layer_ids)):
            agent._execute_tool("buffer_analysis", "{}")

        entry = agent._transaction_log.last_undoable()
        self.assertIsNotNone(entry)
        self.assertEqual(entry["name"], "buffer_analysis")
        self.assertEqual(entry["undo"]["layer_ids"], ["b"])

    def test_unknown_tool_name_records_none_operation_type(self):
        agent = self._make_agent()
        with patch.object(agent_mod.CartogenAi, "_execute_tool_dispatch",
                           lambda self, name, args: {"error": "Unknown tool: bogus_tool"}), \
             patch.object(agent_mod.CartogenAi, "_live_layer_ids", lambda self: set()):
            agent._execute_tool("bogus_tool", "{}")

        entries = agent._transaction_log.summary()
        self.assertIsNone(entries[0]["operation_type"])
        self.assertFalse(entries[0]["success"])

    def test_snapshot_fn_is_called_before_dispatch_for_a_registered_tool(self):
        """v1.7.0: _snapshot_registry.py's snapshot_fn must run BEFORE the
        tool actually executes -- the whole point is capturing state the
        call is about to overwrite. Confirms the snapshot's result also
        flows through to the recorded entry's undo dict."""
        agent = self._make_agent()
        call_order = []
        fake_snapshot = {"kind": "restore_field", "layer_id": "x"}

        def fake_snapshot_fn(arguments):
            call_order.append("snapshot")
            return fake_snapshot

        def fake_dispatch(self, name, args):
            call_order.append("dispatch")
            return {"success": True}

        with patch.object(agent_mod, "get_snapshot_fn", lambda name: fake_snapshot_fn if name == "field_calculator" else None), \
             patch.object(agent_mod.CartogenAi, "_execute_tool_dispatch", fake_dispatch), \
             patch.object(agent_mod.CartogenAi, "_live_layer_ids", lambda self: set()):
            agent._execute_tool("field_calculator", {"layer_name": "x", "new_field": "y", "confirmed": True})

        self.assertEqual(call_order, ["snapshot", "dispatch"])
        entry = agent._transaction_log.summary()[0]
        self.assertEqual(entry["undo"]["kind"], "restore_field")
        self.assertEqual(entry["undo"]["tool_name"], "field_calculator")

    def test_snapshot_fn_receives_a_parsed_dict_not_a_raw_json_string(self):
        """Real live crash, 2026-09-16 -- finally caught with a real traceback after several
        earlier reports of the same bare "Error: 'str' object has no attribute 'get'" text
        with no traceback to confirm the site:

            File "agent.py", line ~1056, in run
                tool_result = self._execute_tool(name, arguments)
            File "agent.py", line ~515, in _execute_tool
                snapshot = snapshot_fn(arguments) if snapshot_fn else None
            File "_snapshot_registry.py", line 157, in _snapshot_style
                layer = _find_layer(arguments.get("layer_name"))
            AttributeError: 'str' object has no attribute 'get'

        run()'s loop reads `arguments` straight off the model's tool call as a raw JSON-encoded
        STRING (fn.get("arguments", "{}")) -- _real_execute_tool/_execute_two_phase_tool each
        parse it into a dict internally before use, but _execute_tool's own snapshot_fn(...)
        call ran on the still-raw string, before either dispatch path (and before this
        function's own try/except, which only wraps dispatch) ever touches it. Any tool
        registered with a snapshot function (apply_categorized_style, confirmed by the real
        traceback) crashed this way every time it was called with real (string) tool-call
        arguments -- test_snapshot_fn_is_called_before_dispatch_for_a_registered_tool above
        never caught this because it calls _execute_tool with an already-parsed dict, not the
        raw string shape run() actually passes."""
        agent = self._make_agent()
        received = {}

        def fake_snapshot_fn(arguments):
            received["arguments"] = arguments
            return {"kind": "restore_style", "layer_id": "x"}

        with patch.object(agent_mod, "get_snapshot_fn",
                           lambda name: fake_snapshot_fn if name == "apply_categorized_style" else None), \
             patch.object(agent_mod.CartogenAi, "_execute_tool_dispatch", lambda self, name, args: {"success": True}), \
             patch.object(agent_mod.CartogenAi, "_live_layer_ids", lambda self: set()):
            # The real shape run()'s loop passes: a raw JSON-encoded string, exactly what
            # fn.get("arguments", "{}") returns straight from the model's tool call.
            result = agent._execute_tool("apply_categorized_style", '{"layer_name": "Health Facilities", "field": "category"}')

        self.assertEqual(result, {"success": True})
        self.assertIsInstance(received["arguments"], dict)
        self.assertEqual(received["arguments"].get("layer_name"), "Health Facilities")

    def test_uncaught_dispatch_exception_becomes_a_normal_error_result(self):
        """Real live crash, 2026-09-13: a turn ended in a bare 'Error: 'str' object
        has no attribute 'get'' chat bubble -- an uncaught AttributeError that escaped
        run()'s tool-call loop entirely because _execute_tool_dispatch's TWO_PHASE_TOOLS
        path (unlike _real_execute_tool) had no exception handling of its own, and
        neither did this call site. This is the general safety net added for it: ANY
        exception from ANY dispatch path becomes a normal {"error": ...} result here,
        so a future tool with the same gap fails the same clean way instead of ending
        the whole turn uncaught."""
        agent = self._make_agent()

        def raising_dispatch(self, name, args):
            raise AttributeError("'str' object has no attribute 'get'")

        with patch.object(agent_mod.CartogenAi, "_execute_tool_dispatch", raising_dispatch), \
             patch.object(agent_mod.CartogenAi, "_live_layer_ids", lambda self: set()):
            result = agent._execute_tool("fetch_nasa_eonet_events", "{}")

        self.assertIn("error", result)
        self.assertIn("fetch_nasa_eonet_events", result["error"])
        self.assertIn("'str' object has no attribute 'get'", result["error"])
        # The transaction log must still see it as a normal, recorded failure --
        # not a call that silently never got logged because it raised.
        entries = agent._transaction_log.summary()
        self.assertEqual(len(entries), 1)
        self.assertFalse(entries[0]["success"])

    def test_no_registered_snapshot_fn_falls_back_to_layer_diff(self):
        """A tool with no _snapshot_registry.py entry (the common case) must
        behave exactly as before this feature existed -- undo determined by
        the new-layer-id diff, snapshot=None passed through record()."""
        agent = self._make_agent()
        layer_ids = iter([{"a"}, {"a", "b"}])
        with patch.object(agent_mod, "get_snapshot_fn", lambda name: None), \
             patch.object(agent_mod.CartogenAi, "_execute_tool_dispatch",
                           lambda self, name, args: {"success": True, "layer_name": "buf_1"}), \
             patch.object(agent_mod.CartogenAi, "_live_layer_ids", lambda self: next(layer_ids)):
            agent._execute_tool("buffer_analysis", "{}")

        entry = agent._transaction_log.last_undoable()
        self.assertEqual(entry["undo"], {"kind": "remove_layers", "layer_ids": ["b"]})


class TestPreviewRequiredCreatesADedicatedTask(unittest.TestCase):
    """2026-09-16 live bug: a destructive-action gate (field_calculator etc. returning
    {"status": "PREVIEW_REQUIRED"}) used to only start a fresh safety-gate plan when
    self.task_manager.tasks was completely empty; otherwise it glued the pending
    confirmation state onto tasks[0] of whatever plan happened to already be active --
    silently overwriting an unrelated, possibly already-DONE task's status and result.
    Reproduced here with a real AgentTaskManager (not a MagicMock) so the actual task
    list is inspected, not just that some method got called."""

    def _agent_with_real_task_manager(self):
        from cartogen_ai.core.agent.task_manager import AgentTaskManager
        agent = agent_mod.CartogenAi.__new__(agent_mod.CartogenAi)
        agent.task_manager = AgentTaskManager()
        agent.memory_manager = MagicMock()
        agent._last_tool_call = None
        return agent

    def _fake_destructive_tool(self, **kwargs):
        return {
            "status": "PREVIEW_REQUIRED",
            "requires_confirmation": True,
            "is_destructive": True,
            "code_snippet": "field_calculator(...)",
            "rationale": "Adds a numeric severity field.",
            "arguments": {"layer_name": "GDACS Disaster Alerts - Yemen",
                           "new_field": "severity", "expression": "2"},
        }

    def test_an_unrelated_already_done_task_is_left_untouched(self):
        agent = self._agent_with_real_task_manager()
        agent.task_manager.create_plan("Health facilities", ["Compile facilities"])
        agent.task_manager.update_task("1", "DONE", "Facilities compiled.")

        with patch.dict(agent_mod.TOOL_REGISTRY,
                         {"field_calculator": self._fake_destructive_tool}):
            agent._real_execute_tool("field_calculator", "{}")

        original = agent.task_manager.tasks[0]
        self.assertEqual(original["status"], "DONE")
        self.assertEqual(original["result"], "Facilities compiled.")
        self.assertNotIn("pending_tool", original)

    def test_the_pending_confirmation_lands_on_a_new_task(self):
        agent = self._agent_with_real_task_manager()
        agent.task_manager.create_plan("Health facilities", ["Compile facilities"])
        agent.task_manager.update_task("1", "DONE", "Facilities compiled.")

        with patch.dict(agent_mod.TOOL_REGISTRY,
                         {"field_calculator": self._fake_destructive_tool}):
            agent._real_execute_tool("field_calculator", "{}")

        self.assertEqual(len(agent.task_manager.tasks), 2)
        preview_task = agent.task_manager.tasks[1]
        self.assertEqual(preview_task["status"], "PREVIEW_READY")
        self.assertEqual(preview_task["pending_tool"], "field_calculator")
        self.assertEqual(preview_task["pending_args"]["new_field"], "severity")

    def test_an_empty_task_manager_still_starts_a_fresh_plan(self):
        """The pre-existing, already-correct behavior for the empty-plan case must
        keep working unchanged."""
        agent = self._agent_with_real_task_manager()

        with patch.dict(agent_mod.TOOL_REGISTRY,
                         {"field_calculator": self._fake_destructive_tool}):
            agent._real_execute_tool("field_calculator", "{}")

        self.assertEqual(len(agent.task_manager.tasks), 1)
        self.assertEqual(agent.task_manager.tasks[0]["status"], "PREVIEW_READY")
        self.assertEqual(agent.task_manager.tasks[0]["pending_tool"], "field_calculator")


if __name__ == "__main__":
    unittest.main()
