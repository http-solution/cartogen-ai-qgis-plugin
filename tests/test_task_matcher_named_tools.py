# -*- coding: utf-8 -*-
"""A request that names a tool must not be steered to a task that does not use it (rc15 hand test D01, 2026-10-06)."""
import unittest

from cartogen_ai.core.agent import task_matcher as tm

# Prompts taken from the rc15 live smoke report (docs/ Section "Defects", D01/D03).
HUB = ("Use optimal_hub_siting to rank the three candidate locations in smoke_hubs by average straight-line distance to all five "
       "demand features in smoke_points. Tell me the winning hub name and each candidate's computed average distance; do not claim "
       "road-network routing or population weighting.")
IMAGERY = "Run extract_features_from_imagery on loaded raster smoke_image with confidence threshold 0.4."
STAC = ("Transform smoke_boundary's extent to WGS84 and call search_stac_satellite_imagery for Sentinel-2 scenes from 2026-08-01 "
        "through 2026-08-31, limit 5.")


class TestNamedToolGuard(unittest.TestCase):
    def test_tool_names_are_picked_out_of_the_request(self):
        self.assertEqual(tm.named_tools(HUB), {"optimal_hub_siting"})
        self.assertEqual(tm.named_tools("Buffer smoke_points by 500 meters."), set())  # a layer name is not a tool

    def test_a_task_that_does_not_use_the_named_tool_is_never_chosen(self):
        for query in (HUB, IMAGERY, STAC):
            verdict = tm.classify(query)
            if verdict["best"] is not None:
                self.assertTrue(tm.named_tools(query) & set(verdict["best"]["tools"]), (query, verdict["best"]["id"]))

    def test_a_named_tool_with_no_task_that_uses_it_gets_no_directive(self):
        verdict = tm.classify(IMAGERY)
        self.assertIsNone(verdict["best"])
        self.assertFalse(verdict["ambiguous"])
        self.assertEqual(verdict["reason"], "names a tool the matched task does not use")

    def test_the_hub_request_is_matched_to_a_task_that_uses_hub_siting(self):
        best = tm.classify(HUB)["best"]
        self.assertIsNotNone(best)
        self.assertIn("optimal_hub_siting", best["tools"])

    def test_requests_that_name_no_tool_are_matched_as_before(self):
        verdict = tm.classify("Health facilities beyond one hour's travel from the point")
        self.assertEqual(verdict["best"]["tools"][0], "calculate_service_area")


class TestWeakTiesAreNotTrusted(unittest.TestCase):
    """rc15/rc17 hand tests: long specific requests tied across sections on two generic words and got a wrong task directive."""

    SEVERITY = ("Calculate a severity index for the three polygons in smoke_admin using its numeric population and need fields, "
                "with admin_name as the unit name. Use equal weights, write the score to severity_rc17, and then style "
                "smoke_admin by that field.")
    PLAN = ("Plan first, then buffer smoke_points by 250 meters, clip the buffers to smoke_boundary, export the result to a "
            "GeoPackage and store a project memory note that the buffer distance was 250 meters.")

    def test_long_requests_that_tie_on_two_words_get_no_directive(self):
        from cartogen_ai.core.services.prompt_refiner import analyze_request
        for query in (self.SEVERITY, self.PLAN):
            a = analyze_request(query)
            self.assertIsNone(a["task"], query)
            self.assertEqual(a["directive"], "")
            self.assertEqual(a["user_message"], query.strip())

    def test_a_short_request_the_task_describes_still_matches(self):
        verdict = tm.classify("build me a dashboard of displacement by district")
        self.assertEqual(verdict["reason"], "tie across sections")
        self.assertIsNotNone(verdict["best"])
        self.assertGreaterEqual(tm._coverage("build me a dashboard of displacement by district", verdict["best"]), tm._TIE_MIN_COVERAGE)



class TestSlotsAnsweredByOwnData(unittest.TestCase):
    """rc17 hand test R2: 'Which facility or service type?' was asked twice of a request that names its own layers."""

    HUB = ("Use optimal_hub_siting to rank the three candidate locations in smoke_hubs by average straight-line distance to all five "
           "demand features in smoke_points.")

    def test_a_request_naming_its_own_layers_is_not_asked_for_a_facility_type(self):
        entry = tm.classify(self.HUB)["best"]
        self.assertIsNotNone(entry)
        self.assertNotIn("facility_type", tm.missing_slots(entry, self.HUB))

    def test_layer_like_names_are_detected_but_tool_names_are_not(self):
        self.assertTrue(tm.has_explicit_data_reference("buffer smoke_points by 500 m"))
        self.assertTrue(tm.has_explicit_data_reference("export to outputs/points.csv"))
        self.assertFalse(tm.has_explicit_data_reference("use optimal_hub_siting on it"))
        self.assertFalse(tm.has_explicit_data_reference("health facilities beyond one hour"))

    def test_with_the_project_layers_only_a_loaded_layer_counts(self):
        layers = ["smoke_hubs", "smoke_points"]
        self.assertTrue(tm.has_explicit_data_reference("rank smoke_hubs by distance to smoke_points", layers))
        # A column or algorithm name is not a data reference (code review of the first version).
        self.assertFalse(tm.has_explicit_data_reference("estimate population affected by flood_risk", layers))
        self.assertFalse(tm.has_explicit_data_reference("run native_buffer on it", layers))
        self.assertFalse(tm.has_explicit_data_reference("export to outputs/points.csv", layers))
        self.assertFalse(tm.has_explicit_data_reference("rank hubs", []))

    def test_supply_hubs_now_answer_the_facility_question(self):
        entry = next(e for e in __import__("cartogen_ai.core.agent.task_register", fromlist=["x"]).load()
                     if "facility_type" in e.get("slots", []))
        self.assertNotIn("facility_type", tm.missing_slots(entry, "Synthetic humanitarian supply hubs"))

    def test_choices_with_no_safe_default_are_still_asked(self):
        entry = next((e for e in __import__("cartogen_ai.core.agent.task_register", fromlist=["x"]).load()
                      if "hazard_type" in e.get("slots", [])), None)
        if entry:
            self.assertIn("hazard_type", tm.missing_slots(entry, "analyse smoke_admin and smoke_points"))


class TestSingleSharedWord(unittest.TestCase):
    """rc17 hand test R4: one shared word is a coincidence in a long request, however high it scores."""

    ENTRY = {"id": "x.01", "cat": "c", "cname": "Data standards", "kw": ["raster", "schema"], "tools": ["validate_schema"], "text": "t",
             "slots": []}

    def _classify(self, query):
        from unittest.mock import patch
        with patch.object(tm, "match", return_value=[(self.ENTRY, 0.5)]):
            return tm.classify(query)

    def test_a_long_request_sharing_one_word_gets_no_directive(self):
        verdict = self._classify("Apply a multicolour colour ramp to the raster layer smoke_dem using band 1 and its real values")
        self.assertEqual(verdict["reason"], "below confidence floor")

    def test_a_long_request_sharing_two_words_is_kept(self):
        verdict = self._classify("Check the raster layer smoke_dem against the schema we agreed for band 1 and its real values")
        self.assertNotEqual(verdict["reason"], "below confidence floor")

    def test_a_short_request_may_match_on_one_word(self):
        verdict = self._classify("raster for flooding")
        self.assertNotEqual(verdict["reason"], "below confidence floor")


class TestRegisterCorpusIsNotWorse(unittest.TestCase):
    """The rc15/rc17 matcher guards (named tool, tie coverage, single hit) must not cost matches the register itself expects.

    Each task's own description is run through classify(); before these guards 453 of 748 matched their own task and 466 got a
    directive. The guards may only ever stay at or above those numbers."""

    def test_task_descriptions_still_match_their_own_task(self):
        from cartogen_ai.core.agent import task_register as reg
        own = directive = total = 0
        for e in reg.load():
            q = e.get("text") or ""
            if len(q.split()) < 3:
                continue
            total += 1
            v = tm.classify(q)
            if v["best"] and v["best"]["id"] == e["id"]:
                own += 1
            if v["best"] and not (v["ambiguous"] and v["reason"] == "below confidence floor"):
                directive += 1
        self.assertGreaterEqual(total, 700)
        self.assertGreaterEqual(own, 453)
        self.assertGreaterEqual(directive, 466)


if __name__ == "__main__":
    unittest.main()


class TestHazardTasksNeedTheHazardNamed(unittest.TestCase):
    """rc22 live smoke V1/J5/J16/T2: a generic 'severity'/'risk' map request must not become a drought/heat task."""

    def _ids(self, query):
        from cartogen_ai.core.agent import task_matcher as tm
        return [e["id"] for e, _s in tm.match(query, limit=10)]

    def test_generic_severity_request_does_not_match_drought(self):
        self.assertNotIn("14.05", self._ids("Show the severity on the map for smoke_admin"))
        self.assertNotIn("14.05", self._ids("Make a map of the JIAF severity for the report"))

    def test_generic_risk_request_does_not_match_a_specific_hazard(self):
        ids = self._ids("Show the INFORM risk on the map using inf_risk")
        self.assertNotIn("14.12", ids)
        self.assertNotIn("14.14", ids)

    def test_naming_the_hazard_still_finds_its_task(self):
        self.assertIn("14.05", self._ids("Map drought severity"))
        self.assertIn("14.02", self._ids("Map flood extent"))
        self.assertIn("14.12", self._ids("Map extreme heat risk"))


class TestClusteringFindsImageClassification(unittest.TestCase):
    def test_cluster_a_raster_into_groups_finds_image_classification(self):
        from cartogen_ai.core.agent import task_matcher as tm
        top = [e["id"] for e, _s in tm.match("Cluster smoke_image into four groups", limit=3)]
        self.assertIn("16.21", top)
