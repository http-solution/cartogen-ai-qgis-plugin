# -*- coding: utf-8 -*-
"""GitHub #149 / #150 (audit F13, F14): the egress gate must see layers named inside SQL and in list/nested arguments, treat the
monitoring workflow as whole-project, and the lineage helpers must record the same sources and the layers a result created.
Pure functions only; the QGIS-side tagging in the orchestrator is not exercised here."""
import unittest

from cartogen_ai.core.agent.lineage import created_layer_names, derive_sources
from cartogen_ai.core.models import egress_gate as g

KNOWN = {"Clinics", "Roads", "Secret Patients", "out"}


class TestSqlLayerNames(unittest.TestCase):
    def test_bare_and_quoted_identifiers(self):
        self.assertEqual(g.sql_layer_names('SELECT * FROM clinics JOIN "Secret Patients" ON 1', KNOWN),
                         {"Clinics", "Secret Patients"})

    def test_no_match_and_non_string(self):
        self.assertEqual(g.sql_layer_names("SELECT 1", KNOWN), set())
        self.assertEqual(g.sql_layer_names(None, KNOWN), set())


class TestArgumentLayerNames(unittest.TestCase):
    def test_list_and_nested_arguments_are_seen(self):
        names, unresolved = g.argument_layer_names("merge", {"layers": ["Clinics", "x"], "p": {"INPUT": "Roads"}}, KNOWN)
        self.assertEqual(names, {"Clinics", "Roads"})
        self.assertFalse(unresolved)

    def test_sql_tool_uses_query_text(self):
        names, _ = g.argument_layer_names("execute_read_only_sql", {"sql_query": "select * from Roads"}, KNOWN)
        self.assertEqual(names, {"Roads"})

    def test_local_sql_naming_nothing_assumes_whole_project(self):
        names, unresolved = g.argument_layer_names("execute_read_only_sql", {"sql_query": "select 1"}, KNOWN)
        self.assertEqual(names, set(KNOWN))
        self.assertTrue(unresolved)

    def test_database_sql_is_not_a_project_layer_read(self):
        names, unresolved = g.argument_layer_names(
            "execute_read_only_sql", {"sql_query": "select 1", "connection_name": "pg"}, KNOWN)
        self.assertEqual(names, set())
        self.assertFalse(unresolved)


class TestGateBehaviour(unittest.TestCase):
    def _eval(self, tool, args):
        return g.evaluate(mode=g.MODE_ENFORCE, provider_is_local=False, tool_name=tool, arguments=args,
                          project_layer_names=KNOWN,
                          get_level=lambda n: "RESTRICTED" if n == "Secret Patients" else "PUBLIC",
                          get_sources=lambda n: [], strict=False)

    def test_sql_over_a_protected_layer_is_blocked(self):
        d = self._eval("execute_read_only_sql", {"sql_query": 'select * from "Secret Patients"'})
        self.assertEqual(d["action"], "block")
        self.assertIn("Secret Patients", d["layers"])

    def test_sql_over_an_open_layer_proceeds(self):
        self.assertIsNone(self._eval("execute_read_only_sql", {"sql_query": "select * from Roads"}))

    def test_workflow_tool_is_whole_project(self):
        d = self._eval("run_monitoring_workflow", {})
        self.assertEqual(d["action"], "block")

    def test_scheduling_a_workflow_is_whole_project_too(self):
        # #149: each scheduled tick posts into the chat the model reads next, so scheduling is the egress decision.
        d = self._eval("schedule_recurring_workflow", {"preset_name": "weekly", "interval_minutes": 5})
        self.assertEqual(d["action"], "block")

    def test_stopping_or_listing_schedules_is_not_gated(self):
        self.assertIsNone(self._eval("stop_recurring_workflow", {"preset_name": "weekly"}))
        self.assertIsNone(self._eval("list_scheduled_workflows", {}))


class TestLineageHelpers(unittest.TestCase):
    def test_derive_sources_reads_lists_and_sql(self):
        self.assertEqual(derive_sources("merge", {"layer_names_list": ["Roads", "Clinics"]}, KNOWN), ["Clinics", "Roads"])
        self.assertEqual(derive_sources("execute_read_only_sql", {"sql_query": "select * from Roads"}, KNOWN), ["Roads"])

    def test_created_layers_from_several_keys_excluding_sources(self):
        res = {"success": True, "layer_name": "Roads", "layers_created": ["out", "nope"], "count": 3}
        self.assertEqual(created_layer_names(res, ["Roads"], KNOWN), ["out"])

    def test_non_dict_result(self):
        self.assertEqual(created_layer_names("x", [], KNOWN), [])


if __name__ == "__main__":
    unittest.main()
