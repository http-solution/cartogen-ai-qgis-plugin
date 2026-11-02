"""PLAN-045: the verified workflow report is pure assembly of recorded facts; every gap it finds is listed, none is hidden."""
import json
import unittest

from cartogen_ai.core.agent import result_gate, source_record, workflow_report


class FakeLayer:
    def __init__(self, props=None):
        self.props = dict(props or {})

    def customProperty(self, key, default=None):
        return self.props.get(key, default)

    def setCustomProperty(self, key, value):
        self.props[key] = value


def lineage(*entries):
    return json.dumps([{"tool": t, "params": p, "sources": s, "source_ids": [], "timestamp": at} for t, p, s, at in entries])


def project():
    boundary = FakeLayer({source_record.PROPERTY_KEY: json.dumps([source_record.build("fetch_geoboundaries", {"iso3": "YEM", "admin_level": "ADM2"}, {"success": True}, now="2026-11-01")]),
                          workflow_report._lineage_key(): lineage(("fetch_geoboundaries", {"iso3": "YEM"}, [], "2026-11-01 10:00:00"))})
    access = FakeLayer({workflow_report._lineage_key(): lineage(("service_area", {"minutes": 30}, ["Districts"], "2026-11-01 10:05:00"))})
    return {"Districts": boundary, "Coverage": access}


class TestKeys(unittest.TestCase):
    def test_the_checks_key_matches_the_gate(self):
        self.assertEqual(workflow_report.CHECKS_PROPERTY_KEY, result_gate.CHECKS_PROPERTY_KEY)


class TestRecordChecks(unittest.TestCase):
    def test_keeps_the_latest_runs_only(self):
        layer = FakeLayer()
        for i in range(result_gate.MAX_STORED_CHECK_RUNS + 3):
            self.assertTrue(result_gate.record_checks(layer, f"t{i}", [{"id": "geometry", "status": "pass", "detail": "ok", "extra": 1}]))
        runs = json.loads(layer.props[result_gate.CHECKS_PROPERTY_KEY])
        self.assertEqual(len(runs), result_gate.MAX_STORED_CHECK_RUNS)
        self.assertEqual(runs[-1]["tool"], f"t{result_gate.MAX_STORED_CHECK_RUNS + 2}")
        self.assertNotIn("extra", runs[-1]["checks"][0])

    def test_never_raises_on_a_bad_layer(self):
        self.assertFalse(result_gate.record_checks(None, "t", []))


class TestGatherAndBuild(unittest.TestCase):
    def test_upstream_layers_are_followed_and_listed_first(self):
        layers = project()
        entries = workflow_report.gather(["Coverage"], layers.get)
        self.assertEqual([e["layer"] for e in entries], ["Districts", "Coverage"])

    def test_the_recipe_is_in_time_order_with_inputs_and_parameters(self):
        text = workflow_report.build_markdown("Access", workflow_report.gather(["Coverage"], project().get), generated_at="t")
        self.assertLess(text.index("fetch_geoboundaries -> Districts"), text.index("service_area from Districts -> Coverage"))
        self.assertIn("minutes=30", text)

    def test_sources_appear_with_the_licence_caveat(self):
        text = workflow_report.build_markdown("Access", workflow_report.gather(["Coverage"], project().get))
        self.assertIn("geoBoundaries", text)
        self.assertIn("not checked against the data providers", text)

    def test_unchecked_layers_are_said_to_be_unchecked(self):
        text = workflow_report.build_markdown("Access", workflow_report.gather(["Coverage"], project().get))
        self.assertIn("No automated result checks were recorded for: Districts, Coverage", text)
        self.assertIn("none recorded", text)

    def test_a_failed_check_is_listed_before_the_table(self):
        layers = project()
        result_gate.record_checks(layers["Coverage"], "service_area", [{"id": "value_range", "status": "fail", "detail": "all values equal"}])
        text = workflow_report.build_markdown("Access", workflow_report.gather(["Coverage"], layers.get))
        self.assertIn("**FAILED checks", text)
        self.assertLess(text.index("value_range -- all values equal"), text.index("| Layer |"))

    def test_a_missing_layer_and_an_unknown_origin_are_reported(self):
        layers = {"Loaded": FakeLayer()}
        text = workflow_report.build_markdown("X", workflow_report.gather(["Loaded", "Gone"], layers.get))
        self.assertIn("Origin unknown", text)
        self.assertIn("Not in the project any more", text)

    def test_cycles_do_not_loop(self):
        a = FakeLayer({workflow_report._lineage_key(): lineage(("t", {}, ["B"], "1"))})
        b = FakeLayer({workflow_report._lineage_key(): lineage(("t", {}, ["A"], "2"))})
        self.assertEqual(len(workflow_report.gather(["A"], {"A": a, "B": b}.get)), 2)

    def test_the_analysts_assumptions_are_added_as_given_and_the_rerun_claim_is_modest(self):
        text = workflow_report.build_markdown("X", workflow_report.gather(["Coverage"], project().get), assumptions=["Roads as of 2024."])
        self.assertIn("- Roads as of 2024.", text)
        self.assertIn("expected, not shown", text)

    def test_long_parameters_are_cut(self):
        self.assertIn("...", workflow_report._params_text({"sql": "x" * 500}))


if __name__ == "__main__":
    unittest.main()
