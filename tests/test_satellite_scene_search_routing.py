"""DEF-10 (hand run A13): "find Sentinel-2 scenes over Aden for last month with under 20 percent cloud" must reach the scene search with
an area and real dates. Three parts: the tool list carries a way to get the area, the model is told today's date, and bad dates are
refused with a message the model can act on."""
import datetime
import unittest
from unittest.mock import patch

from cartogen_ai.core.agent import capabilities as cap
from cartogen_ai.core.agent import prompts
from cartogen_ai.core.agent.tools import multimodal_remote_sensing as rs
from cartogen_ai.core.services.tool_router import ToolRouter

A13 = "find Sentinel-2 scenes over Aden for last month with under 20 percent cloud"


class TestToolsOffered(unittest.TestCase):
    def test_the_scene_search_and_the_place_lookup_are_both_required(self):
        names = cap.required_tools(A13)
        self.assertIn("search_stac_satellite_imagery", names)
        self.assertIn("geocode_and_enrich", names)

    def test_the_router_offers_both_to_the_model(self):
        offered = {t["function"]["name"] for t in ToolRouter(prompts.TOOLS_SCHEMA).filter_relevant_tools(A13)}
        self.assertIn("search_stac_satellite_imagery", offered)
        self.assertIn("geocode_and_enrich", offered)

    def test_other_phrasings_are_covered_and_one_search_is_not_a_workflow(self):
        for q in ("show me satellite imagery of Aden", "search STAC for Sentinel 2 over Mukalla"):
            self.assertIn("geocode_and_enrich", cap.required_tools(q))
        self.assertFalse(cap.is_multi_step(A13))


class TestTodayLine(unittest.TestCase):
    def test_given_when_a_date_range_tool_is_offered_or_no_list_was_passed(self):
        day = datetime.date(2026, 10, 28)
        self.assertIn("2026-10-28", prompts._today_line(["search_stac_satellite_imagery"], today=day))
        self.assertIn("2026-10-28", prompts._today_line(None, today=day))

    def test_left_out_when_no_such_tool_is_offered(self):
        self.assertEqual(prompts._today_line(["buffer_analysis"], today=datetime.date(2026, 10, 28)), "")

    def test_it_reaches_the_system_prompt(self):
        text = prompts.build_system_prompt(active_tool_names=["search_stac_satellite_imagery"])
        self.assertIn("Today's date is", text)
        self.assertNotIn("Today's date is", prompts.build_system_prompt(active_tool_names=["buffer_analysis"]))


class TestDateValidation(unittest.TestCase):
    def setUp(self):
        rs._STAC_CACHE.clear()
        rs._STAC_QUOTA["count"] = 0

    def test_a_malformed_date_is_explained_and_nothing_is_sent(self):
        with patch.object(rs, "_qgis_urlopen") as sent:
            res = rs.search_stac_satellite_imagery([44.9, 12.7, 45.1, 12.9], "last month", "2026-09-30")
        self.assertIn("YYYY-MM-DD", res["error"])
        sent.assert_not_called()

    def test_reversed_dates_are_explained(self):
        res = rs.search_stac_satellite_imagery([44.9, 12.7, 45.1, 12.9], "2026-09-30", "2026-09-01")
        self.assertIn("after end_date", res["error"])

    def test_a_good_request_sends_clean_dates_and_the_cloud_filter(self):
        captured = {}

        def fake_build(url, data=None, headers=None):
            captured["payload"] = data
            return object()

        class _Resp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        with patch.object(rs, "_net_build_request", side_effect=fake_build), patch.object(rs, "_qgis_urlopen", return_value=_Resp()), \
                patch.object(rs, "_read_capped", return_value=b'{"features": []}'):
            res = rs.search_stac_satellite_imagery([44.9, 12.7, 45.1, 12.9], "2026-09-01T00:00:00Z", "2026-09-30", 5, 20)
        self.assertTrue(res["success"])
        self.assertIn(b"2026-09-01T00:00:00Z/2026-09-30T23:59:59Z", captured["payload"])
        self.assertIn(b'"lt": 20.0', captured["payload"])
        self.assertIn("note", res)


if __name__ == "__main__":
    unittest.main()
