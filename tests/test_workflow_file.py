"""PLAN-048 stage 1: the shareable workflow file's validator and the reviewed tool lists. Pure; no QGIS. Every rule in workflow_file.py has a test here."""
import copy
import inspect
import json
import os
import unittest

from cartogen_ai.core import tool_operations
from cartogen_ai.core.agent import mcp_policy, source_record, tool_lists, workflow_file as wf
import cartogen_ai.core.agent.agent_orchestrator  # noqa: F401  (registers every tool)
from cartogen_ai.core.agent.tools.registry import TOOL_REGISTRY, TOOLS_SCHEMA

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMAS = wf.schemas_from(TOOLS_SCHEMA)
GOOD = {
    "format": "cartogen-workflow", "version": 1, "name": "Reach", "description": "d",
    "roles": {"facilities": {"kind": "vector", "geometry": "point"}},
    "steps": [
        {"tool": "buffer_analysis", "arguments": {"layer_name": "@facilities", "distance": 5000, "output_name": "reach"}},
        {"tool": "get_feature_count", "arguments": {"layer_name": "$prev.layer_name"}},
    ],
}


def check(doc):
    return wf.validate(doc, SCHEMAS, tool_operations.get_tool_operation_type)


def with_step(**changes):
    doc = copy.deepcopy(GOOD)
    doc["steps"][0].update(changes)
    return doc


class TestLists(unittest.TestCase):
    def test_every_listed_tool_exists_and_none_is_a_delete_or_has_its_own_confirmation(self):
        problems = []
        for name in sorted(tool_lists.FILE_TOOLS):
            func = TOOL_REGISTRY.get(name)
            if func is None:
                problems.append(f"{name}: not a tool")
                continue
            if tool_operations.get_tool_operation_type(name) == "DELETE":
                problems.append(f"{name}: DELETE")
            if "confirmed" in inspect.signature(func).parameters:
                problems.append(f"{name}: has its own confirmed step")
        self.assertEqual(problems, [])

    def test_mcp_and_files_share_one_list(self):
        self.assertIs(mcp_policy.READ_TOOLS, tool_lists.READ_TOOLS)
        self.assertIs(mcp_policy.WRITE_TOOLS, tool_lists.WRITE_TOOLS)
        self.assertTrue(tool_lists.READ_TOOLS <= tool_lists.FILE_TOOLS and tool_lists.WRITE_TOOLS <= tool_lists.FILE_TOOLS)

    def test_fetch_tools_are_files_only_and_match_the_source_table(self):
        self.assertEqual(tool_lists.FETCH_TOOLS, frozenset(source_record.SOURCES))
        self.assertFalse(tool_lists.FETCH_TOOLS & (mcp_policy.READ_TOOLS | mcp_policy.WRITE_TOOLS), "fetch tools are not offered over MCP")

    def test_dangerous_tools_are_not_on_the_file_list(self):
        for name in ("execute_pyqgis_script", "run_steps", "create_plan", "add_layer_from_path", "add_web_layer", "set_attribute_value", "add_field",
                     "store_global_memory", "set_layer_sensitivity", "run_allowlisted_processing_algorithm", "save_workflow_preset"):
            self.assertNotIn(name, tool_lists.FILE_TOOLS)


class TestAccepts(unittest.TestCase):
    def test_a_good_file_is_accepted_normalised_and_fingerprinted(self):
        doc, problems, warnings = check(GOOD)
        self.assertEqual((problems, warnings), ([], []))
        self.assertEqual(len(doc["fingerprint"]), 64)
        again, _p, _w = check(json.loads(json.dumps(GOOD)))
        self.assertEqual(again["fingerprint"], doc["fingerprint"])

    def test_the_fingerprint_changes_when_a_step_changes(self):
        other = copy.deepcopy(GOOD)
        other["steps"][0]["arguments"]["distance"] = 6000
        self.assertNotEqual(check(GOOD)[0]["fingerprint"], check(other)[0]["fingerprint"])

    def test_text_and_bytes_are_accepted_and_a_preset_args_key_is_converted_with_a_warning(self):
        doc = with_step()
        doc["steps"][0]["args"] = doc["steps"][0].pop("arguments")
        parsed, problems, warnings = check(json.dumps(doc).encode("utf-8"))
        self.assertEqual(problems, [])
        self.assertIn("arguments", parsed["steps"][0])
        self.assertTrue(any("args" in w for w in warnings))

    def test_the_worked_example_file_is_valid(self):
        with open(os.path.join(ROOT, "docs", "examples", "workflows", "access-to-care.cgworkflow.json"), encoding="utf-8") as fh:
            doc, problems, _w = check(fh.read())
        self.assertEqual(problems, [])
        self.assertEqual([s["tool"] for s in doc["steps"]], ["fetch_geoboundaries", "buffer_analysis", "spatial_join"])

    def test_describe_steps_lists_tool_kind_and_arguments(self):
        doc = check(GOOD)[0]
        rows = wf.describe_steps(doc, tool_operations.get_tool_operation_type)
        self.assertEqual([r["tool"] for r in rows], ["buffer_analysis", "get_feature_count"])
        self.assertIn("@facilities", rows[0]["arguments"])
        self.assertEqual(rows[1]["operation"], "READ")


class TestRefusesTheWholeFile(unittest.TestCase):
    def refused(self, source, part):
        doc, problems, _w = check(source)
        self.assertIsNone(doc)
        self.assertTrue(any(part in p for p in problems), problems)

    def test_not_json_not_an_object_wrong_format_wrong_version(self):
        self.refused("{nope", "not valid JSON")
        self.refused(b"\xff\xfe", "not valid JSON")
        self.refused("[1]", "JSON object")
        self.refused({"format": "other", "version": 1}, "not a Cartogen workflow")
        self.refused({**GOOD, "version": 2}, "Update the plugin")
        self.refused({**GOOD, "version": "1"}, "version")
        self.refused({**GOOD, "version": 0}, "Unknown version")

    def test_oversize(self):
        self.refused(json.dumps({**GOOD, "description": "x" * (wf.MAX_BYTES + 10)}), "the limit is")

    def test_bad_header_roles_and_lists(self):
        self.refused({**GOOD, "name": ""}, "`name`")
        self.refused({**GOOD, "roles": {"Bad-Name": {}}}, "role name")
        self.refused({**GOOD, "roles": {"a": {"kind": "table"}}}, "kind")
        self.refused({**GOOD, "limitations": "text"}, "limitations")
        self.refused({**GOOD, "data_sources": [{"name": "x", "url": "ftp://x"}]}, "http")
        self.refused({**GOOD, "steps": []}, "non-empty")
        self.refused({**GOOD, "steps": [GOOD["steps"][1]] * (wf.MAX_STEPS + 1)}, "At most")


class TestRefusesAStep(unittest.TestCase):
    def refused(self, doc, part):
        parsed, problems, _w = check(doc)
        self.assertIsNone(parsed)
        self.assertTrue(any(part in p for p in problems), problems)
        return problems

    def test_a_tool_off_the_list_a_delete_a_batch_tool_and_an_unknown_tool(self):
        self.refused(with_step(tool="execute_pyqgis_script", arguments={"script": "1"}), "not on the list")
        self.refused(with_step(tool="run_steps", arguments={}), "cannot be used")
        self.refused(with_step(tool="no_such_tool", arguments={}), "not a tool in this version")
        deleting = next((t for t in SCHEMAS if tool_operations.get_tool_operation_type(t) == "DELETE"), None)
        self.assertIsNotNone(deleting)
        self.refused(with_step(tool=deleting, arguments={}), "deletes or replaces project state")

    def test_confirmed_is_a_refusal_not_a_silent_drop(self):
        self.refused(with_step(arguments={**GOOD["steps"][0]["arguments"], "confirmed": True}), "cannot approve")
        self.refused(with_step(arguments={**GOOD["steps"][0]["arguments"], "output_name": {"confirmed": True}}), "cannot approve")

    def test_unknown_missing_and_wrong_typed_arguments(self):
        self.refused(with_step(arguments={"layer_name": "@facilities", "distance": 5, "colour": "red"}), "not an argument")
        self.refused(with_step(arguments={"layer_name": "@facilities"}), "missing required")
        self.refused(with_step(arguments={"layer_name": "@facilities", "distance": "far"}), "should be of type")
        self.refused(with_step(arguments={"layer_name": "@facilities", "distance": True}), "should be of type")
        self.refused(with_step(arguments=[1]), "must be an object")

    def test_paths_urls_and_long_strings_are_refused(self):
        for value in ("/home/me/x.gpkg", "C:\\data\\x.shp", "~/x", "../x", "https://example.org/x", "file:x"):
            self.refused(with_step(arguments={**GOOD["steps"][0]["arguments"], "output_name": value}), "file path or web address")
        self.refused(with_step(arguments={**GOOD["steps"][0]["arguments"], "output_name": "x" * 501}), "characters")

    def test_references_must_point_back_and_roles_must_be_declared(self):
        doc = copy.deepcopy(GOOD)
        doc["steps"][1]["arguments"]["layer_name"] = "$2.layer_name"
        self.refused(doc, "EARLIER")
        doc["steps"][1]["arguments"]["layer_name"] = "$prev.layer_name"
        doc["steps"].insert(0, {"tool": "get_feature_count", "arguments": {"layer_name": "$prev.layer_name"}})
        self.refused(doc, "EARLIER")
        self.refused(with_step(arguments={"layer_name": "@ghost", "distance": 5}), "not a role declared")
        self.refused(with_step(arguments={"layer_name": "$oops", "distance": 5}), "not a valid reference")

    def test_a_role_cannot_stand_where_a_number_is_wanted(self):
        self.refused(with_step(arguments={"layer_name": "@facilities", "distance": "@facilities"}), "role")

    def test_both_args_and_arguments_is_refused(self):
        self.refused(with_step(args={}), "both")

    def test_a_fetch_tool_is_accepted_as_a_step(self):
        doc = copy.deepcopy(GOOD)
        doc["steps"].insert(0, {"tool": "fetch_geoboundaries", "arguments": {"iso3": "YEM", "admin_level": "ADM2"}})
        self.assertEqual(check(doc)[1], [])

    def test_every_problem_names_its_step(self):
        problems = self.refused(with_step(tool="execute_pyqgis_script", arguments={}), "Step 1")
        self.assertTrue(all(p.startswith("Step 1") for p in problems))


class TestWarnings(unittest.TestCase):
    def test_an_unused_role_and_unknown_keys_warn_but_do_not_refuse(self):
        doc = copy.deepcopy(GOOD)
        doc["roles"]["spare"] = {"kind": "raster"}
        doc["extra"] = 1
        doc["steps"][0]["colour"] = "red"
        parsed, problems, warnings = check(doc)
        self.assertEqual(problems, [])
        self.assertTrue(parsed)
        joined = " ".join(warnings)
        for part in ("spare", "extra", "colour"):
            self.assertIn(part, joined)

    def test_garbage_never_raises(self):
        for junk in (None, 5, "", "null", {}, {"format": "cartogen-workflow", "version": 1}, {"format": "cartogen-workflow", "version": 1, "steps": [None, 3, {}]}):
            doc, problems, _w = check(junk)
            self.assertIsNone(doc)
            self.assertTrue(problems)


if __name__ == "__main__":
    unittest.main()
