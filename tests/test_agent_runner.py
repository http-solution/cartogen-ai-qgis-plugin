# -*- coding: utf-8 -*-
import unittest
from unittest.mock import MagicMock, patch
from cartogen_ai.core.agent.prompts import build_system_prompt
from cartogen_ai.core.agent.memory import SpatialMemoryManager
from cartogen_ai.core.agent.task_manager import AgentTaskManager
import cartogen_ai.core.agent.agent_orchestrator as agent_mod
from cartogen_ai.core.models.transactions import TurnTransactionLog
from cartogen_ai.core.models.plan_gate import PlanValidationGate


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
        agent._plan_gate = PlanValidationGate()
        agent._is_plan_gate_enabled = lambda: False
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


class TestAddLayerFromPathTwoPhaseSourceLabel(unittest.TestCase):
    """The two-phase dispatch downloads a URL to a temp file, then calls
    add_layer_from_path with that local path. It must also pass the original URL, or
    the error and the default layer name come from the temp copy (live report
    2026-09-24: "Invalid layer: C:\\...\\Temp\\tmp_2kgn_72.geojson")."""

    def _agent(self):
        agent = agent_mod.CartogenAi.__new__(agent_mod.CartogenAi)
        agent.task_manager = MagicMock()
        agent.memory_manager = MagicMock()
        agent._get_schema_props = lambda name: {"file_path": {}, "layer_name": {}}
        agent._run_on_main_thread = lambda fn, args: fn(args)
        return agent

    def _dispatch(self, file_path, prefetch_result):
        import json
        agent = self._agent()
        with patch("cartogen_ai.core.agent.tools.vector_tools._prefetch_url_to_temp",
                   return_value=prefetch_result), \
             patch("cartogen_ai.core.agent.tools.vector_tools.add_layer_from_path",
                   return_value={"error": "x"}) as add_layer, \
             patch("os.remove"):
            agent._execute_two_phase_tool("add_layer_from_path", json.dumps({"file_path": file_path}))
        return add_layer

    def test_url_download_passes_original_url_as_source_label(self):
        url = "https://example.org/districts.geojson"
        add_layer = self._dispatch(url, ("/tmp/tmp_2kgn_72.geojson", True))
        add_layer.assert_called_once_with("/tmp/tmp_2kgn_72.geojson", None, url)

    def test_local_path_passes_no_source_label(self):
        add_layer = self._dispatch("/data/districts.geojson", ("/data/districts.geojson", False))
        add_layer.assert_called_once_with("/data/districts.geojson", None, None)


class _FakeClient:
    """Returns one tool call, then a final answer -- just enough to exercise
    run()'s tool-calling loop once."""
    def __init__(self, tool_name="get_layers", tool_result=None):
        self.calls = 0
        self.tool_name = tool_name

    def complete(self, messages, tools=None, max_tokens=None):
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
    agent.loop_guard_enabled = False     # these tests drive the loop to its cap on purpose; the guard has its own tests (test_loop_guard.py)
    agent.conversation_history = []
    agent.task_manager = MagicMock()
    agent.task_manager.get_plan.return_value = None
    agent.memory_manager = MagicMock()
    agent._auto_model_provider = None
    # run() resets this unconditionally at the top of every call (point 20's
    # transaction log, see models/transactions.py) -- a bare __new__()'d agent
    # needs one too, even though these tests patch _execute_tool itself and
    # never exercise the log's actual recording.
    agent._transaction_log = TurnTransactionLog()
    # Same reason: run() also resets _plan_gate unconditionally (§1.6 option (b),
    # models/plan_gate.py).
    agent._plan_gate = PlanValidationGate()
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
             patch("cartogen_ai.core.agent.agent_orchestrator.build_system_prompt", return_value="sys"), \
             patch("cartogen_ai.core.agent.agent_orchestrator.TOOLS_SCHEMA", []):
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
             patch("cartogen_ai.core.agent.agent_orchestrator.build_system_prompt", return_value="sys"), \
             patch("cartogen_ai.core.agent.agent_orchestrator.TOOLS_SCHEMA", []):
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
             patch("cartogen_ai.core.agent.agent_orchestrator.build_system_prompt", return_value="sys"), \
             patch("cartogen_ai.core.agent.agent_orchestrator.TOOLS_SCHEMA", []):
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
        self.max_tokens_per_call = []

    def complete(self, messages, tools=None, max_tokens=None):
        self.calls += 1
        self.messages_per_call.append([dict(m) for m in messages])  # snapshot, not a live ref
        self.max_tokens_per_call.append(max_tokens)
        return {"message": {
            "role": "assistant", "content": None,
            "tool_calls": [{"id": f"c{self.calls}", "function": {"name": self.tool_name, "arguments": "{}"}}],
        }}


class TestPacingAndCompaction(unittest.TestCase):
    """Large/complex requests used to fire up to MAX_ITERATIONS API calls back-to-back with no
    pacing, and re-send every prior tool result in full on every call -- real risk of tripping a
    provider's rate limit or a context-length ceiling on a genuinely large task. See
    PACING_THRESHOLD_ITERATIONS/PACING_DELAY_SECONDS and MAX_FULL_TOOL_RESULTS_PER_TURN's own
    comments in agent_orchestrator.py."""

    def _run_looping(self, execute_tool_fn):
        client = _CapturingLoopingClient()
        agent = _make_bare_agent(client)
        with patch.object(agent_mod.CartogenAi, "_apply_auto_model_selection", lambda self, q: None), \
             patch.object(agent_mod.CartogenAi, "_execute_tool", execute_tool_fn), \
             patch("cartogen_ai.core.agent.agent_orchestrator.build_system_prompt", return_value="sys"), \
             patch("cartogen_ai.core.agent.agent_orchestrator.TOOLS_SCHEMA", []), \
             patch("cartogen_ai.core.agent.agent_orchestrator.time.sleep") as mock_sleep:
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

    def test_max_tokens_scales_down_after_the_first_iteration(self):
        # Phase 6 (2026-09-19, cost/performance pass): the first client.complete() call of a
        # turn always gets the full DEFAULT_MAX_TOKENS (it might be a one-shot final answer,
        # never safe to cut), every later iteration of the same multi-tool-call turn gets the
        # reduced INTERMEDIATE_MAX_TOKENS budget instead of padding at full size regardless.
        client, _ = self._run_looping(lambda self, name, args: {"success": True})
        self.assertEqual(client.max_tokens_per_call[0], agent_mod.DEFAULT_MAX_TOKENS)
        self.assertTrue(len(client.max_tokens_per_call) > 1)
        for later in client.max_tokens_per_call[1:]:
            self.assertEqual(later, agent_mod.INTERMEDIATE_MAX_TOKENS)
        self.assertLess(agent_mod.INTERMEDIATE_MAX_TOKENS, agent_mod.DEFAULT_MAX_TOKENS)

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
             patch("cartogen_ai.core.agent.agent_orchestrator.build_system_prompt", return_value="sys"), \
             patch("cartogen_ai.core.agent.agent_orchestrator.TOOLS_SCHEMA", []), \
             patch("cartogen_ai.core.agent.agent_orchestrator.time.sleep"):
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


class TestSandboxFlailingNudgeInjectedMidTurn(unittest.TestCase):
    """Integration test for the circuit breaker above run()'s tool-calling loop: a client
    that only ever calls execute_pyqgis_script, always rejected by the sandbox, must get the
    corrective nudge appended to `messages` as soon as SANDBOX_FLAILING_THRESHOLD consecutive
    rejections have happened -- not just that the pure detector function returns the right
    string in isolation (already covered in test_new_tools.py), but that run()'s own loop
    actually wires it in at the right point and only once."""

    def _run_always_rejected(self):
        client = _CapturingLoopingClient(tool_name="execute_pyqgis_script")
        agent = _make_bare_agent(client)
        rejected = {"error": "Script rejected for safety: Blocked import 'os' -- not allowed in execute_pyqgis_script."}
        with patch.object(agent_mod.CartogenAi, "_apply_auto_model_selection", lambda self, q: None), \
             patch.object(agent_mod.CartogenAi, "_execute_tool", lambda self, name, args: dict(rejected)), \
             patch("cartogen_ai.core.agent.agent_orchestrator.build_system_prompt", return_value="sys"), \
             patch("cartogen_ai.core.agent.agent_orchestrator.TOOLS_SCHEMA", []), \
             patch("cartogen_ai.core.agent.agent_orchestrator.time.sleep"):
            agent.run("find some health facility data")
        return client

    def test_nudge_appears_in_messages_after_the_threshold_is_reached(self):
        client = self._run_always_rejected()
        # The call right after the threshold-th rejection is the first one that could
        # possibly carry the nudge -- it must be present from there through the end.
        call_with_nudge = client.messages_per_call[agent_mod.SANDBOX_FLAILING_THRESHOLD]
        nudge_msgs = [m for m in call_with_nudge if "execute_pyqgis_script is a last resort" in (m.get("content") or "")]
        self.assertEqual(len(nudge_msgs), 1)

    def test_nudge_never_appears_before_the_threshold_is_reached(self):
        client = self._run_always_rejected()
        for call_messages in client.messages_per_call[:agent_mod.SANDBOX_FLAILING_THRESHOLD]:
            nudge_msgs = [m for m in call_messages if "execute_pyqgis_script is a last resort" in (m.get("content") or "")]
            self.assertEqual(nudge_msgs, [])

    def test_nudge_is_injected_only_once_across_the_whole_turn(self):
        # A 20-iteration turn that never recovers would otherwise get re-nudged every
        # single iteration once past the threshold -- must fire exactly once.
        client = self._run_always_rejected()
        last_call = client.messages_per_call[-1]
        nudge_msgs = [m for m in last_call if "execute_pyqgis_script is a last resort" in (m.get("content") or "")]
        self.assertEqual(len(nudge_msgs), 1)


class TestExecuteToolTransactionRecording(unittest.TestCase):
    """_execute_tool (agent_orchestrator.py) wraps every tool call with a before/after
    live-layer-id snapshot and records it into self._transaction_log --
    point 20's transaction log (see models/transactions.py). This exercises
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

            File "agent_orchestrator.py", line ~1056, in run
                tool_result = self._execute_tool(name, arguments)
            File "agent_orchestrator.py", line ~515, in _execute_tool
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
        agent._plan_gate = PlanValidationGate()
        agent._is_plan_gate_enabled = lambda: False
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


class TestConversationHistoryThreadSafety(unittest.TestCase):
    """Phase 5 (2026-09-19): conversation_history is mutated from run() on the background
    QgsTask thread AND from chat_tab_widget.py's image-attachment handler on the main Qt
    thread, with no lock -- a genuine cross-thread race. Real threading.Thread stress
    tests, not mocks, since this is one of the few things in this codebase actually
    testable without a live QGIS session (pure Python list + threading.Lock, no qgis.core
    involved) -- per the standing verify-before-closing rule, a real concurrency test is
    preferred over "trust the lock exists" whenever one is feasible."""

    def _agent(self):
        agent = agent_mod.CartogenAi.__new__(agent_mod.CartogenAi)
        agent.conversation_history = []
        return agent

    def test_concurrent_appends_from_many_threads_lose_no_messages(self):
        agent = self._agent()
        # MAX_HISTORY_MESSAGES trimming would make a lost-message check ambiguous (a
        # message "missing" at the end could just be correctly trimmed) -- temporarily
        # raise it high enough that this test's own message count never triggers a trim,
        # so every successful append is expected to still be present at the end.
        original_max = agent_mod.MAX_HISTORY_MESSAGES
        agent_mod.MAX_HISTORY_MESSAGES = 100_000
        try:
            threads_n, appends_per_thread = 20, 50

            def worker(thread_id):
                for i in range(appends_per_thread):
                    agent._append_history({"role": "user", "content": f"t{thread_id}-{i}"})

            threads = [
                __import__("threading").Thread(target=worker, args=(t,))
                for t in range(threads_n)
            ]
            for th in threads:
                th.start()
            for th in threads:
                th.join()

            self.assertEqual(len(agent.conversation_history), threads_n * appends_per_thread)
            # No duplicate/corrupted entries -- every (thread_id, i) pair appears exactly
            # once, which a lost update or a torn append could otherwise violate.
            seen = {m["content"] for m in agent.conversation_history}
            self.assertEqual(len(seen), threads_n * appends_per_thread)
        finally:
            agent_mod.MAX_HISTORY_MESSAGES = original_max

    def test_concurrent_read_snapshot_and_append_never_raises_or_corrupts(self):
        """_read_history_snapshot() (the run()-message-building read) racing against
        _append_history() (a concurrent turn/image-attachment write) must never raise
        and must always return a list of well-formed dicts -- never a torn/partial
        read."""
        agent = self._agent()
        errors = []
        stop = __import__("threading").Event()

        def writer():
            i = 0
            while not stop.is_set():
                agent._append_history({"role": "user", "content": f"msg-{i}"})
                i += 1

        def reader():
            for _ in range(500):
                try:
                    snapshot = agent._read_history_snapshot()
                    for m in snapshot:
                        assert isinstance(m, dict) and "role" in m and "content" in m
                except Exception as e:
                    errors.append(e)

        import threading as _threading
        writer_thread = _threading.Thread(target=writer)
        reader_thread = _threading.Thread(target=reader)
        writer_thread.start()
        reader_thread.start()
        reader_thread.join()
        stop.set()
        writer_thread.join()

        self.assertEqual(errors, [])


class TestHistoryDigestOnTrim(unittest.TestCase):
    """Phase 6 (2026-09-19, cost/performance pass): _trim_history() used to just slice off
    and discard the oldest messages once conversation_history exceeded MAX_HISTORY_MESSAGES
    -- older turns vanished from the model's context with no trace at all. It now collapses
    the dropped messages into a single synthetic role="system" digest entry (extractive, not
    an LLM call -- see _summarize_dropped_messages's own docstring) prepended ahead of the
    kept tail, and grows/re-caps that same digest entry on every subsequent trim instead of
    losing the earlier summary each time."""

    def _agent(self):
        agent = agent_mod.CartogenAi.__new__(agent_mod.CartogenAi)
        agent.conversation_history = []
        return agent

    def test_trim_beyond_cap_produces_a_leading_digest_message(self):
        agent = self._agent()
        original_max = agent_mod.MAX_HISTORY_MESSAGES
        agent_mod.MAX_HISTORY_MESSAGES = 10
        try:
            for i in range(20):
                agent._append_history({"role": "user", "content": f"turn {i}"})
            history = agent.conversation_history
            self.assertEqual(len(history), 11)
            self.assertTrue(agent_mod.CartogenAi._is_digest_message(history[0]))
            self.assertIn("turn 0", history[0]["content"])
            self.assertIn("turn 9", history[0]["content"])
            # The kept tail is untouched, ordinary messages -- only what overflowed the cap
            # was summarized away.
            self.assertEqual(history[1]["content"], "turn 10")
            self.assertEqual(history[-1]["content"], "turn 19")
        finally:
            agent_mod.MAX_HISTORY_MESSAGES = original_max

    def test_digest_grows_across_multiple_trims_instead_of_being_overwritten(self):
        agent = self._agent()
        original_max = agent_mod.MAX_HISTORY_MESSAGES
        agent_mod.MAX_HISTORY_MESSAGES = 4
        try:
            for i in range(6):
                agent._append_history({"role": "user", "content": f"a{i}"})
            first_digest = agent.conversation_history[0]["content"]
            self.assertIn("a0", first_digest)
            for i in range(6, 12):
                agent._append_history({"role": "user", "content": f"a{i}"})
            second_digest = agent.conversation_history[0]["content"]
            # Both the earliest-dropped and the next-dropped batch's content survive in the
            # single digest message -- growth, not replacement.
            self.assertIn("a0", second_digest)
            self.assertIn("a6", second_digest)
        finally:
            agent_mod.MAX_HISTORY_MESSAGES = original_max

    def test_digest_content_is_capped_and_never_unbounded(self):
        agent = self._agent()
        original_max = agent_mod.MAX_HISTORY_MESSAGES
        agent_mod.MAX_HISTORY_MESSAGES = 2
        try:
            for i in range(200):
                agent._append_history({"role": "user", "content": f"message number {i} " * 3})
            digest = agent.conversation_history[0]["content"]
            self.assertLessEqual(
                len(digest), len(agent_mod._HISTORY_DIGEST_MARKER) + agent_mod._HISTORY_DIGEST_MAX_CHARS + 1
            )
        finally:
            agent_mod.MAX_HISTORY_MESSAGES = original_max

    def test_digest_message_is_excluded_from_persisted_history_on_reload(self):
        # chat_persistence.load_chat_history()/load_chat_history_with_timestamps() both
        # filter to role in ("user", "assistant") -- confirms the digest's role="system"
        # choice means it never round-trips back in as a fake chat bubble or fake API turn
        # after a project reopen, without needing to special-case it in chat_persistence.py.
        digest_entry = {"role": "system", "content": f"{agent_mod._HISTORY_DIGEST_MARKER}\nstuff"}
        real_entry = {"role": "user", "content": "hello"}
        with patch(
            "cartogen_ai.core.agent.chat_persistence._load_raw_entries",
            return_value=[digest_entry, real_entry],
        ):
            from cartogen_ai.core.agent.chat_persistence import load_chat_history
            restored = load_chat_history()
        self.assertEqual(restored, [{"role": "user", "content": "hello"}])

    def test_history_lock_is_lazily_created_for_bypassed_init(self):
        """CartogenAi.__new__(CartogenAi) (this file's own established test pattern, used
        throughout) skips __init__ entirely, so _history_lock never gets created the
        normal way -- _get_history_lock() must still work rather than raising
        AttributeError, exactly the regression this test guards against."""
        agent = agent_mod.CartogenAi.__new__(agent_mod.CartogenAi)
        agent.conversation_history = []
        lock = agent._get_history_lock()
        self.assertTrue(hasattr(lock, "acquire") and hasattr(lock, "release"))
        # Same lock instance on a second call, not a fresh one each time.
        self.assertIs(agent._get_history_lock(), lock)


class TestExceptionsAndLogging(unittest.TestCase):
    def test_cartogen_exception_hierarchy(self):
        from cartogen_ai.core.exceptions import (
            CartogenError, ApiError, SpatialValidationError, SecuritySandboxError
        )
        e = ApiError("rate limited", provider="gemini", status_code=429)
        self.assertIsInstance(e, CartogenError)
        d = e.to_dict()
        self.assertIn("error", d)
        self.assertEqual(d["details"]["status_code"], 429)

        s = SpatialValidationError("CRS mismatch", layer_name="roads")
        self.assertEqual(s.details["layer_name"], "roads")

        sec = SecuritySandboxError("import os blocked", blocked_ident="os")
        self.assertEqual(sec.blocked_ident, "os")

    def test_logger_functions(self):
        from cartogen_ai.core.logger import log_info, log_warning, log_error
        # Verify logging executes cleanly without throwing
        log_info("Test informational message", tag="Test")
        log_warning("Test warning message", tag="Test")
        log_error("Test error message", tag="Test")


class TestProjectInspectorWiring(unittest.TestCase):
    """§1.5 option (b): run()'s actual wiring to project_inspector.inspect_project(), not
    just the module's own formatting (see test_project_inspector.py / test_prompt_modules.py's
    TestProjectInspectorContext for those). Same _make_bare_agent + patched build_system_prompt
    pattern as TestToolStepCallback above."""

    def _run_and_capture_build_system_prompt_call(self, gate_enabled, inspect_project_return):
        client = _FakeClient()
        agent = _make_bare_agent(client)
        agent._is_project_inspector_enabled = lambda: gate_enabled
        captured = {}

        def fake_build_system_prompt(*args, **kwargs):
            captured.update(kwargs)
            return "sys"

        with patch.object(agent_mod.CartogenAi, "_apply_auto_model_selection", lambda self, q: None), \
             patch.object(agent_mod.CartogenAi, "_execute_tool", lambda self, name, args: {"success": True}), \
             patch("cartogen_ai.core.agent.agent_orchestrator.build_system_prompt", fake_build_system_prompt), \
             patch("cartogen_ai.core.agent.agent_orchestrator.TOOLS_SCHEMA", []), \
             patch("cartogen_ai.core.services.project_inspector.inspect_project",
                   return_value=inspect_project_return) as mock_inspect:
            agent.run("list my layers")
        return captured, mock_inspect

    def test_disabled_never_calls_inspect_project(self):
        captured, mock_inspect = self._run_and_capture_build_system_prompt_call(
            gate_enabled=False, inspect_project_return={"layouts": ["x"]},
        )
        mock_inspect.assert_not_called()
        self.assertIsNone(captured.get("project_inspector_ctx"))

    def test_enabled_calls_inspect_project_and_passes_its_result_through(self):
        snapshot = {"layouts": ["Sitrep A3"], "themes": [], "metadata": {}}
        captured, mock_inspect = self._run_and_capture_build_system_prompt_call(
            gate_enabled=True, inspect_project_return=snapshot,
        )
        mock_inspect.assert_called_once()
        self.assertEqual(captured.get("project_inspector_ctx"), snapshot)


class TestPlanValidationGateWiring(unittest.TestCase):
    """§1.6 option (b): _real_execute_tool's actual wiring to PlanValidationGate, not just
    the gate class itself (see test_plan_gate.py for that). Same __new__/patch.dict(TOOL_REGISTRY)
    pattern as TestPreviewRequiredCreatesADedicatedTask above."""

    def _agent(self, gate_enabled):
        from cartogen_ai.core.models.plan_gate import PlanValidationGate
        agent = agent_mod.CartogenAi.__new__(agent_mod.CartogenAi)
        agent._plan_gate = PlanValidationGate()
        agent.task_manager = MagicMock()
        agent.memory_manager = MagicMock()
        agent._last_tool_call = None
        agent._is_plan_gate_enabled = lambda: gate_enabled
        return agent

    def _fake_export_tool(self, **kwargs):
        return {"success": True, "output_path": "/tmp/out.csv"}

    def test_disabled_gate_calls_the_publish_tool_normally(self):
        agent = self._agent(gate_enabled=False)
        with patch.dict(agent_mod.TOOL_REGISTRY, {"export_to_csv": self._fake_export_tool}):
            res = agent._real_execute_tool("export_to_csv", "{}")
        self.assertTrue(res.get("success"))

    def test_enabled_gate_blocks_a_publish_tool_before_any_plan(self):
        agent = self._agent(gate_enabled=True)
        with patch.dict(agent_mod.TOOL_REGISTRY, {"export_to_csv": self._fake_export_tool}):
            res = agent._real_execute_tool("export_to_csv", "{}")
        self.assertEqual(res["status"], "PLAN_REQUIRED")
        self.assertEqual(res["tool_name"], "export_to_csv")

    def test_enabled_gate_never_blocks_a_read_tool(self):
        agent = self._agent(gate_enabled=True)
        with patch.dict(agent_mod.TOOL_REGISTRY, {"get_layers": lambda: {"success": True, "layers": []}}):
            res = agent._real_execute_tool("get_layers", "{}")
        self.assertTrue(res.get("success"))

    def test_calling_create_plan_unblocks_a_later_publish_call_the_same_turn(self):
        agent = self._agent(gate_enabled=True)

        def fake_create_plan(**kwargs):
            return {"success": True, "title": kwargs.get("title", ""), "task_count": 0, "plan": {}}

        with patch.dict(agent_mod.TOOL_REGISTRY,
                         {"create_plan": fake_create_plan, "export_to_csv": self._fake_export_tool}):
            blocked = agent._real_execute_tool("export_to_csv", "{}")
            self.assertEqual(blocked["status"], "PLAN_REQUIRED")

            plan_res = agent._real_execute_tool(
                "create_plan", {"title": "Export roads", "task_descriptions": ["Export to CSV"]},
            )
            self.assertTrue(plan_res.get("success"))

            allowed = agent._real_execute_tool("export_to_csv", "{}")
        self.assertTrue(allowed.get("success"))

    def test_a_failed_create_plan_call_does_not_unblock_the_gate(self):
        agent = self._agent(gate_enabled=True)

        def failing_create_plan(**kwargs):
            return {"error": "boom"}

        with patch.dict(agent_mod.TOOL_REGISTRY,
                         {"create_plan": failing_create_plan, "export_to_csv": self._fake_export_tool}):
            agent._real_execute_tool("create_plan", {"title": "x", "task_descriptions": []})
            res = agent._real_execute_tool("export_to_csv", "{}")
        self.assertEqual(res["status"], "PLAN_REQUIRED")


class TestEgressGateWiring(unittest.TestCase):
    """Cloud-provider egress gate (docs/OLLAMA_ENFORCEMENT_GATE_SCOPE_2026-09-24.md): the plumbing
    in _real_execute_tool, then _egress_gate_decision itself against a fake qgis.core."""

    def _agent(self):
        agent = agent_mod.CartogenAi.__new__(agent_mod.CartogenAi)
        agent._plan_gate = PlanValidationGate()
        agent._is_plan_gate_enabled = lambda: False
        agent.task_manager = MagicMock()
        agent.memory_manager = MagicMock()
        agent._last_tool_call = None
        return agent

    def _run(self, decision, user_confirmed=False):
        calls = []

        def fake_tool(**kwargs):
            calls.append(kwargs)
            return {"success": True}

        agent = self._agent()
        with patch.object(agent_mod.CartogenAi, "_egress_gate_decision", lambda self, n, a: decision),              patch.dict(agent_mod.TOOL_REGISTRY, {"buffer_analysis": fake_tool}):
            res = agent._real_execute_tool("buffer_analysis", "{}", user_confirmed=user_confirmed)
        return res, calls

    def test_block_with_known_layers_returns_a_preview_not_the_raw_block(self):
        # §1.4 decision 2 (override policy, 2026-09-28): a block with known layers is
        # overridable, so it's wrapped as PREVIEW_REQUIRED (reusing the existing
        # destructive-action Confirm-button machinery) instead of handed to the model as a
        # flat EGRESS_BLOCKED result -- the raw block dict is no longer what the caller sees.
        blocked = {"status": "EGRESS_BLOCKED", "message": "no"}
        res, calls = self._run({"action": "block", "layers": {"a": "tagged SENSITIVE"}, "result": blocked})
        self.assertEqual(res["status"], "PREVIEW_REQUIRED")
        self.assertIn("a", res["rationale"])
        self.assertEqual(calls, [])

    def test_block_with_no_layers_is_never_overridable(self):
        # A check-failure block (egress_gate.check_failed_decision) has empty layers -- there's
        # nothing concrete to show the user, so it stays a hard block even with user_confirmed=True.
        blocked = {"status": "EGRESS_BLOCKED", "message": "check failed"}
        res, calls = self._run({"action": "block", "layers": {}, "result": blocked}, user_confirmed=True)
        self.assertEqual(res, blocked)
        self.assertEqual(calls, [])

    def test_confirmed_override_runs_the_tool_and_attaches_a_note(self):
        blocked = {"status": "EGRESS_BLOCKED", "message": "no"}
        res, calls = self._run(
            {"action": "block", "layers": {"a": "tagged SENSITIVE"}, "result": blocked},
            user_confirmed=True,
        )
        self.assertTrue(res["success"])
        self.assertIn("a", res["egress_override_note"])
        self.assertEqual(len(calls), 1)

    def test_warn_runs_the_tool_and_attaches_the_warning(self):
        res, calls = self._run({"action": "warn", "layers": {"a": "x"}, "result": None, "warning": "careful"})
        self.assertTrue(res["success"])
        self.assertEqual(res["egress_warning"], "careful")
        self.assertEqual(len(calls), 1)

    def test_no_decision_runs_the_tool_untouched(self):
        res, calls = self._run(None)
        self.assertEqual(res, {"success": True})
        self.assertEqual(len(calls), 1)

    def test_default_is_off_and_needs_no_instance_state(self):
        # No patching of the decision: outside QGIS the mode reads "off", so this is a no-op and
        # must not touch self.client, the project or anything else the bare agent lacks.
        agent = self._agent()
        self.assertIsNone(agent._egress_gate_decision("buffer_analysis", {"layer_name": "x"}))

    # -- _egress_gate_decision against a fake qgis.core -------------------------------------
    def _fake_qgis(self, layers, raise_on_layers=False):
        """layers: {name: (sensitivity_level_or_None, [lineage source names])}"""
        import json
        import sys
        import types

        from cartogen_ai.core.models.sensitivity import SENSITIVITY_PROPERTY_KEY
        from cartogen_ai.core.agent.lineage import LINEAGE_PROPERTY_KEY

        class FakeLayer:
            def __init__(self, name, level, sources):
                self._n, self._level, self._sources = name, level, sources

            def name(self):
                return self._n

            def id(self):                      # every real QgsMapLayer has one; the gate now resolves lineage source ids
                return "id_" + self._n

            def customProperty(self, key, default=""):
                if key == SENSITIVITY_PROPERTY_KEY and self._level:
                    return json.dumps({"level": self._level, "reason": None})
                if key == LINEAGE_PROPERTY_KEY and self._sources:
                    return json.dumps([{"tool": "t", "params": {}, "sources": self._sources}])
                return default

        objs = {n: FakeLayer(n, lv, src) for n, (lv, src) in layers.items()}

        class FakeProject:
            @staticmethod
            def instance():
                return FakeProject()

            def mapLayers(self):
                if raise_on_layers:
                    raise RuntimeError("boom")
                return dict(objs)

            def mapLayersByName(self, name):
                return [objs[name]] if name in objs else []

        core = types.ModuleType("qgis.core")
        core.QgsProject = FakeProject
        pkg = types.ModuleType("qgis")
        pkg.core = core
        return patch.dict(sys.modules, {"qgis": pkg, "qgis.core": core})

    def _decide(self, base_url, layers, mode="enforce", strict=False, tool="buffer_analysis",
                args=None, raise_on_layers=False):
        from cartogen_ai.core.agent import lineage
        from cartogen_ai.core.models import egress_gate
        agent = self._agent()
        agent.client = MagicMock(base_url=base_url)
        args = args if args is not None else {"layer_name": "beneficiaries"}
        with self._fake_qgis(layers, raise_on_layers),              patch.object(lineage, "QGIS_AVAILABLE", True),              patch.object(egress_gate, "read_mode", return_value=mode),              patch.object(egress_gate, "read_strict", return_value=strict):
            return agent._egress_gate_decision(tool, args)

    LAYERS = {"beneficiaries": ("SENSITIVE", []), "boundary": ("PUBLIC", [])}

    def test_cloud_provider_and_a_sensitive_layer_is_blocked(self):
        res = self._decide("https://api.openai.com/v1/chat/completions", self.LAYERS)
        self.assertEqual(res["action"], "block")
        self.assertEqual(res["result"]["status"], "EGRESS_BLOCKED")

    def test_local_provider_is_allowed(self):
        self.assertIsNone(self._decide("http://127.0.0.1:11434/v1/chat/completions", self.LAYERS))

    def test_a_client_with_no_readable_endpoint_counts_as_cloud(self):
        self.assertEqual(self._decide(None, self.LAYERS)["action"], "block")

    def test_a_public_layer_is_allowed_on_cloud(self):
        self.assertIsNone(self._decide("https://api.openai.com/v1", self.LAYERS,
                                       args={"layer_name": "boundary"}))

    def test_lineage_from_the_real_property_is_followed(self):
        layers = {"src": ("SENSITIVE", []), "buffered": (None, ["src"])}
        res = self._decide("https://api.openai.com/v1", layers, args={"layer_name": "buffered"})
        self.assertEqual(res["action"], "block")
        self.assertIn("derived from 'src'", res["layers"]["buffered"])

    def test_check_failure_blocks_in_enforce_mode(self):
        res = self._decide("https://api.openai.com/v1", self.LAYERS, raise_on_layers=True)
        self.assertEqual(res["action"], "block")
        self.assertIn("could not be completed", res["result"]["message"])

    def test_check_failure_does_not_block_in_warn_mode(self):
        self.assertIsNone(self._decide("https://api.openai.com/v1", self.LAYERS, mode="warn",
                                       raise_on_layers=True))


class TestMemoryToolsRefuseCoordinates(unittest.TestCase):
    """rc7 smoke test 2026-09-30 (F23): the model wrote the (wrong) analysis origin into project memory
    unprompted, where it persists and is fed back into later prompts."""

    def _tools(self):
        from cartogen_ai.core.agent.tools import task_tools
        return task_tools

    def test_a_note_with_coordinates_is_refused_and_not_stored(self):
        task_tools = self._tools()
        manager = MagicMock()
        with patch.object(task_tools, "_MEMORY_MANAGER", manager):
            res = task_tools.store_project_memory(
                "service_area_analysis", "Computed 1-hour service area around 44.036028, 15.970136.")
        self.assertIn("error", res)
        self.assertIn("coordinates", res["error"].lower())
        manager.store_project_note.assert_not_called()

    def test_the_same_guard_applies_to_global_memory(self):
        task_tools = self._tools()
        manager = MagicMock()
        with patch.object(task_tools, "_MEMORY_MANAGER", manager):
            res = task_tools.store_global_memory("home_base", "4902068.0, 1799912.0")
        self.assertIn("error", res)
        manager.store_global_note.assert_not_called()

    def test_an_ordinary_note_is_stored_as_before(self):
        task_tools = self._tools()
        manager = MagicMock()
        manager.store_project_note.return_value = {"success": True}
        with patch.object(task_tools, "_MEMORY_MANAGER", manager):
            res = task_tools.store_project_memory("style", "User prefers hospitals shown in red.")
        self.assertEqual(res, {"success": True})
        manager.store_project_note.assert_called_once()


if __name__ == "__main__":
    unittest.main()
