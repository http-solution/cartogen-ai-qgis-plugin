"""Long requests (over 25 words) need a name or phrase match to take a tool slot, not description words alone.

Why: the owner's real 16-call run (2026-11-01, per-call log) carried eight tools that matched only on description words and won their
slots on an alphabetical tie at score 8 (analyze_critical_links, apply_network_barriers, classify_facilities_by_access, ...). They were
never called and cost about 4,800 tokens on every call, roughly 17 percent of the 440,000 tokens the run used."""
import json
import unittest
from pathlib import Path

from cartogen_ai.core.agent.tools import TOOLS_SCHEMA
from cartogen_ai.core.services import tool_router
from cartogen_ai.core.services.tool_router import ToolRouter

TAIZ = ("Show me all the hospitals and clinics in Taiz governorate, count how many fall inside each district, colour the districts by that "
        "count and put the result on a printable map with a legend")
FILLERS = {"analyze_critical_links", "analyze_incident_trend", "apply_network_barriers", "classify_facilities_by_access",
           "design_sampling_frame", "estimate_population_exposure", "export_layout_atlas", "generate_html_dashboard"}
NEEDED = {"ingest_osm_features", "apply_graduated_style", "create_print_layout", "fetch_hdx_admin_boundaries"}
SIZE = {t["function"]["name"]: len(json.dumps(t)) // 4 for t in TOOLS_SCHEMA}


class TestLongRequestFloor(unittest.TestCase):
    def test_the_floor_is_above_the_description_only_ceiling(self):
        """+8 is the most description words can add (4 hits x 2); a floor of 9 or more means a phrase or name match is required."""
        self.assertGreaterEqual(tool_router._LONG_QUERY_MIN_SCORE, 9)

    def test_the_taiz_request_keeps_what_it_needs_and_drops_the_unused_fillers(self):
        offered = {t["function"]["name"] for t in ToolRouter(TOOLS_SCHEMA).filter_relevant_tools(TAIZ)}
        self.assertLessEqual(NEEDED, offered)
        self.assertEqual(offered & FILLERS, set(), "tools that matched on description words alone are back")

    def test_long_routing_requests_carry_fewer_tool_tokens(self):
        rows = json.loads((Path(__file__).resolve().parent / "fixtures" / "routing_requests.json").read_text(encoding="utf-8"))
        router = ToolRouter(TOOLS_SCHEMA)
        long_rows = [r["prompt"] for r in rows if len(r["prompt"].split()) > 25]
        self.assertGreaterEqual(len(long_rows), 20)
        average = sum(sum(SIZE[t["function"]["name"]] for t in router.filter_relevant_tools(q)) for q in long_rows) / len(long_rows)
        self.assertLess(average, 7000, "was 9,055 tokens of tool schemas per long request before the floor moved from 6 to 9")


if __name__ == "__main__":
    unittest.main()
