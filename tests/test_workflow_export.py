"""PLAN-048 stage 2: building a shareable workflow file from recorded history. Pure; no QGIS. The round trip (export, then validate) is the main guard."""
import json
import unittest

from cartogen_ai.core import tool_operations
from cartogen_ai.core.agent import source_record, workflow_export as we, workflow_file as wf, workflow_report
import cartogen_ai.core.agent.agent_orchestrator  # noqa: F401  (registers every tool)
from cartogen_ai.core.agent.tools.registry import TOOLS_SCHEMA

SCHEMAS = wf.schemas_from(TOOLS_SCHEMA)
OP = tool_operations.get_tool_operation_type
LIN = workflow_report._lineage_key()


class FakeLayer:
    def __init__(self, props=None):
        self.props = dict(props or {})

    def customProperty(self, key, default=None):
        return self.props.get(key, default)


def history(*calls):
    return json.dumps([{"tool": t, "params": p, "sources": s, "source_ids": [], "timestamp": at} for t, p, s, at in calls])


def project():
    """Clinics (loaded) -> buffer -> reach; Districts fetched; a join of both -> joined. All recorded the way the orchestrator records them."""
    return {
        "Clinics": FakeLayer(),
        "Districts": FakeLayer({LIN: history(("fetch_geoboundaries", {"iso3": "YEM", "admin_level": "ADM2"}, [], "2026-11-02 10:00:00")),
                                source_record.PROPERTY_KEY: json.dumps([source_record.build("fetch_geoboundaries", {"iso3": "YEM"}, {"success": True}, now="2026-11-02")])}),
        "reach": FakeLayer({LIN: history(("buffer_analysis", {"layer_name": "Clinics", "distance": 5000, "output_name": "reach"}, ["Clinics"], "2026-11-02 10:05:00"))}),
        "joined": FakeLayer({LIN: history(("spatial_join", {"target_layer": "Districts", "join_layer": "reach"}, ["Districts", "reach"], "2026-11-02 10:10:00"))}),
    }


def export(layers, names=("joined",), info=None):
    return we.export_from_layers(list(names), layers.get, SCHEMAS, OP, "Reach by district", "d", info)


class TestRoundTrip(unittest.TestCase):
    def test_an_exported_history_validates_and_keeps_the_order(self):
        built = export(project())
        self.assertEqual(built["problems"], [])
        doc = built["document"]
        self.assertEqual([s["tool"] for s in doc["steps"]], ["fetch_geoboundaries", "buffer_analysis", "spatial_join"])
        again, problems, _w = wf.validate(json.loads(json.dumps(doc)), SCHEMAS, OP)
        self.assertEqual(problems, [])
        self.assertEqual(again["fingerprint"], built["fingerprint"])

    def test_a_layer_the_chain_did_not_make_becomes_a_role_and_made_layers_keep_their_names(self):
        built = export(project())
        steps = built["document"]["steps"]
        self.assertEqual(list(built["document"]["roles"]), ["clinics"])
        self.assertEqual(steps[1]["arguments"]["layer_name"], "@clinics")
        self.assertEqual(steps[2]["arguments"], {"target_layer": "Districts", "join_layer": "reach"})
        self.assertEqual(built["roles"], {"Clinics": "@clinics"})

    def test_role_details_come_from_layer_info_and_are_names_only(self):
        built = export(project(), info=lambda n: {"kind": "vector", "geometry": "point", "fields": ["name", "type"]} if n == "Clinics" else None)
        role = built["document"]["roles"]["clinics"]
        self.assertEqual((role["geometry"], role["fields"]), ("point", ["name", "type"]))

    def test_the_data_sources_travel_with_the_file(self):
        sources = export(project())["document"]["data_sources"]
        self.assertEqual(sources[0]["name"], "geoBoundaries (gbOpen)")
        self.assertIn("licence", sources[0])

    def test_the_file_says_it_was_not_rerun(self):
        self.assertTrue(any("not been run again" in t for t in export(project())["document"]["limitations"]))

    def test_no_path_no_confirmed_and_no_fingerprint_key_in_the_document(self):
        text = json.dumps(export(project())["document"])
        for bad in ("confirmed", "C:\\", "/home", "fingerprint"):
            self.assertNotIn(bad, text)


class TestWhatIsLeftOut(unittest.TestCase):
    def test_an_unlisted_tool_is_skipped_with_the_reason(self):
        layers = project()
        layers["reach"].props[LIN] = history(("buffer_analysis", {"layer_name": "Clinics", "distance": 5000, "output_name": "reach"}, ["Clinics"], "2026-11-02 10:05:00"),
                                             ("set_layer_sensitivity", {"layer_name": "reach", "level": "SENSITIVE"}, ["reach"], "2026-11-02 10:06:00"))
        built = export(layers)
        self.assertEqual([s["tool"] for s in built["skipped"]], ["set_layer_sensitivity"])
        self.assertIn("not on the list", built["skipped"][0]["why"])
        self.assertTrue(any("left out" in w for w in built["warnings"]))
        self.assertNotIn("set_layer_sensitivity", [s["tool"] for s in built["document"]["steps"]])

    def test_a_step_with_a_path_in_it_is_skipped_not_written(self):
        layers = project()
        layers["reach"].props[LIN] = history(("buffer_analysis", {"layer_name": "Clinics", "distance": 5000, "output_name": "C:\\Users\\me\\reach"}, ["Clinics"], "2026-11-02 10:05:00"))
        built = export(layers)
        self.assertIn("file path", built["skipped"][0]["why"])
        self.assertNotIn("Users", json.dumps(built["document"]))

    def test_a_layer_made_only_by_a_skipped_step_becomes_a_role(self):
        layers = project()
        layers["reach"].props[LIN] = history(("add_layer_from_path", {"path": "/data/x.gpkg"}, [], "2026-11-02 10:05:00"))
        built = export(layers)
        self.assertIn("reach", built["roles"])
        self.assertEqual(built["document"]["steps"][-1]["arguments"]["join_layer"], "@reach")

    def test_unadvertised_and_confirmed_keys_are_dropped(self):
        layers = project()
        layers["reach"].props[LIN] = history(("buffer_analysis", {"layer_name": "Clinics", "distance": 1, "output_name": "reach", "confirmed": True, "junk": 1}, ["Clinics"], "2026-11-02 10:05:00"))
        args = export(layers)["document"]["steps"][1]["arguments"]
        self.assertEqual(sorted(args), ["distance", "layer_name", "output_name"])

    def test_a_call_that_made_two_layers_is_one_step(self):
        layers = project()
        call = ("buffer_analysis", {"layer_name": "Clinics", "distance": 1, "output_name": "reach"}, ["Clinics"], "2026-11-02 10:05:00")
        layers["reach"].props[LIN] = history(call)
        layers["reach2"] = FakeLayer({LIN: history(call)})
        built = export(layers, names=("reach", "reach2"))
        self.assertEqual([s["tool"] for s in built["document"]["steps"]], ["buffer_analysis"])

    def test_a_layer_name_inside_longer_text_is_warned_about(self):
        layers = project()
        layers["reach"].props[LIN] = history(("buffer_analysis", {"layer_name": "Clinics", "distance": 1, "output_name": "Clinics reach"}, ["Clinics"], "2026-11-02 10:05:00"))
        self.assertTrue(any("longer text" in w for w in export(layers)["warnings"]))


class TestRefusals(unittest.TestCase):
    def test_nothing_exportable_is_a_clear_error(self):
        layers = {"x": FakeLayer({LIN: history(("set_layer_sensitivity", {"layer_name": "x", "level": "SENSITIVE"}, ["x"], "2026-11-02 10:00:00"))})}
        built = export(layers, names=("x",))
        self.assertIsNone(built["document"])
        self.assertIn("No step", built["problems"][0])

    def test_a_layer_with_no_history_and_a_missing_layer(self):
        self.assertIsNone(export({"a": FakeLayer()}, names=("a",))["document"])
        self.assertIn("None of the named layers", export({}, names=("gone",))["problems"][0])

    def test_more_than_twenty_steps_is_refused_with_advice(self):
        calls = [("get_feature_count", {"layer_name": "Clinics"}, ["Clinics"], f"2026-11-02 10:{n:02d}:00") for n in range(21)]
        built = export({"Clinics": FakeLayer(), "out": FakeLayer({LIN: history(*calls)})}, names=("out",))
        self.assertIsNone(built["document"])
        self.assertIn("narrower", built["problems"][0])


class TestRoleNames(unittest.TestCase):
    def test_names_are_valid_and_unique(self):
        taken = {}
        a = we._role_name("District Boundaries (ADM2)", taken)
        taken[a] = 1
        b = we._role_name("District boundaries  ADM2", taken)
        self.assertRegex(a, wf._ROLE.pattern)
        self.assertNotEqual(a, b)
        self.assertEqual(we._role_name("123", {}), "layer_123")
        self.assertEqual(we._role_name("???", {}), "layer")


if __name__ == "__main__":
    unittest.main()


class TestToolHelpers(unittest.TestCase):
    def test_the_tool_is_registered_as_a_file_write_and_is_not_offered_over_mcp_or_in_files(self):
        from cartogen_ai.core.agent import tool_lists
        from cartogen_ai.core.agent.tools.registry import TOOL_REGISTRY
        self.assertIn("export_workflow_file", TOOL_REGISTRY)
        self.assertEqual(OP("export_workflow_file"), "PUBLISH")
        self.assertNotIn("export_workflow_file", tool_lists.FILE_TOOLS)
        self.assertNotIn("export_workflow_file", tool_lists.READ_TOOLS | tool_lists.WRITE_TOOLS)

    def test_confirmed_is_not_advertised_so_the_model_cannot_approve_its_own_preview(self):
        props = SCHEMAS["export_workflow_file"]["properties"]
        self.assertNotIn("confirmed", props)

    def test_no_tool_opens_or_runs_a_workflow_file(self):
        from cartogen_ai.core.agent.tools.registry import TOOL_REGISTRY
        offenders = [n for n in TOOL_REGISTRY if "workflow_file" in n and not n.startswith("export_")]
        self.assertEqual(offenders, [])

    def test_the_path_gets_the_workflow_extension_and_the_text_is_what_is_written(self):
        from cartogen_ai.core.agent.tools import workflow_file_tools as wt
        doc = {"name": "My flow"}
        self.assertTrue(wt._target_path("/tmp/x/flow", doc).endswith("flow.cgworkflow.json"))
        self.assertTrue(wt._target_path("/tmp/x/flow.json", doc).endswith("flow.cgworkflow.json"))
        self.assertTrue(wt._target_path("/tmp/x/flow.cgworkflow.json", doc).endswith("flow.cgworkflow.json"))
        self.assertEqual(wt._target_path("/tmp/x/flow.cgworkflow.json", doc).count(".cgworkflow"), 1)
        self.assertEqual(json.loads(wt.file_text({"a": 1})), {"a": 1})

    def test_without_qgis_the_tool_says_so(self):
        from cartogen_ai.core.agent.tools import workflow_file_tools as wt
        if not wt.QGIS_AVAILABLE:
            self.assertEqual(wt.export_workflow_file(["x"]), {"error": "QGIS not available"})
