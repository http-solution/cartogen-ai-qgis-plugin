"""PLAN-023 R3-3: the registration contract of raster_time_series_stats (offline: no QGIS, no numpy needed). The arithmetic is in test_raster_series.py and the
real-raster behaviour in test_raster_series_tool_live.py."""
import unittest

from cartogen_ai.core import tool_operations
from cartogen_ai.core.agent.tools import raster_series as rs
from cartogen_ai.core.agent.tools import raster_series_tool as tool
from cartogen_ai.core.agent.tools.registry import TOOL_KEYWORDS, TOOL_REGISTRY, TOOLS_SCHEMA


def schema():
    return next(t["function"] for t in TOOLS_SCHEMA if t["function"]["name"] == "raster_time_series_stats")


class TestRegistration(unittest.TestCase):
    def test_it_is_registered_with_the_three_statistics(self):
        self.assertIn("raster_time_series_stats", TOOL_REGISTRY)
        params = schema()["parameters"]
        self.assertEqual(params["required"], ["rasters"])
        self.assertEqual(params["properties"]["statistic"]["enum"], list(rs.STATISTICS))
        for key in ("rasters", "times", "target", "baseline", "min_observations", "output_name", "align_to_first", "resampling"):
            self.assertIn(key, params["properties"], key)

    def test_the_description_says_the_trend_is_per_year_and_has_no_significance(self):
        text = schema()["description"]
        self.assertIn("per YEAR", text)
        self.assertIn("not its statistical significance", text)
        self.assertIn("at least 3", text)

    def test_it_is_classified_as_creating_a_layer_and_has_routing_keywords(self):
        self.assertEqual(tool_operations.TOOL_OPERATION_TYPES["raster_time_series_stats"], tool_operations.CREATE)
        self.assertIn("time series", TOOL_KEYWORDS["raster_time_series_stats"])

    def test_without_qgis_it_says_so_instead_of_crashing(self):
        self.assertEqual(TOOL_REGISTRY["raster_time_series_stats"](["a", "b", "c"]), {"error": "QGIS not available"})

    def test_the_limits_are_documented_constants(self):
        self.assertEqual(tool.MAX_RASTERS, 60)
        self.assertGreaterEqual(tool.ACCUMULATOR_ARRAYS, 5)           # the trend holds five full-size arrays


if __name__ == "__main__":
    unittest.main()
