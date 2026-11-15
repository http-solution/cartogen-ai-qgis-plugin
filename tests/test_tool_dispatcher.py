"""Direct tests for core/agent/tool_dispatcher.py (PLAN-040 audit finding 11).

The queued cross-thread delivery is Qt's job and needs a live QGIS; what is ours, and tested here, is what the two slots do with the
agent: the result goes into the container, and any exception becomes an error dict instead of an empty container (an empty container is
what produced the "Execution failed unexpectedly." bug the module's comments describe).
"""
import unittest
from unittest import mock

from cartogen_ai.core.agent.tool_dispatcher import ToolDispatcher


class TestSlots(unittest.TestCase):
    def setUp(self):
        self.agent = mock.Mock()
        self.dispatcher = ToolDispatcher(self.agent)

    def test_execute_puts_the_agent_result_in_the_container(self):
        self.agent._real_execute_tool.return_value = {"success": True}
        box = []
        self.dispatcher._do_execute("buffer", {"d": 1}, box)
        self.agent._real_execute_tool.assert_called_once_with("buffer", {"d": 1})
        self.assertEqual(box, [{"success": True}])

    def test_execute_turns_an_exception_into_an_error_dict(self):
        self.agent._real_execute_tool.side_effect = RuntimeError("boom")
        box = []
        self.dispatcher._do_execute("buffer", {}, box)
        self.assertEqual(len(box), 1)
        self.assertIn("boom", box[0]["error"])
        self.assertIn("_do_execute raised", box[0]["error"])

    def test_callable_slot_runs_the_function_with_its_argument(self):
        box = []
        self.dispatcher._do_execute_callable(lambda x: {"got": x}, 7, box)
        self.assertEqual(box, [{"got": 7}])

    def test_callable_slot_turns_an_exception_into_an_error_dict(self):
        def bad(_):
            raise ValueError("nope")

        box = []
        self.dispatcher._do_execute_callable(bad, None, box)
        self.assertEqual(box, [{"error": "nope"}])

    def test_the_dispatcher_keeps_the_agent_it_was_given(self):
        self.assertIs(self.dispatcher.agent, self.agent)

    def test_the_container_identity_is_preserved(self):
        # The cross-thread bug fixed in this module was a COPY of the list being filled; the slot must mutate the object it was handed.
        self.agent._real_execute_tool.return_value = {"ok": 1}
        box = []
        keep = box
        self.dispatcher._do_execute("t", {}, box)
        self.assertIs(box, keep)
        self.assertEqual(keep, [{"ok": 1}])


if __name__ == "__main__":
    unittest.main()
