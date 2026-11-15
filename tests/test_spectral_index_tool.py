"""PLAN-023 R3-1: the registration contract of calculate_spectral_index (offline: no QGIS, no numpy needed). The arithmetic is in test_raster_indices.py and the
real-raster behaviour in test_spectral_index_tool_live.py."""
import unittest

from cartogen_ai.core import tool_operations
from cartogen_ai.core.agent.tools import raster_indices as ri
from cartogen_ai.core.agent.tools import spectral_index_tool as tool
from cartogen_ai.core.agent.tools.registry import TOOL_KEYWORDS, TOOL_REGISTRY, TOOLS_SCHEMA


def schema():
    return next(t["function"] for t in TOOLS_SCHEMA if t["function"]["name"] == "calculate_spectral_index")


class TestRegistration(unittest.TestCase):
    def test_it_is_registered_with_required_index_and_bands(self):
        self.assertIn("calculate_spectral_index", TOOL_REGISTRY)
        params = schema()["parameters"]
        self.assertEqual(params["required"], ["index", "bands"])
        self.assertEqual(params["properties"]["index"]["enum"], list(ri.INDICES))
        for key in ("bands", "output_name", "soil_factor", "align_to_first", "resampling"):
            self.assertIn(key, params["properties"], key)

    def test_the_description_lists_every_index_with_its_band_roles(self):
        text = schema()["description"]
        for name, (roles, _f, _m) in ri.INDICES.items():
            self.assertIn(f"{name}: {', '.join(roles)}", text)
        self.assertIn("Nothing guesses which band is which", text)

    def test_it_is_classified_as_creating_a_layer_and_has_routing_keywords(self):
        self.assertEqual(tool_operations.TOOL_OPERATION_TYPES["calculate_spectral_index"], tool_operations.CREATE)
        self.assertIn("savi", TOOL_KEYWORDS["calculate_spectral_index"])

    def test_without_qgis_it_says_so_instead_of_crashing(self):
        self.assertEqual(TOOL_REGISTRY["calculate_spectral_index"]("NDVI", {"nir": "a", "red": "b"}), {"error": "QGIS not available"})

    def test_the_nodata_value_is_a_single_documented_constant(self):
        self.assertEqual(tool.NODATA, -9999.0)


if __name__ == "__main__":
    unittest.main()
