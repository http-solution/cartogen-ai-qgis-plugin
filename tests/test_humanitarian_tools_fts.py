# -*- coding: utf-8 -*-
"""Tests for fetch_fts_funding_data (agent/tools/humanitarian_tools.py), the
Phase 2 humanitarian-ops improvement: OCHA Financial Tracking Service
integration for funding requirements/received/gap/coverage. Network calls are
mocked -- the actual live-API schema (in particular that funding totals live
at data.incoming.fundingTotal, not the more elaborate report1-4 breakdown
returned by the groupby=cluster variant) was verified by hand against the
real API before writing this tool; see the humanitarian-ops session notes."""
import json
import unittest
from unittest.mock import patch, MagicMock
from cartogen_ai.core.agent.tools.humanitarian_tools import fetch_fts_funding_data, _LOOKUP_CACHE


def _mock_response(payload):
    resp = MagicMock()
    resp.read.return_value = json.dumps(payload).encode()
    resp.__enter__.return_value = resp
    resp.__exit__.return_value = False
    return resp


_ONE_PLAN_2026 = {
    "data": [
        {
            "id": 1520,
            "planVersion": {"name": "Yemen Humanitarian Needs and Response Plan 2026"},
            "years": [{"year": "2026"}],
            "origRequirements": 2162563336,
            "revisedRequirements": 2162563336,
        },
    ]
}

_FLOW_2026 = {"data": {"incoming": {"flowCount": 405, "fundingTotal": 434734581, "pledgeTotal": 40679900}}}

_MULTI_PLAN_2020 = {
    "data": [
        {"id": 831, "planVersion": {"name": "Somalia HRP 2020"}, "years": [{"year": "2020"}], "revisedRequirements": 1000},
        {"id": 952, "planVersion": {"name": "GHRP (COVID) 2020"}, "years": [{"year": "2020"}], "revisedRequirements": 2000},
    ]
}


class TestFetchFtsFundingDataValidation(unittest.TestCase):
    def test_rejects_non_three_letter_code(self):
        res = fetch_fts_funding_data("YE")
        self.assertIn("error", res)
        self.assertIn("ISO", res["error"])

    def test_rejects_non_alpha_code(self):
        res = fetch_fts_funding_data("Y3M")
        self.assertIn("error", res)


class TestFetchFtsFundingDataAutoSelect(unittest.TestCase):
    def setUp(self):
        _LOOKUP_CACHE._store.clear()

    @patch("cartogen_ai.core.agent.tools.humanitarian_tools.urllib.request.urlopen")
    def test_auto_selects_latest_year_and_computes_gap(self, mock_urlopen):
        mock_urlopen.side_effect = [_mock_response(_ONE_PLAN_2026), _mock_response(_FLOW_2026)]

        res = fetch_fts_funding_data("yem")  # lowercase input, should be normalized

        self.assertTrue(res["success"])
        self.assertEqual(res["country_iso3"], "YEM")
        self.assertEqual(res["plan_id"], 1520)
        self.assertTrue(res["auto_selected_plan"])
        self.assertEqual(res["requirements_usd"], 2162563336)
        self.assertEqual(res["funding_received_usd"], 434734581)
        self.assertEqual(res["gap_usd"], 2162563336 - 434734581)
        self.assertAlmostEqual(res["coverage_percent"], 20.1, places=1)

    @patch("cartogen_ai.core.agent.tools.humanitarian_tools.urllib.request.urlopen")
    def test_result_is_cached_on_repeated_call(self, mock_urlopen):
        mock_urlopen.side_effect = [_mock_response(_ONE_PLAN_2026), _mock_response(_FLOW_2026)]

        first = fetch_fts_funding_data("YEM")
        second = fetch_fts_funding_data("YEM")

        self.assertNotIn("cached", first)
        self.assertTrue(second.get("cached"))
        self.assertEqual(mock_urlopen.call_count, 2)  # not 4 -- second call served from cache


class TestFetchFtsFundingDataMultiplePlans(unittest.TestCase):
    def setUp(self):
        _LOOKUP_CACHE._store.clear()

    @patch("cartogen_ai.core.agent.tools.humanitarian_tools.urllib.request.urlopen")
    def test_returns_plan_suggestion_instead_of_guessing(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response(_MULTI_PLAN_2020)

        res = fetch_fts_funding_data("SOM", year=2020)

        self.assertEqual(res["status"], "PLAN_SUGGESTION")
        self.assertEqual(len(res["plans"]), 2)
        self.assertEqual({p["plan_id"] for p in res["plans"]}, {831, 952})

    @patch("cartogen_ai.core.agent.tools.humanitarian_tools.urllib.request.urlopen")
    def test_no_plans_for_year_is_a_clean_error(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response({"data": []})

        res = fetch_fts_funding_data("SOM", year=1999)

        self.assertIn("error", res)


class TestFetchFtsFundingDataExplicitPlanId(unittest.TestCase):
    def setUp(self):
        _LOOKUP_CACHE._store.clear()

    @patch("cartogen_ai.core.agent.tools.humanitarian_tools.urllib.request.urlopen")
    def test_uses_plan_id_directly_without_listing_plans(self, mock_urlopen):
        plan_payload = {
            "data": {
                "id": 1116,
                "planVersion": {"name": "Yemen HRP 2023"},
                "revisedRequirements": 4344155316,
            }
        }
        flow_payload = {"data": {"incoming": {"fundingTotal": 1778292357}}}
        mock_urlopen.side_effect = [_mock_response(plan_payload), _mock_response(flow_payload)]

        res = fetch_fts_funding_data("YEM", plan_id=1116)

        self.assertTrue(res["success"])
        self.assertFalse(res["auto_selected_plan"])
        self.assertEqual(res["plan_id"], 1116)
        self.assertEqual(res["gap_usd"], 4344155316 - 1778292357)

    @patch("cartogen_ai.core.agent.tools.humanitarian_tools.urllib.request.urlopen")
    def test_unknown_plan_id_is_a_clean_error(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response({"data": {}})

        res = fetch_fts_funding_data("YEM", plan_id=999999)

        self.assertIn("error", res)


class TestFetchFtsFundingDataRobustness(unittest.TestCase):
    def setUp(self):
        _LOOKUP_CACHE._store.clear()

    @patch("cartogen_ai.core.agent.tools.humanitarian_tools.urllib.request.urlopen")
    def test_handles_network_failure_gracefully(self, mock_urlopen):
        mock_urlopen.side_effect = OSError("network unreachable")
        res = fetch_fts_funding_data("YEM")
        self.assertIn("error", res)

    @patch("cartogen_ai.core.agent.tools.humanitarian_tools.urllib.request.urlopen")
    def test_handles_missing_funding_total_gracefully(self, mock_urlopen):
        # Regression guard: confirmed live that a brand-new plan's response can
        # lack the funding total entirely under some API response shapes --
        # must report a clear error, not crash or silently return None math.
        mock_urlopen.side_effect = [_mock_response(_ONE_PLAN_2026), _mock_response({"data": {"incoming": {}}})]
        res = fetch_fts_funding_data("YEM")
        self.assertIn("error", res)

    @patch("cartogen_ai.core.agent.tools.humanitarian_tools.urllib.request.urlopen")
    def test_handles_missing_requirements_gracefully(self, mock_urlopen):
        no_reqs = {"data": [{"id": 1, "planVersion": {"name": "x"}, "years": [{"year": "2026"}]}]}
        mock_urlopen.return_value = _mock_response(no_reqs)
        res = fetch_fts_funding_data("YEM")
        self.assertIn("error", res)


if __name__ == "__main__":
    unittest.main()
