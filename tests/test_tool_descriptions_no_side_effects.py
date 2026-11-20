"""No registered tool description may tell the model to act without being asked. On 2026-11-20 the save_project description said to save "at the end of a task", and a 'run the model'
request wrote a project file nobody asked for (live run, row C12). This pins the wording that caused it, so a new description cannot bring it back."""
import re
import unittest

from cartogen_ai.core.agent.tools.registry import TOOLS_SCHEMA

# phrases that invite a side effect the user did not ask for
INVITING = re.compile(r"at the end of (a|the|your) (task|request|run|session)|so the user'?s work is persisted|as a checkpoint before|persist(s|ed)? (the|your|their) work|without being asked", re.I)


class TestDescriptions(unittest.TestCase):
    def test_no_description_invites_an_unrequested_side_effect(self):
        found = [(t["function"]["name"], m.group(0)) for t in TOOLS_SCHEMA for m in [INVITING.search(t["function"]["description"])] if m]
        self.assertEqual(found, [])

    def test_the_pattern_would_have_caught_the_save_project_wording_that_caused_it(self):
        old = "Use this as a checkpoint before a risky multi-step operation, or at the end of a task so the user's work is persisted."
        self.assertTrue(INVITING.search(old))


if __name__ == "__main__":
    unittest.main()
