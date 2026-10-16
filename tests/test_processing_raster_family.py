"""Offline rules for the package D raster family: what is on the list, what is kept off, and which parameters are refused."""
import unittest
from unittest.mock import patch

from cartogen_ai.core.agent.tools._processing_allowlist import (ALLOWED_ALGORITHM_IDS, FAMILY_NAMES, RASTER_ALGORITHM_IDS, RASTER_EXCLUDED,
                                                                RASTER_FAMILY, parameter_violation)
from cartogen_ai.core.agent.tools.processing_allowlist_tools import _resolve_params


class RasterFamilyTests(unittest.TestCase):
    def test_excluded_algorithms_are_not_on_the_list(self):
        self.assertEqual(sorted(set(RASTER_EXCLUDED) & set(ALLOWED_ALGORITHM_IDS)), [])
        self.assertEqual([k for k, v in RASTER_EXCLUDED.items() if len(v) < 10], [])

    def test_family_is_on_the_list_with_names(self):
        self.assertTrue(set(RASTER_FAMILY) <= set(ALLOWED_ALGORITHM_IDS))
        self.assertTrue(set(RASTER_FAMILY) <= set(FAMILY_NAMES))
        self.assertTrue(all(v for v in RASTER_FAMILY.values()))

    def test_raw_gdal_options_are_refused_for_the_family_only(self):
        for key in ("OPTIONS", "CREATION_OPTIONS", "options"):
            self.assertIn("raw GDAL", parameter_violation("gdal:sieve", {key: "COMPRESS=LZW"}) or "")
        self.assertIsNotNone(parameter_violation("gdal:sieve", {"EXTRA": "-x"}))
        self.assertIsNone(parameter_violation("gdal:sieve", {"INPUT": "dem", "THRESHOLD": 10}))
        self.assertEqual(sorted(RASTER_ALGORITHM_IDS), sorted(RASTER_FAMILY))

    def test_a_layer_list_parameter_resolves_each_name_but_a_field_list_does_not(self):
        layers = {"a": object(), "b": object()}
        with patch("cartogen_ai.core.agent.tools.processing_allowlist_tools._find_layer_by_name", side_effect=layers.get):
            out = _resolve_params({"LAYERS": ["a", "b", "missing"], "FIELDS": ["a", "b"]}, destination_keys=set(), raster_keys=set(),
                                  layer_list_keys={"LAYERS"})
        self.assertIs(out["LAYERS"][0], layers["a"])
        self.assertIs(out["LAYERS"][1], layers["b"])
        self.assertEqual(out["LAYERS"][2], "missing")
        self.assertEqual(out["FIELDS"], ["a", "b"])


    def test_a_raster_stack_refuses_vector_layers_before_running(self):
        from cartogen_ai.core.agent.tools import processing_allowlist_tools as tools

        class Raster:
            def name(self):
                return "dem"

        class Vector:
            def name(self):
                return "pts"

        with patch.object(tools, "QgsRasterLayer", Raster, create=True):
            self.assertIsNone(tools._raster_list_violation("native:cellstackpercentile", {"INPUT": [Raster(), Raster()]}, {"INPUT"}))
            message = tools._raster_list_violation("native:cellstackpercentile", {"INPUT": [Raster(), Vector(), "missing"]}, {"INPUT"})
            self.assertIn("raster layers only", message)
            self.assertIn("pts", message)
            self.assertIn("missing", message)
            # a vector overlay is not in the raster family, so its list is not touched
            self.assertIsNone(tools._raster_list_violation("native:multiunion", {"LAYERS": [Vector()]}, {"LAYERS"}))


if __name__ == "__main__":
    unittest.main()
