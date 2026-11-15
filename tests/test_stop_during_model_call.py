"""rc40 hand test RC37-F2 / OI-223: Stop pressed while a model request is in flight. net.py drops the request; the orchestrator must
then report a stop, not an API error, and the provider retry loop must not resend it."""
import unittest
from unittest.mock import patch

import cartogen_ai.core.agent.agent_orchestrator as agent_mod
from tests.test_agent_runner import _make_bare_agent


class _DroppedRequestClient:
    def complete(self, messages, tools=None, max_tokens=None):
        raise ConnectionError("stopped by the user")


class TestStopDuringModelCall(unittest.TestCase):
    def _run(self, should_stop):
        agent = _make_bare_agent(_DroppedRequestClient())
        with patch.object(agent_mod.CartogenAi, "_apply_auto_model_selection", lambda self, q: None), \
             patch("cartogen_ai.core.agent.agent_orchestrator.build_system_prompt", return_value="sys"), \
             patch("cartogen_ai.core.agent.agent_orchestrator.TOOLS_SCHEMA", []), \
             patch("cartogen_ai.core.agent.agent_orchestrator.time.sleep"):
            return agent.run("hello", should_stop=should_stop)

    def test_a_dropped_request_after_stop_is_reported_as_a_stop(self):
        calls = {"n": 0}

        def stop():
            calls["n"] += 1
            return calls["n"] > 1                  # not stopped at the top of the turn, stopped once the request was dropped

        self.assertEqual(self._run(stop), "[Agent stopped] Stopped by user.")

    def test_the_same_failure_without_stop_is_still_an_api_error(self):
        self.assertTrue(self._run(lambda: False).startswith("[API error]"))

    def test_the_retry_loop_does_not_resend_after_stop(self):
        from cartogen_ai.infrastructure.providers import base
        from requests import RequestException
        sent = []

        def send():
            sent.append(1)
            raise RequestException("dropped")

        with patch.object(base, "_user_stopped", return_value=True), patch.object(base.time, "sleep"), \
             self.assertRaises(RequestException):
            base._request_with_retry(send, 5, 3)
        self.assertEqual(len(sent), 1)


if __name__ == "__main__":
    unittest.main()
