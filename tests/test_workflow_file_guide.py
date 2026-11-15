"""PLAN-048 stage 4: the user guide for workflow files may not drift from the code. It must list every tool a file may use, state the real limits, and its
example file must pass the validator."""
import json
import os
import re
import unittest

from cartogen_ai.core import tool_operations
from cartogen_ai.core.agent import tool_lists, workflow_file
import cartogen_ai.core.agent.agent_orchestrator  # noqa: F401  (registers every tool)
from cartogen_ai.core.agent.tools.registry import TOOLS_SCHEMA

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


GUIDE = read("docs", "WORKFLOW_FILES.md")


class TestGuide(unittest.TestCase):
    def test_every_tool_a_file_may_use_is_listed_and_no_other_tool_is(self):
        mentioned = {t for t in tool_lists.FILE_TOOLS if f"`{t}`" in GUIDE}
        self.assertEqual(sorted(tool_lists.FILE_TOOLS - mentioned), [], "the guide must name every tool a file may use")

    def test_the_limits_in_the_guide_are_the_real_ones(self):
        self.assertIn(f"**{workflow_file.MAX_STEPS} steps**", GUIDE)
        self.assertIn(f"**{workflow_file.MAX_BYTES // 1024} KB**", GUIDE)
        self.assertIn(f"at most {workflow_file.MAX_STRING} characters", GUIDE)

    def test_the_example_file_in_the_guide_is_valid(self):
        block = re.search(r"```json\n(.*?)\n```", GUIDE, re.S).group(1)
        doc, problems, _w = workflow_file.validate(json.loads(block), workflow_file.schemas_from(TOOLS_SCHEMA), tool_operations.get_tool_operation_type)
        self.assertEqual(problems, [])
        self.assertTrue(doc)

    def test_the_guide_says_it_has_not_been_tried_by_a_person_and_is_linked(self):
        self.assertIn("No person has yet tried it end to end", GUIDE)
        self.assertIn("WORKFLOW_FILES.md", read("README.md"))
        self.assertIn("WORKFLOW_FILES.md", read("docs", "README.md"))
        self.assertIn("WORKFLOW_FILES.md", read("docs", "USER_GUIDE.md"))

    def test_the_guide_does_not_claim_a_tool_opens_or_runs_a_file(self):
        self.assertIn("no tool can open or run a workflow file", GUIDE.lower())


if __name__ == "__main__":
    unittest.main()
