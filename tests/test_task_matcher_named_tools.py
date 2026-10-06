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


if __name__ == "__main__":
    unittest.main()
