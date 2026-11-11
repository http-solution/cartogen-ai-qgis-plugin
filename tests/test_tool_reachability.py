"""PLAN-023 R1-6: the reachability ratchet. A tool the model can call but that no task and no persona names is a tool the task directive and the persona re-rank will never suggest; it can only be found by name or with find_tools. New tools must therefore be named by a task or a persona file, or be added to the frozen exception list in tests/fixtures/tool_reachability_exceptions.json
(which may only shrink: a listed tool that becomes reachable must be taken off the list)."""
import json
import unittest
from pathlib import Path

from cartogen_ai.core import personas as pp
from cartogen_ai.core.agent import task_register as reg
from cartogen_ai.core.agent.tools.registry import TOOL_REGISTRY

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "tool_reachability_exceptions.json"


def _reachable():
    named = {t for task in reg.load() for t in task["tools"]}
    for pid in pp.ids():
        named |= pp.tools_named(pp.get(pid))
    return named


class TestReachabilityRatchet(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.exceptions = json.loads(FIXTURE.read_text(encoding="utf-8"))["tools"]
        cls.reachable = _reachable()

    def test_the_exception_list_is_sorted_unique_and_only_names_registered_tools(self):
        self.assertEqual(self.exceptions, sorted(set(self.exceptions)))
        self.assertEqual([t for t in self.exceptions if t not in TOOL_REGISTRY], [], "a listed tool no longer exists: delete it from the list")

    def test_every_tool_is_in_a_task_or_a_persona_or_on_the_frozen_list(self):
        missing = sorted(set(TOOL_REGISTRY) - self.reachable - set(self.exceptions))
        self.assertEqual(missing, [], "these tools are in no task and no persona: add each to a task in tools/add_persona_tasks.py or to a persona file's workflows or tool_aliases "
                                      "(do not add to the exception list; it may only shrink)")

    def test_a_listed_tool_that_became_reachable_must_leave_the_list(self):
        now_reachable = sorted(set(self.exceptions) & self.reachable)
        self.assertEqual(now_reachable, [], "these are now named by a task or persona: delete them from tests/fixtures/tool_reachability_exceptions.json (the ratchet only tightens)")

    def test_the_check_can_fail(self):
        # shown on a synthetic registry so a ratchet that passes everything cannot slip through
        registry = set(TOOL_REGISTRY) | {"a_brand_new_tool"}
        self.assertEqual(sorted(registry - self.reachable - set(self.exceptions)), ["a_brand_new_tool"])
        self.assertEqual(sorted(set(self.exceptions) & (self.reachable | {self.exceptions[0]})), [self.exceptions[0]])


if __name__ == "__main__":
    unittest.main()
