"""PLAN-044: where fetched data came from. Pure logic plus the provenance record and report text; the layer tagging is in test_source_record_live.py."""
import json
import unittest

from cartogen_ai.core.agent import source_record
from cartogen_ai.core.agent.tools import export_tools


class FakeLayer:
    def __init__(self, props=None):
        self.props = dict(props or {})

    def customProperty(self, key, default=None):
        return self.props.get(key, default)

    def setCustomProperty(self, key, value):
        self.props[key] = value

    def name(self):
        return "fake"


class TestBuild(unittest.TestCase):
    def test_a_successful_fetch_gets_a_record_with_licence_date_and_coverage(self):
        record = source_record.build("fetch_geoboundaries", {"iso3": "YEM", "admin_level": "ADM2"}, {"success": True, "layer_name": "x"}, now="2026-11-01")
        self.assertEqual(record["retrieved_at"], "2026-11-01")
        self.assertEqual(record["coverage"], "YEM; ADM2")
        self.assertIn("CC BY", record["licence"])
        self.assertFalse(record["licence_checked"])

    def test_nothing_for_failures_unknown_tools_or_non_dicts(self):
        self.assertIsNone(source_record.build("fetch_geoboundaries", {}, {"error": "x"}))
        self.assertIsNone(source_record.build("fetch_geoboundaries", {}, {"success": False}))
        self.assertIsNone(source_record.build("buffer", {}, {"success": True}))
        self.assertIsNone(source_record.build("fetch_geoboundaries", {}, [1]))

    def test_hdx_does_not_claim_one_licence(self):
        record = source_record.build("fetch_hdx_admin_boundaries", {"iso3": "YEM"}, {"success": True})
        self.assertIn("per dataset", record["licence"])

    def test_coverage_uses_box_extent_layer_and_period(self):
        self.assertEqual(source_record.coverage_for({"bbox": [44.0, 13.0, 44.5, 13.6], "days": 3}, {}), "box 44, 13, 44.5, 13.6; last 3 days")
        self.assertEqual(source_record.coverage_for({"extent_layer": "Taiz", "year": "2020"}, {}), "extent of layer 'Taiz'; year 2020")
        self.assertIsNone(source_record.coverage_for({}, {}))

    def test_attach_uses_data_source_and_keeps_an_existing_source_key(self):
        result = {"success": True, "source": "USGS text", "layer_name": "q"}
        source_record.attach("fetch_usgs_earthquakes", {"days": 7}, result)
        self.assertEqual(result["source"], "USGS text")
        self.assertEqual(result["data_source"]["tool"], "fetch_usgs_earthquakes")

    def test_every_registered_tool_is_a_real_tool(self):
        from cartogen_ai.core.agent.tools.registry import TOOLS_SCHEMA
        names = {t["function"]["name"] for t in TOOLS_SCHEMA}
        # importing the tool modules registers them
        from cartogen_ai.core.agent.agent_orchestrator import TWO_PHASE_TOOLS      # noqa: F401
        self.assertLessEqual(source_record.source_tools() - names, set())


class TestStore(unittest.TestCase):
    def test_tagging_twice_with_the_same_coverage_replaces_not_duplicates(self):
        layer = FakeLayer()
        first = {"tool": "t", "coverage": "YEM", "retrieved_at": "a"}
        self.assertTrue(source_record.tag_layer(layer, first))
        source_record.tag_layer(layer, {"tool": "t", "coverage": "YEM", "retrieved_at": "b"})
        source_record.tag_layer(layer, {"tool": "t", "coverage": "SYR", "retrieved_at": "b"})
        stored = source_record.parse(layer.props[source_record.PROPERTY_KEY])
        self.assertEqual(len(stored), 2)
        self.assertEqual([r["retrieved_at"] for r in stored if r["coverage"] == "YEM"], ["b"])

    def test_unreadable_property_is_empty_not_an_error(self):
        self.assertEqual(source_record.parse("{not json"), [])
        self.assertEqual(source_record.parse(None), [])
        self.assertFalse(source_record.tag_layer(None, {"tool": "t"}))

    def test_collect_inherits_through_lineage_and_survives_cycles(self):
        record = {"tool": "fetch_geoboundaries", "coverage": "YEM", "retrieved_at": "d"}
        child = FakeLayer({"cartogen/lineage": json.dumps([{"tool": "buffer", "sources": ["parent"]}])})
        parent = FakeLayer({source_record.PROPERTY_KEY: json.dumps([record]),
                            "cartogen/lineage": json.dumps([{"tool": "x", "sources": ["child"]}])})
        lookup = {"child": child, "parent": parent}.get
        from cartogen_ai.core.agent import lineage
        if not lineage.QGIS_AVAILABLE:
            self.skipTest("lineage reads layers only with QGIS")
        self.assertEqual(source_record.collect(child, lookup), [record])

    def test_collect_without_lookup_is_only_the_layers_own(self):
        record = {"tool": "t", "coverage": "c", "retrieved_at": "d"}
        self.assertEqual(source_record.collect(FakeLayer({source_record.PROPERTY_KEY: json.dumps([record])})), [record])


class TestReport(unittest.TestCase):
    def test_description_says_the_licence_was_not_checked(self):
        line = source_record.describe(source_record.build("ingest_osm_features", {"bbox": [1, 2, 3, 4]}, {"success": True}, now="2026-11-01"))
        for part in ("OpenStreetMap", "ODbL 1.0", "not checked against the source", "retrieved 2026-11-01", "box 1, 2, 3, 4", "© OpenStreetMap contributors"):
            self.assertIn(part, line)

    def test_markdown_report_lists_a_layers_data_source(self):
        layer = FakeLayer({source_record.PROPERTY_KEY: json.dumps([source_record.build("fetch_usgs_earthquakes", {}, {"success": True})])})
        original = export_tools._find_layer_by_name
        export_tools._find_layer_by_name = lambda name: layer
        try:
            entries = export_tools._layer_provenance_entries(["fake"])
        finally:
            export_tools._find_layer_by_name = original
        self.assertEqual(entries[0]["data_sources"][0]["tool"], "fetch_usgs_earthquakes")


if __name__ == "__main__":
    unittest.main()
