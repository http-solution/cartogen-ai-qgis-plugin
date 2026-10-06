# -*- coding: utf-8 -*-
"""A named tool that is not called after several other calls gets a nudge (rc17 hand test B3, 2026-10-06)."""
import unittest

from cartogen_ai.core.agent.agent_orchestrator import CartogenAi

LOG_OTHER = [("get_layers", False, None), ("execute_read_only_sql", True, "x"), ("generate_spatial_report", False, None),
             ("search_web", True, "y")]


class TestDriftNudge(unittest.TestCase):
    def test_a_named_tool_not_called_after_four_other_calls_is_nudged(self):
        text = CartogenAi._named_tool_drift_nudge("call search_stac_satellite_imagery for Sentinel-2 scenes", LOG_OTHER)
        self.assertIn("search_stac_satellite_imagery", text)

    def test_no_nudge_once_the_named_tool_was_called(self):
        log = LOG_OTHER + [("search_stac_satellite_imagery", False, None)]
        self.assertIsNone(CartogenAi._named_tool_drift_nudge("call search_stac_satellite_imagery now", log))

    def test_no_nudge_when_no_tool_is_named_or_too_few_calls(self):
        self.assertIsNone(CartogenAi._named_tool_drift_nudge("show me the health facilities", LOG_OTHER))
        self.assertIsNone(CartogenAi._named_tool_drift_nudge("call search_stac_satellite_imagery", LOG_OTHER[:2]))


if __name__ == "__main__":
    unittest.main()
