"""TR-1: 'Map ...' tasks start their tool order with a data-fetch tool that fits their subject.

Why: 279 of 302 'Map ...' tasks began "Prefer these tools, in order: add_layer_from_path, ...", which loads a file the user already has, so
the model was told to start there for "map hospitals and clinics" and never fetched anything (owner's Taiz run, 2026-11-01). The register's
tool order is derived by tools/derive_task_fetch.py; this test re-runs that derivation and pins the result."""
import importlib.util
import json
import os
import unittest

from cartogen_ai.core.agent.tools import TOOLS_SCHEMA

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _deriver():
    spec = importlib.util.spec_from_file_location("derive_task_fetch", os.path.join(ROOT, "tools", "derive_task_fetch.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestTaskFetchTools(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.deriver = _deriver()
        with open(cls.deriver.REGISTER, encoding="utf-8") as fh:
            cls.register = json.load(fh)
        cls.by_id = {e["id"]: e for e in cls.register}

    def test_the_committed_register_matches_the_derivation(self):
        self.assertEqual(self.register, self.deriver.derive(self.register),
                         "run python tools/derive_task_fetch.py and commit the register")

    def test_every_added_tool_is_a_registered_tool(self):
        registered = {t["function"]["name"] for t in TOOLS_SCHEMA}
        used = {tool for _p, tool in self.deriver._RULES}
        self.assertLessEqual(used, registered)

    def test_most_map_tasks_now_have_a_fetch_tool(self):
        maps = [e for e in self.register if e["text"].lower().startswith("map ")]
        with_fetch = [e for e in maps if any(t.startswith(self.deriver.FETCH_PREFIXES) for t in e["tools"])]
        self.assertGreaterEqual(len(maps), 300)
        self.assertGreaterEqual(len(with_fetch), 200, "was 23 of 302 before TR-1")

    def test_the_fetch_tool_is_only_ever_inserted_at_the_front(self):
        """Taking the derived first tool off every changed task gives a list the derivation would give the same first tool for again,
        and no tool appears twice."""
        derived = [e for e in self.register if e["text"].lower().startswith("map ") and e["tools"]
                   and self.deriver.fetch_tool_for({**e, "tools": e["tools"][1:]}) == e["tools"][0]]
        self.assertGreaterEqual(len(derived), 150)
        for entry in derived:
            self.assertEqual(len(entry["tools"]), len(set(entry["tools"])), entry["id"])

    def test_spot_checks(self):
        first = {i: self.by_id[i]["tools"][0] for i in ("6.01", "8.02", "10.06", "7.01", "14.02", "13.01", "16.09", "3.18")}
        self.assertEqual(first, {"6.01": "fetch_osm_features", "8.02": "fetch_osm_features", "10.06": "fetch_osm_features",
                                 "7.01": "search_hdx_datasets", "14.02": "search_hdx_datasets", "13.01": "search_hdx_datasets",
                                 "16.09": "fetch_nasa_active_fires", "3.18": "fetch_worldpop_population"})

    def test_assessments_of_features_are_not_sent_to_openstreetmap(self):
        for task_id in ("5.06", "5.07", "6.24", "6.25", "7.08"):
            self.assertFalse(self.by_id[task_id]["tools"][0].startswith(self.deriver.FETCH_PREFIXES), task_id)
        self.assertEqual(self.by_id["9.04"]["tools"][0], "search_hdx_datasets")     # food prices are data, not a map feature

    def test_a_fetch_and_show_task_still_cannot_answer_a_computation(self):
        """The 'only shows data' guard (algorithm_topics.DISPLAY_ONLY_TOOLS) must still hold now that those tasks start with a fetch tool."""
        from cartogen_ai.core.agent.task_matcher import classify
        verdict = classify("create thiessen polygons around the health facilities")
        self.assertTrue(verdict["best"] is None or (verdict["ambiguous"] and verdict["reason"] == "below confidence floor"), verdict["reason"])

    def test_a_task_that_already_had_a_fetch_tool_is_untouched(self):
        entry = {"text": "Map hospitals and clinics", "tools": ["fetch_osm_features", "add_layer_from_path"]}
        self.assertIsNone(self.deriver.fetch_tool_for(entry))
        self.assertIsNone(self.deriver.fetch_tool_for({"text": "Create base maps", "tools": ["add_layer_from_path"]}))


if __name__ == "__main__":
    unittest.main()
