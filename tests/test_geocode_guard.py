"""Tracker item 1.26: geocoding refuses place text that comes from a protected layer. The pure parts (comparison, refusal text, the tools' signatures and descriptions). Offline, no QGIS: the real layers are in tests/test_geocode_guard_live.py."""
import inspect
import unittest

from cartogen_ai.core.agent.tools import TOOL_REGISTRY, TOOLS_SCHEMA
from cartogen_ai.core.agent.tools import _geocode_guard as gg


class TestComparison(unittest.TestCase):
    def test_texts_are_compared_trimmed_collapsed_and_ignoring_case(self):
        self.assertEqual(gg.norm("  12  Main   Street "), "12 main street")
        self.assertEqual(gg.norm(None), "")
        self.assertEqual(gg.norm("STRASSE"), gg.norm("strasse"))

    def test_a_text_that_is_a_value_of_a_protected_layer_is_found_and_counted(self):
        candidates = {"cases": {"12 main street", "4 oak road"}, "other": {"somewhere else"}}
        found = gg.texts_matching(["12 MAIN STREET", "99 Unknown Lane", "4 oak road "], candidates)
        self.assertEqual(found, {"cases": 2})

    def test_no_match_means_nothing_is_found(self):
        self.assertEqual(gg.texts_matching(["Amman", "Sanaa"], {"cases": {"12 main street"}}), {})
        self.assertEqual(gg.texts_matching([], {"cases": {"x"}}), {})
        self.assertEqual(gg.texts_matching(["   "], {"cases": {""}}), {})

    def test_a_retyped_or_derived_text_is_not_found_a_stated_limit(self):
        self.assertEqual(gg.texts_matching(["Main Street"], {"cases": {"12 main street"}}), {})


class TestRefusal(unittest.TestCase):
    def test_the_refusal_names_the_layers_the_tool_and_the_way_forward_and_forbids_working_around_it(self):
        result = gg.refusal("geocode_batch", {"case_addresses": "SENSITIVE; 3 of the 5 text(s) match values in it"})
        self.assertEqual(result["status"], "GEOCODING_REFUSED_PROTECTED")
        self.assertEqual(result["layers"], ["case_addresses"])
        self.assertIn("geocode_batch refused", result["error"])
        self.assertIn("'case_addresses'", result["error"])
        self.assertIn("public server", result["error"])
        self.assertIn("Do not retry with different arguments", result["message"])
        self.assertIn("PUBLIC or INTERNAL", result["message"])
        self.assertIn("Sensitivity dialog", result["message"])

    def test_several_layers_are_all_listed_in_order(self):
        result = gg.refusal("geocode_and_enrich", {"b": "RESTRICTED", "a": "SENSITIVE"})
        self.assertEqual(result["layers"], ["a", "b"])
        self.assertLess(result["error"].index("'a'"), result["error"].index("'b'"))

    def test_without_qgis_the_check_lets_a_lookup_through_because_no_project_exists(self):
        try:
            import qgis.core  # noqa: F401
        except ImportError:
            self.assertIsNone(gg.check("geocode_batch", ["Amman"], None))


class TestTheToolsCarryTheGuard(unittest.TestCase):
    def test_both_tools_take_a_source_layer_in_code_and_in_their_schema(self):
        schemas = {t["function"]["name"]: t["function"] for t in TOOLS_SCHEMA}
        for name in ("geocode_batch", "geocode_and_enrich"):
            self.assertIn("source_layer", inspect.signature(TOOL_REGISTRY[name]).parameters, name)
            self.assertIn("source_layer", schemas[name]["parameters"]["properties"], name)
            self.assertNotIn("source_layer", schemas[name]["parameters"].get("required", []), name)

    def test_the_guard_runs_before_any_network_call(self):
        for name in ("geocode_batch", "geocode_and_enrich"):
            source = inspect.getsource(TOOL_REGISTRY[name])
            self.assertLess(source.index("_geocode_guard.check("), source.index("_geocode_one(") if name == "geocode_and_enrich" else source.index("cancel_signal"), name)

    def test_the_batch_description_tells_the_model_it_is_refused_for_protected_layers(self):
        description = next(t["function"]["description"] for t in TOOLS_SCHEMA if t["function"]["name"] == "geocode_batch")
        self.assertIn("REFUSED", description)
        self.assertIn("source_layer", description)

    def test_the_data_source_catalogue_says_so(self):
        import json
        from pathlib import Path
        path = Path(__file__).resolve().parents[1] / "src" / "cartogen_ai" / "core" / "agent" / "data_sources.json"
        entry = next(e for e in json.loads(path.read_text(encoding="utf-8"))["sources"] if e["id"] == "geocoding")
        self.assertIn("refused", entry["egress_note"])


if __name__ == "__main__":
    unittest.main()
