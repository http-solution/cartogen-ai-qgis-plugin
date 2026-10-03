import math
import unittest

from cartogen_ai.core.agent.prompts import build_system_prompt
from cartogen_ai.core.agent import task_matcher
from cartogen_ai.core.agent.tools import TOOLS_SCHEMA
from cartogen_ai.core.agent.tools.engineering_tools import (
    assess_watershed_hydrology_request,
    calculate_rational_watershed_peak_flow,
    parse_dms_location,
    parse_dms_location_text,
)
from cartogen_ai.core.services.tool_router import ToolRouter


REPORTED_QUERY = (
    "determine watershed area, steam length, h, slope, return period 20 year, "
    "intensity, tc, and peak flow at this location "
    "32° 1'47.39\"N, 35°48'21.00\"E"
)


class TestEngineeringHydrologyTools(unittest.TestCase):
    def test_exact_reported_dms_location_is_converted_deterministically(self):
        longitude, latitude = parse_dms_location_text(
            "32° 1'47.39\"N, 35°48'21.00\"E"
        )
        self.assertTrue(math.isclose(latitude, 32.0298305556, abs_tol=1e-10))
        self.assertTrue(math.isclose(longitude, 35.8058333333, abs_tol=1e-10))
        result = parse_dms_location("32° 1'47.39\"N, 35°48'21.00\"E")
        self.assertTrue(result["success"])
        self.assertEqual(result["coordinate_order"], "longitude, latitude")

    def test_dms_parser_rejects_invalid_or_incomplete_coordinates(self):
        self.assertIn("error", parse_dms_location("32°61'0\"N, 35°48'0\"E"))
        self.assertIn("error", parse_dms_location("32°1'0\"N"))
        self.assertIn("error", parse_dms_location("32°1'0\"N, 33°1'0\"S"))

    def test_coordinate_and_return_period_are_not_complete_design_inputs(self):
        result = assess_watershed_hydrology_request(
            "32° 1'47.39\"N, 35°48'21.00\"E", 20
        )
        self.assertEqual(result["status"], "INPUT_REQUIRED")
        self.assertEqual(result["outlet"]["longitude"], 35.8058333333)
        self.assertEqual(len(result["missing_inputs"]), 3)
        measurements = " ".join(result["required_gis_measurements"])
        self.assertIn("longest hydraulic flow path", measurements)
        self.assertIn("total stream-network length", result["required_gis_measurements"][3])

    def test_preflight_ready_only_when_design_sources_are_explicit(self):
        result = assess_watershed_hydrology_request(
            "32° 1'47.39\"N, 35°48'21.00\"E",
            20,
            dem_source="Copernicus DEM GLO-30, 30 m, EGM2008",
            idf_source="Local authority IDF curve, station X, 2025 edition",
            runoff_coefficient=0.42,
        )
        self.assertEqual(result["status"], "READY_FOR_GIS_DELINEATION")
        self.assertEqual(result["missing_inputs"], [])

    def test_rational_calculation_returns_auditable_units_and_equations(self):
        length_m = 1200.0
        slope = 60.0 / length_m
        tc = 0.0195 * length_m**0.77 * slope**-0.385
        result = calculate_rational_watershed_peak_flow(
            area_km2=0.5,
            flow_length_km=1.2,
            upstream_elevation_m=910,
            outlet_elevation_m=850,
            return_period_years=20,
            rainfall_intensity_mm_h=55,
            intensity_duration_minutes=tc,
            intensity_source="Local authority station X, 20-year IDF, 2025",
            runoff_coefficient=0.4,
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["measurements"]["H_elevation_drop_m"], 60)
        self.assertEqual(result["measurements"]["channel_slope_percent"], 5.0)
        self.assertTrue(math.isclose(result["results"]["peak_flow_m3_s"], 3.058, abs_tol=1e-4))
        self.assertEqual(result["design_status"], "PRELIMINARY_REQUIRES_LOCAL_ENGINEERING_REVIEW")
        self.assertTrue(result["design_inputs"]["intensity_source"].startswith("Local authority"))

    def test_rational_calculation_rejects_uncited_or_wrong_duration_intensity(self):
        base = dict(
            area_km2=0.25,
            flow_length_km=0.8,
            upstream_elevation_m=850,
            outlet_elevation_m=810,
            return_period_years=20,
            rainfall_intensity_mm_h=60,
            runoff_coefficient=0.5,
        )
        self.assertIn("error", calculate_rational_watershed_peak_flow(
            **base, intensity_duration_minutes=15, intensity_source=""
        ))
        wrong_duration = calculate_rational_watershed_peak_flow(
            **base, intensity_duration_minutes=240, intensity_source="Cited local IDF"
        )
        self.assertIn("does not match computed Tc", wrong_duration["error"])

    def test_reported_query_routes_to_all_three_engineering_guards(self):
        names = {
            entry["function"]["name"]
            for entry in ToolRouter(TOOLS_SCHEMA).filter_relevant_tools(REPORTED_QUERY, top_k=40)
        }
        self.assertTrue({
            "parse_dms_location",
            "assess_watershed_hydrology_request",
            "calculate_rational_watershed_peak_flow",
        } <= names)

    def test_reported_query_matches_engineering_hydrology_contract(self):
        verdict = task_matcher.classify(REPORTED_QUERY)
        self.assertEqual(verdict["best"]["id"], "36.01")
        self.assertEqual(verdict["best"]["cname"], "Engineering hydrology and drainage")
        self.assertFalse(verdict["ambiguous"])
        self.assertEqual(
            task_matcher.missing_slots(verdict["best"], REPORTED_QUERY),
            ["dem_source", "idf_source", "runoff_coefficient"],
        )

    def test_hydrology_prompt_rule_is_present_when_engineering_tool_is_active(self):
        prompt = build_system_prompt(
            active_tool_names=["assess_watershed_hydrology_request"]
        )
        self.assertIn("A coordinate and return period cannot determine a watershed", prompt)
        self.assertIn("longest hydraulic flow path", prompt)


class TestEngineeringAdjustments(unittest.TestCase):
    """Changes made when these tools were integrated into the GitHub tree (not in the original local version)."""

    def test_a_latitude_past_the_pole_is_rejected_even_when_the_degrees_equal_90(self):
        self.assertIn("error", parse_dms_location("90°30'0\"N, 35°48'0\"E"))
        self.assertTrue(parse_dms_location("90°0'0\"N, 35°48'0\"E")["success"])
        self.assertIn("error", parse_dms_location("32°1'0\"N, 180°0'1\"E"))

    def test_without_an_intensity_the_calculator_returns_tc_and_asks_for_the_idf_value(self):
        from cartogen_ai.core.agent.tools.engineering_tools import kirpich_tc_minutes
        result = calculate_rational_watershed_peak_flow(
            area_km2=0.5, flow_length_km=1.2, upstream_elevation_m=910, outlet_elevation_m=850, return_period_years=20)
        self.assertEqual(result["status"], "TC_COMPUTED_INTENSITY_REQUIRED")
        self.assertNotIn("peak_flow_m3_s", result["results"])
        self.assertTrue(math.isclose(result["results"]["time_of_concentration_minutes"],
                                     kirpich_tc_minutes(1200.0, 0.05), abs_tol=1e-3))
        self.assertIn("Do not estimate the intensity", result["next_step"])

    def test_a_partial_design_input_is_an_error_not_a_silent_tc_only_answer(self):
        result = calculate_rational_watershed_peak_flow(
            area_km2=0.5, flow_length_km=1.2, upstream_elevation_m=910, outlet_elevation_m=850, return_period_years=20,
            rainfall_intensity_mm_h=55)
        self.assertIn("error", result)

    def test_the_area_warnings_follow_the_documented_limits(self):
        length_m, drop = 1200.0, 60.0
        from cartogen_ai.core.agent.tools.engineering_tools import kirpich_tc_minutes
        tc = kirpich_tc_minutes(length_m, drop / length_m)
        common = dict(flow_length_km=1.2, upstream_elevation_m=910, outlet_elevation_m=850, return_period_years=20,
                      rainfall_intensity_mm_h=55, intensity_duration_minutes=tc, intensity_source="Cited IDF",
                      runoff_coefficient=0.4)
        small = calculate_rational_watershed_peak_flow(area_km2=0.2, **common)
        mid = calculate_rational_watershed_peak_flow(area_km2=0.6, **common)
        large = calculate_rational_watershed_peak_flow(area_km2=0.9, **common)
        self.assertEqual(len(small["warnings"]), 1)
        self.assertEqual(len(mid["warnings"]), 2)                     # past the Kirpich calibration area only
        self.assertTrue(any("80 ha" in w for w in large["warnings"]))  # past FHWA's Rational Method limit too

    def test_no_router_alias_is_short_enough_to_match_inside_ordinary_words(self):
        from cartogen_ai.core.services.tool_router import _TOOL_ALIASES
        for tool in ("parse_dms_location", "assess_watershed_hydrology_request", "calculate_rational_watershed_peak_flow"):
            for alias in _TOOL_ALIASES[tool]:
                self.assertGreaterEqual(len(alias), 5, (tool, alias))     # aliases match as substrings of the query

    def test_the_tools_are_classified_as_read_only_calculations(self):
        from cartogen_ai.core.agent.tool_operations import TOOL_OPERATION_TYPES
        for tool in ("parse_dms_location", "assess_watershed_hydrology_request", "calculate_rational_watershed_peak_flow"):
            self.assertEqual(TOOL_OPERATION_TYPES[tool], "READ")


if __name__ == "__main__":
    unittest.main()
