"""DEF-32 (round-3 smoke row V1): unticking the plugin during a request cancels it, and the CartogenAI log showed CRITICAL model_call provider_error and
cli_bridge_error lines (the bridge line was already INFO level; the CRITICAL one was the orchestrator's model_call). A request that ended because the user (or an unload) cancelled it is a stop, logged at INFO and reported as a stop."""
import unittest
from unittest.mock import patch

import cartogen_ai.core.agent.agent_orchestrator as agent_mod
from cartogen_ai.infrastructure.providers import cli_bridge as cb
from tests.test_agent_runner import _make_bare_agent


class _CancelledClient:
    def complete(self, messages, tools=None, max_tokens=None):
        return {"error": "The CLI request was cancelled."}


class TestOrchestratorLogsACancelAsAStop(unittest.TestCase):
    def _run(self, should_stop):
        logged = []
        agent = _make_bare_agent(_CancelledClient())
        with patch.object(agent_mod.CartogenAi, "_apply_auto_model_selection", lambda self, q: None), \
             patch("cartogen_ai.core.agent.agent_orchestrator.build_system_prompt", return_value="sys"), \
             patch("cartogen_ai.core.agent.agent_orchestrator.TOOLS_SCHEMA", []), \
             patch("cartogen_ai.core.agent.agent_orchestrator.time.sleep"), \
             patch("cartogen_ai.core.agent.agent_orchestrator.log_event", side_effect=lambda *a, **k: logged.append((a, k))):
            reply = agent.run("hello", should_stop=should_stop)
        return reply, [(a[0], k) for a, k in logged if a and a[0] == "model_call"]

    def test_a_cancelled_call_is_a_stop_and_not_an_error_line(self):
        calls = {"n": 0}

        def stop():
            calls["n"] += 1
            return calls["n"] > 1

        reply, model_calls = self._run(stop)
        self.assertEqual(reply, "[Agent stopped] Stopped by user.")
        self.assertEqual(len(model_calls), 1)
        self.assertEqual(model_calls[0][1]["outcome"], "cancelled")
        self.assertFalse(model_calls[0][1].get("error"))

    def test_the_same_error_without_a_stop_is_still_an_error_line(self):
        reply, model_calls = self._run(lambda: False)
        self.assertTrue(reply.startswith("[API error]"))
        self.assertEqual(model_calls[0][1]["outcome"], "provider_error")
        self.assertTrue(model_calls[0][1]["error"])


class TestCliBridgeLogsACancelQuietly(unittest.TestCase):
    def _complete(self, cancelled):
        event = type("E", (), {"is_set": staticmethod(lambda: cancelled)})()
        logged = []
        with patch.object(cb, "find_executable", return_value="/bin/claude"), \
             patch.object(cb, "run_cli", side_effect=cb.CliBridgeError("The CLI request was cancelled." if cancelled else "boom")), \
             patch.object(cb, "log_event", side_effect=lambda *a, **k: logged.append((a[0], k))):
            result = cb.ClaudeCliClient(cancel_event=event).complete([{"role": "user", "content": "hi"}])
        return result, logged

    def test_a_cancel_is_logged_under_its_own_name_not_as_an_error(self):
        result, logged = self._complete(True)
        self.assertIn("cancelled", result["error"])
        names = [n for n, _ in logged]
        self.assertIn("cli_bridge_cancelled", names)
        self.assertNotIn("cli_bridge_error", names)
        self.assertFalse(any(k.get("error") for _, k in logged))

    def test_any_other_failure_still_logs_the_error(self):
        result, logged = self._complete(False)
        self.assertEqual(result, {"error": "boom"})
        self.assertIn("cli_bridge_error", [n for n, _ in logged])
        self.assertNotIn("cli_bridge_cancelled", [n for n, _ in logged])


if __name__ == "__main__":
    unittest.main()
