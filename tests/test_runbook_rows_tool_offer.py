"""DEF-17: for the nine runbook rows that failed with a weak model (A5, A6, C1, C3, C4, C6, D4, E2, S5), the tools each row needs must at least
be OFFERED to the model for the exact prompt. A tool the router leaves out cannot be chosen, and the model then asks the user for what the tool
would have supplied (A5, A6 in the 1.18.4 run). Whether a model CHOOSES the right tool is a model question this table does not answer: it only
removes the offering as a cause. Prompts are the runbook's, with <F> replaced."""
import unittest

from cartogen_ai.core.agent.prompts import TOOLS_SCHEMA
from cartogen_ai.core.services.tool_router import ToolRouter

F = r"C:\smoke\fixtures"
ROWS = {
    "A5": ("get building footprints for a small area in Aden", ["fetch_building_footprints", "geocode_and_enrich"]),
    "A6": ("download population for a small area in Aden", ["fetch_worldpop_population", "geocode_and_enrich"]),
    "C1": ("block roads within 500 metres of bridges_grid_fixture, using speed_kmh as the base speed, call the new field speed_blocked",
           ["apply_network_barriers"]),
    "C3": ("which facilities in hospitals_grid_fixture are within 1 hour of origin_fixture, using speed_blocked", ["classify_facilities_by_access"]),
    "C4": ("travel times from origin_fixture to hospitals_grid_fixture using speed_blocked", ["travel_time_matrix"]),
    "C6": (f"Load hub_candidates_fixture.geojson and demand_points_fixture.geojson from {F}, then which 2 of the hub_candidates_fixture sites "
           "should be hubs to serve demand_points_fixture, weighted by people", ["add_layer_from_path"]),
    "D4": (f"compare needs in admin_units_fixture (people_in_need, displaced, water_gap; unit field ADM2_PCODE) with {F}\\3w_fixture.csv "
           "(admin column admin_pcode, organization column organization), write the result to presence_gap", ["calculate_presence_gap"]),
    "E2": ("compute the preliminary PiN and severity from the JIAF file, join to admin_units_fixture by P-code", ["compute_jiaf_preliminary"]),
    "S5": ("set up a forecast trigger for flooding with no threshold", ["evaluate_forecast_trigger"]),
}


class TestRunbookRowsOfferTheirTools(unittest.TestCase):
    def test_every_needed_tool_exists_and_is_offered(self):
        registered = {t["function"]["name"] for t in TOOLS_SCHEMA}
        router = ToolRouter(TOOLS_SCHEMA)
        problems = []
        for row, (prompt, needed) in ROWS.items():
            offered = {t["function"]["name"] for t in router.filter_relevant_tools(prompt)}
            problems += [f"{row}: {name} is not a registered tool" for name in needed if name not in registered]
            problems += [f"{row}: {name} is not offered" for name in needed if name in registered and name not in offered]
        self.assertEqual(problems, [])

    def test_a_place_name_request_is_offered_the_place_lookup_but_a_layer_request_is_not_burdened(self):
        router = ToolRouter(TOOLS_SCHEMA)
        offered = {t["function"]["name"] for t in router.filter_relevant_tools("buffer roads by 200 metres and dissolve the result")}
        self.assertNotIn("geocode_and_enrich", offered)


if __name__ == "__main__":
    unittest.main()
