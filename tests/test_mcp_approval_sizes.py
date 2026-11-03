"""PLAN-055 gap D, option 1 (owner's go-ahead 2026-11-03): the dialog that asks a person to approve an MCP write also says how big the input layers are.
A geoprocessing write runs as one synchronous Processing call on the QGIS main thread, so on a large layer QGIS stops responding until it ends, with no
Stop. The person cannot weigh that without the size. Pure parts here; the live lookup against a real project is tests/test_mcp_server_live.py."""
import unittest
from unittest import mock

from cartogen_ai.core.agent import mcp_policy, mcp_server


class TestLayerNameCandidates(unittest.TestCase):
    def test_strings_and_lists_of_strings_in_order_without_repeats(self):
        args = {"layer_name": "roads", "layers": ["clinics", "roads", "zones"], "distance": 500, "output_name": "roads", "flag": True}
        self.assertEqual(mcp_policy.layer_name_candidates(args), ["roads", "clinics", "zones"])

    def test_empty_blank_and_non_text_values_are_ignored(self):
        self.assertEqual(mcp_policy.layer_name_candidates({"a": "", "b": "  ", "c": None, "d": 3, "e": ["", 4]}), [])

    def test_not_a_dict_is_empty(self):
        self.assertEqual(mcp_policy.layer_name_candidates(None), [])
        self.assertEqual(mcp_policy.layer_name_candidates("roads"), [])


class TestApprovalTextSizes(unittest.TestCase):
    def test_without_sizes_the_text_is_what_it_was(self):
        self.assertEqual(mcp_policy.approval_text("t", {"a": 1}, "CREATE"), mcp_policy.approval_text("t", {"a": 1}, "CREATE", sizes=None))
        self.assertNotIn("feature", mcp_policy.approval_text("t", {"a": 1}, "CREATE", sizes=[]))

    def test_sizes_are_listed_with_thousands_separators_and_a_singular(self):
        text = mcp_policy.approval_text("buffer_analysis", {"layer_name": "roads"}, "CREATE", sizes=[("roads", 12345), ("pin", 1)])
        self.assertIn("roads: 12,345 features", text)
        self.assertIn("pin: 1 feature", text)
        self.assertNotIn("1 features", text)

    def test_a_small_input_gets_no_warning(self):
        text = mcp_policy.approval_text("t", {}, "CREATE", sizes=[("a", mcp_policy.LARGE_INPUT_FEATURES - 1)])
        self.assertNotIn("stop responding", text)

    def test_a_large_input_says_qgis_may_stop_responding_and_cannot_be_stopped_from_here(self):
        text = mcp_policy.approval_text("t", {}, "CREATE", sizes=[("a", 3), ("big", mcp_policy.LARGE_INPUT_FEATURES)])
        self.assertIn("stop responding", text)
        self.assertIn("big", text)

    def test_an_unknown_size_is_said_not_guessed_and_not_called_large(self):
        text = mcp_policy.approval_text("t", {}, "CREATE", sizes=[("a", None), ("b", -1)])
        self.assertIn("a: size unknown", text)
        self.assertIn("b: size unknown", text)
        self.assertNotIn("stop responding", text)

    def test_the_question_to_the_person_is_still_last(self):
        text = mcp_policy.approval_text("t", {}, "CREATE", sizes=[("a", 5)])
        self.assertTrue(text.rstrip().endswith("the call is refused."))


class TestSizesReachTheDialog(unittest.TestCase):
    def run_it(self, name, approve, sizes_side_effect=None, sizes=None):
        from cartogen_ai.core.agent.tools.registry import TOOL_REGISTRY
        fake = mock.MagicMock(return_value={"success": True})
        patched = mock.patch.object(mcp_server, "layer_sizes", side_effect=sizes_side_effect) if sizes_side_effect else \
            mock.patch.object(mcp_server, "layer_sizes", return_value=sizes or [])
        with mock.patch.dict(TOOL_REGISTRY, {name: fake}), mock.patch.object(mcp_server, "egress_refusal", return_value=None), patched as lookup:
            result = mcp_server.run_allowed_tool(name, {"old_name": "a", "new_name": "b"}, approve=approve)
        return result, lookup

    def test_a_write_shows_the_sizes_it_looked_up(self):
        shown = []
        result, _ = self.run_it("rename_layer", lambda n, t: shown.append(t) or True, sizes=[("a", 70000)])
        self.assertTrue(result["success"])
        self.assertIn("a: 70,000 features", shown[0])
        self.assertIn("stop responding", shown[0])

    def test_a_failing_lookup_still_asks_and_still_works_without_sizes(self):
        shown = []
        result, _ = self.run_it("rename_layer", lambda n, t: shown.append(t) or True, sizes_side_effect=RuntimeError("no project"))
        self.assertTrue(result["success"])
        self.assertEqual(len(shown), 1)
        self.assertNotIn("feature", shown[0])

    def test_a_read_tool_does_no_lookup_and_asks_nobody(self):
        asked = []
        _result, lookup = self.run_it("get_layers", lambda n, t: asked.append(t) or True)
        self.assertEqual(asked, [])
        lookup.assert_not_called()


if __name__ == "__main__":
    unittest.main()
