"""PLAN-048 stage 3, the parts that need no dialog: mapping roles to layers, starting part-way, compatibility, the chat message, and the model-free
runner (CartogenAi.run_workflow_steps) with the tool dispatcher stubbed -- so this proves the loop and the context handling, not any real tool."""
import copy
import json
import unittest
from unittest.mock import MagicMock, patch

from cartogen_ai.core import tool_operations
from cartogen_ai.core.agent import workflow_file as wf, workflow_import as wi
import cartogen_ai.core.agent.agent_orchestrator as agent_mod
from cartogen_ai.core.agent.tools.registry import TOOLS_SCHEMA
from tests.test_agent_runner import _make_bare_agent

SCHEMAS = wf.schemas_from(TOOLS_SCHEMA)
OP = tool_operations.get_tool_operation_type
DOC_SOURCE = {
    "format": "cartogen-workflow", "version": 1, "name": "Reach", "description": "d",
    "roles": {"facilities": {"kind": "vector", "geometry": "point", "fields": ["name"]}, "districts": {"kind": "vector", "geometry": "polygon"}},
    "steps": [
        {"tool": "buffer_analysis", "arguments": {"layer_name": "@facilities", "distance": 5000, "output_name": "reach"}},
        {"tool": "spatial_join", "arguments": {"target_layer": "@districts", "join_layer": "$prev.layer_name"}},
        {"tool": "get_feature_count", "arguments": {"layer_name": "$2.layer_name"}},
    ],
}
MAPPING = {"facilities": "Clinics", "districts": "Admin2"}


def document():
    doc, problems, _w = wf.validate(copy.deepcopy(DOC_SOURCE), SCHEMAS, OP)
    assert not problems, problems
    return doc


class TestApplyMapping(unittest.TestCase):
    def test_roles_become_layer_names_and_references_are_left_for_the_runner(self):
        steps, problems = wi.apply_mapping(document(), MAPPING)
        self.assertEqual(problems, [])
        self.assertEqual(steps[0], {"tool": "buffer_analysis", "arguments": {"layer_name": "Clinics", "distance": 5000, "output_name": "reach"}})
        self.assertEqual(steps[1]["arguments"], {"target_layer": "Admin2", "join_layer": "$prev.layer_name"})
        self.assertEqual(steps[2]["arguments"], {"layer_name": "$2.layer_name"})

    def test_the_document_itself_is_not_changed(self):
        doc = document()
        before = json.dumps(doc, sort_keys=True)
        wi.apply_mapping(doc, MAPPING)
        self.assertEqual(json.dumps(doc, sort_keys=True), before)

    def test_an_unmapped_blank_or_missing_layer_is_a_problem(self):
        self.assertIn("role 'districts'", wi.apply_mapping(document(), {"facilities": "Clinics"})[1][0])
        self.assertTrue(wi.apply_mapping(document(), {"facilities": "Clinics", "districts": "  "})[1])
        steps, problems = wi.apply_mapping(document(), MAPPING, available={"Clinics"})
        self.assertEqual(steps, [])
        self.assertIn("'Admin2'", problems[0])

    def test_a_layer_whose_name_looks_like_a_role_is_not_substituted_twice(self):
        steps, _p = wi.apply_mapping(document(), {"facilities": "@districts", "districts": "Admin2"})
        self.assertEqual(steps[0]["arguments"]["layer_name"], "@districts")

    def test_starting_part_way_renumbers_references_and_only_needs_the_roles_still_used(self):
        steps, problems = wi.apply_mapping(document(), {"districts": "Admin2"}, start_at=2)
        self.assertEqual(problems, [])
        self.assertEqual(len(steps), 2)
        self.assertEqual(steps[1]["arguments"], {"layer_name": "$1.layer_name"})

    def test_a_reference_to_a_step_before_the_start_is_refused(self):
        doc = document()
        _s, problems = wi.apply_mapping(doc, MAPPING, start_at=3)
        self.assertTrue(any("before step 3" in p for p in problems), problems)

    def test_a_bad_start_is_refused(self):
        for bad in (0, 4, "2", True, None):
            self.assertTrue(wi.apply_mapping(document(), MAPPING, start_at=bad)[1], bad)

    def test_used_roles_in_order(self):
        self.assertEqual(wi.used_roles(document()["steps"]), ["facilities", "districts"])


class TestCompatibility(unittest.TestCase):
    def info(self, table):
        return table.get

    def test_the_wrong_kind_is_a_problem_and_the_wrong_geometry_or_missing_fields_are_warnings(self):
        table = {"Clinics": {"kind": "raster"}, "Admin2": {"kind": "vector", "geometry": "point", "fields": []}}
        problems, warnings = wi.compatibility(document(), MAPPING, self.info(table))
        self.assertTrue(any("needs a vector" in p for p in problems))
        table["Clinics"] = {"kind": "vector", "geometry": "point", "fields": ["id"]}
        problems, warnings = wi.compatibility(document(), MAPPING, self.info(table))
        self.assertEqual(problems, [])
        self.assertTrue(any("polygon" in w for w in warnings))
        self.assertTrue(any("no field" in w and "name" in w for w in warnings))

    def test_a_missing_layer_is_a_problem_and_an_unchosen_role_is_skipped(self):
        problems, _w = wi.compatibility(document(), {"facilities": "Gone"}, self.info({}))
        self.assertTrue(any("not in the project" in p for p in problems))
        self.assertEqual(wi.compatibility(document(), {}, self.info({})), ([], []))


class TestShownToThePerson(unittest.TestCase):
    def test_rows_show_the_chosen_layer_or_the_role_until_chosen(self):
        rows = wi.step_rows(document(), {"facilities": "Clinics"}, OP)
        self.assertEqual([r["n"] for r in rows], [1, 2, 3])
        self.assertIn("Clinics", rows[0]["arguments"])
        self.assertIn("@districts", rows[1]["arguments"])
        self.assertEqual(rows[0]["operation"], "CREATE")

    def test_result_text_for_each_ending(self):
        doc = document()
        self.assertIn("finished", wi.result_text(doc, {"success": True, "total": 3, "completed": 3}))
        self.assertIn("was not started", wi.result_text(doc, {"error": "bad", "completed": 0}))
        stopped = {"success": False, "completed": 1, "total": 3, "stopped_at_step": 2, "stopped_because": "boom", "error": "boom", "not_run": "Steps 2-3 were NOT run."}
        text = wi.result_text(doc, stopped)
        self.assertIn("stopped at step 2 of 3", text)
        self.assertIn("boom", text)
        waiting = {**stopped, "status": "PREVIEW_REQUIRED", "stopped_because": "waiting"}
        self.assertIn("start at step 3", wi.result_text(doc, waiting))
        self.assertIn("step 3 of 3", wi.result_text(doc, {**stopped, "stopped_at_step": 1}, start_at=3))
        self.assertIn("did not return", wi.result_text(doc, None))


class TestRunner(unittest.TestCase):
    def run_it(self, execute, start_at=1, mapping=None, doc=None):
        agent = _make_bare_agent(MagicMock())
        ran, seen_context = [], []
        doc = doc or document()
        steps, problems = wi.apply_mapping(doc, mapping or MAPPING, start_at)
        self.assertEqual(problems, [])

        def fake(self_, name, args):
            args = json.loads(args) if isinstance(args, str) else args
            ran.append((name, args))
            seen_context.append(getattr(self_, "_workflow_context", None))
            return execute(name, args)

        facts = {"Clinics": {"kind": "vector", "geographic": False}, "Admin2": {"kind": "vector", "geographic": False}}
        with patch.object(agent_mod.CartogenAi, "_execute_tool", fake), \
             patch.object(agent_mod.CartogenAi, "_project_layer_facts", staticmethod(lambda _=None: facts)):
            result = agent.run_workflow_steps(steps, {"name": doc["name"], "fingerprint": doc["fingerprint"]}, should_stop=None)
        return result, ran, seen_context, agent

    def test_the_steps_run_in_order_with_references_resolved_and_no_model_call(self):
        result, ran, _ctx, agent = self.run_it(lambda n, a: {"success": True, "layer_name": n + "_out"})
        self.assertTrue(result["success"], result)
        self.assertEqual([r[0] for r in ran], ["buffer_analysis", "spatial_join", "get_feature_count"])
        self.assertEqual(ran[1][1], {"target_layer": "Admin2", "join_layer": "buffer_analysis_out"})
        self.assertEqual(ran[2][1], {"layer_name": "spatial_join_out"})
        agent.client.complete.assert_not_called()

    def test_the_workflow_identity_is_visible_to_the_tools_and_cleared_afterwards(self):
        doc = document()
        _r, _ran, ctx, agent = self.run_it(lambda n, a: {"success": True, "layer_name": "x"}, doc=doc)
        self.assertEqual(ctx[0], {"workflow": {"name": "Reach", "fingerprint": doc["fingerprint"]}})
        self.assertIsNone(agent._workflow_context)

    def test_it_stops_at_the_first_error_and_says_what_did_not_run(self):
        result, ran, _c, _a = self.run_it(lambda n, a: {"error": "bad layer"} if n == "spatial_join" else {"success": True, "layer_name": "x"})
        self.assertEqual([r[0] for r in ran], ["buffer_analysis", "spatial_join"])
        self.assertFalse(result["success"])
        self.assertEqual(result["stopped_at_step"], 2)
        self.assertIn("NOT run", result["not_run"])

    def test_a_step_waiting_for_confirmation_stops_the_run(self):
        result, ran, _c, _a = self.run_it(lambda n, a: {"status": "PREVIEW_REQUIRED", "requires_confirmation": True} if n == "spatial_join"
                                           else {"success": True, "layer_name": "x"})
        self.assertEqual(result["status"], "PREVIEW_REQUIRED")
        self.assertEqual(len(ran), 2)

    def test_a_stop_request_ends_the_run_before_the_next_step(self):
        agent = _make_bare_agent(MagicMock())
        steps, _p = wi.apply_mapping(document(), MAPPING)
        calls = []
        with patch.object(agent_mod.CartogenAi, "_execute_tool", lambda s, n, a: calls.append(n) or {"success": True, "layer_name": "x"}), \
             patch.object(agent_mod.CartogenAi, "_project_layer_facts", staticmethod(lambda _=None: {"Clinics": {"kind": "vector"}, "Admin2": {"kind": "vector"}})):
            result = agent.run_workflow_steps(steps, None, should_stop=lambda: True)
        self.assertEqual(calls, [])
        self.assertFalse(result["success"])
        self.assertIn("Stopped", result["stopped_because"])

    def test_a_file_may_have_more_steps_than_the_models_own_run_steps_allows(self):
        doc = copy.deepcopy(DOC_SOURCE)
        doc["roles"] = {"facilities": {"kind": "vector"}}
        doc["steps"] = [{"tool": "buffer_analysis", "arguments": {"layer_name": "@facilities", "distance": 100 * (n + 1), "output_name": f"r{n}"}}
                        for n in range(12)]            # distinct calls: three identical ones in a row would (rightly) trip the loop guard
        parsed, problems, _w = wf.validate(doc, SCHEMAS, OP)
        self.assertEqual(problems, [])
        result, ran, _c, _a = self.run_it(lambda n, a: {"success": True, "layer_name": "x"}, mapping={"facilities": "Clinics"}, doc=parsed)
        self.assertTrue(result["success"], result)
        self.assertEqual(len(ran), 12)

    def test_a_layer_that_is_not_in_the_project_is_refused_before_any_step_runs(self):
        agent = _make_bare_agent(MagicMock())
        steps, _p = wi.apply_mapping(document(), MAPPING)
        calls = []
        with patch.object(agent_mod.CartogenAi, "_execute_tool", lambda s, n, a: calls.append(n) or {"success": True}), \
             patch.object(agent_mod.CartogenAi, "_project_layer_facts", staticmethod(lambda _=None: {"Other": {"kind": "vector"}})):
            result = agent.run_workflow_steps(steps, None)
        self.assertEqual(calls, [])
        self.assertIn("not in the project", result["error"])


class TestLineageExtra(unittest.TestCase):
    def test_the_lineage_entry_accepts_extra_fields_but_never_overrides_its_own(self):
        import inspect
        from cartogen_ai.core.agent import lineage
        self.assertIn("extra", inspect.signature(lineage.tag_layer_lineage).parameters)
        src = inspect.getsource(lineage.tag_layer_lineage)
        self.assertIn("if k not in entry", src)


if __name__ == "__main__":
    unittest.main()
