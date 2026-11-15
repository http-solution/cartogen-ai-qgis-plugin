"""PLAN-023 R3-2: the registration contract of load_stac_assets (offline: no QGIS needed). The size and address rules are in test_stac_ops.py; the real download is in test_stac_load_tool_live.py."""
import unittest

from cartogen_ai.core import tool_operations
from cartogen_ai.core.agent.tools.registry import TOOL_KEYWORDS, TOOL_REGISTRY, TOOLS_SCHEMA


def schema():
    return next(t["function"] for t in TOOLS_SCHEMA if t["function"]["name"] == "load_stac_assets")


class TestRegistration(unittest.TestCase):
    def test_it_is_registered_with_dates_and_bands_required(self):
        self.assertIn("load_stac_assets", TOOL_REGISTRY)
        params = schema()["parameters"]
        self.assertEqual(params["required"], ["start_date", "end_date", "assets"])
        for key in ("bbox", "layer_name", "max_cloud", "limit"):
            self.assertIn(key, params["properties"], key)

    def test_the_description_states_the_limits_and_what_is_not_supported(self):
        self.assertEqual(tool_operations.TOOL_OPERATION_TYPES["load_stac_assets"], tool_operations.CREATE)
        text = schema()["description"]
        for word in ("AREA ONLY", "nothing is downloaded until it is confirmed", "at most 6", "Landsat", "AWS credentials", "search_stac_satellite_imagery"):
            self.assertIn(word, text)
        self.assertIn("download sentinel-2", TOOL_KEYWORDS["load_stac_assets"])

    def test_without_qgis_it_says_so_instead_of_crashing(self):
        self.assertEqual(TOOL_REGISTRY["load_stac_assets"]("2026-10-01", "2026-11-01", ["red"]), {"error": "QGIS not available"})


if __name__ == "__main__":
    unittest.main()
