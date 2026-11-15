"""#145/#146, rc48 evidence t35: a script that edits a file-backed layer must not come back as a success (pure part, no QGIS)."""
import unittest

from cartogen_ai.core.agent.services.script_isolation import script_reply

PROBLEM = "your changes to the layer 'smoke_points' were NOT applied: it is stored in a file or database"


class TestScriptReply(unittest.TestCase):
    def test_nothing_applied_and_a_problem_is_a_failure_that_says_so(self):
        reply = script_reply({"new_name": "Changed"}, [], [], [PROBLEM])
        self.assertFalse(reply["success"])
        self.assertFalse(reply["applied"])
        self.assertIn("NOT applied", reply["error"])
        self.assertIn("smoke_points", reply["error"])
        self.assertEqual(reply["script_result"], {"new_name": "Changed"})

    def test_part_applied_part_not_is_a_success_flagged_partial(self):
        reply = script_reply({}, ["script_points"], [], [PROBLEM])
        self.assertTrue(reply["success"])
        self.assertTrue(reply["partially_applied"])
        self.assertIn("could not be applied", reply["warning"])
        self.assertIn("temporary", reply["note"])

    def test_a_script_that_only_reads_is_untouched(self):
        self.assertEqual(script_reply({"n": 5}, [], [], []), {"success": True, "result": {"n": 5}})

    def test_a_new_layer_is_flagged_temporary(self):
        reply = script_reply({}, ["script_points"], [], [])
        self.assertTrue(reply["success"])
        self.assertIn("temporary", reply["note"])
        self.assertNotIn("partially_applied", reply)


class TestBlockedImportHint(unittest.TestCase):
    def test_a_blocked_module_names_what_a_script_can_do_instead(self):
        from cartogen_ai.core.agent.tools.system_tools import _validate_script_safety
        message = _validate_script_safety("import os\ndef run():\n    return 1\n")
        self.assertIn("Blocked import 'os'", message)
        self.assertIn("qgis.core", message)
        self.assertIn("export_layer", message)

    def test_a_clean_script_passes(self):
        from cartogen_ai.core.agent.tools.system_tools import _validate_script_safety
        self.assertIsNone(_validate_script_safety("def run():\n    return 1\n"))


if __name__ == "__main__":
    unittest.main()
