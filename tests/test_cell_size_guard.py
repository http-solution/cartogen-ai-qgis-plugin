"""A raster cell size larger than the whole input layer is refused before the algorithm runs (DEF-30, row B6; the QGIS 4.2.2 answer was a cryptic 'writeBlock() called on read-only provider').
Uses stand-in layer objects, so it runs without QGIS."""
import types
import unittest

from cartogen_ai.core.agent.tools import processing_allowlist_tools as pat


def _layer(width, height, authid="EPSG:4326", valid=True, name="smoke_mesh"):
    ext = types.SimpleNamespace(width=lambda: width, height=lambda: height)
    crs = types.SimpleNamespace(isValid=lambda: valid, authid=lambda: authid)
    return types.SimpleNamespace(extent=lambda: ext, crs=lambda: crs, name=lambda: name)


class TestCellSizeGuard(unittest.TestCase):
    def test_a_cell_larger_than_the_layer_is_refused_with_a_suggestion(self):
        msg = pat.cell_size_violation("native:meshrasterize", {"INPUT": _layer(0.01, 0.01), "PIXEL_SIZE": 5})
        self.assertIn("larger than the whole of 'smoke_mesh'", msg)
        self.assertIn("Nothing was run", msg)
        self.assertIn("0.0001", msg)

    def test_a_sensible_cell_is_left_alone(self):
        self.assertIsNone(pat.cell_size_violation("native:meshrasterize", {"INPUT": _layer(0.01, 0.01), "PIXEL_SIZE": 0.001}))

    def test_other_algorithms_and_unreadable_input_are_not_judged(self):
        self.assertIsNone(pat.cell_size_violation("native:buffer", {"INPUT": _layer(0.01, 0.01), "PIXEL_SIZE": 5}))
        self.assertIsNone(pat.cell_size_violation("native:meshrasterize", {"INPUT": "a name", "PIXEL_SIZE": 5}))

    def test_a_different_output_crs_is_never_refused_by_mistake(self):
        params = {"INPUT": _layer(0.01, 0.01, "EPSG:4326"), "PIXEL_SIZE": 5, "CRS_OUTPUT": "EPSG:32638"}     # 5 metres on a degrees layer is fine
        self.assertIsNone(pat.cell_size_violation("native:meshrasterize", params))

    def test_a_layer_with_no_crs_is_judged_in_its_own_units(self):
        msg = pat.cell_size_violation("native:meshrasterize", {"INPUT": _layer(0.01, 0.01, "", valid=False), "PIXEL_SIZE": 5, "CRS_OUTPUT": "EPSG:4326"})
        self.assertIn("larger than the whole", msg)

    def test_the_gate_runs_it(self):
        with self.assertRaises(ValueError):
            pat._check_raster_lists("native:meshrasterize", {"INPUT": _layer(0.01, 0.01), "PIXEL_SIZE": 5}, ())


if __name__ == "__main__":
    unittest.main()
