"""DEF-30 (round-3 smoke row B6): an algorithm that declares an output layer but made none must not be reported as a plain success."""
import unittest

from cartogen_ai.core.agent.tools.processing_allowlist_tools import no_layer_result

MESH = "native:meshrasterize"


class TestNoLayerResult(unittest.TestCase):
    def test_a_missing_raster_says_no_layer_was_made_and_names_the_cell_size(self):
        r = no_layer_result(MESH, {"OUTPUT"}, {"OUTPUT"}, {"INPUT", "PIXEL_SIZE", "OUTPUT"})
        self.assertTrue(r["success"])
        self.assertIs(r["layer_created"], False)
        self.assertIn("NO layer", r["message"])
        self.assertIn("PIXEL_SIZE", r["message"])
        self.assertIn("degrees", r["message"])
        self.assertNotIn("ran successfully", r["message"])

    def test_a_missing_vector_says_no_layer_without_the_cell_size_hint(self):
        r = no_layer_result("native:buffer", {"OUTPUT"}, set(), {"INPUT", "DISTANCE", "OUTPUT"})
        self.assertIs(r["layer_created"], False)
        self.assertIn("NO layer", r["message"])
        self.assertNotIn("cell size", r["message"].lower())

    def test_a_raster_without_a_cell_size_parameter_gets_no_hint(self):
        r = no_layer_result("gdal:slope", {"OUTPUT"}, {"OUTPUT"}, {"INPUT", "OUTPUT"})
        self.assertNotIn("cell size", r["message"].lower())

    def test_an_algorithm_with_no_layer_destination_keeps_the_old_wording(self):
        r = no_layer_result("native:selectbyexpression", set(), set(), {"INPUT", "EXPRESSION"})
        self.assertEqual(r["message"], "'native:selectbyexpression' ran successfully with no new layer output.")
        self.assertNotIn("layer_created", r)

    def test_unknown_definition_keeps_the_old_wording(self):
        self.assertNotIn("layer_created", no_layer_result("x:y", set(), None, None))


if __name__ == "__main__":
    unittest.main()
