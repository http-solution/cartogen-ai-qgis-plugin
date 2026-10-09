# -*- coding: utf-8 -*-
"""Pure checks of fetch_dem's planning rules (tile names, tile selection, size limits). No network, no QGIS."""
import unittest

from cartogen_ai.core.agent.tools import dem_tools as d


class TestDemPlanning(unittest.TestCase):
    def test_tile_names_match_the_published_scheme(self):
        self.assertEqual(d.tile_name(15, 45), "Copernicus_DSM_COG_10_N15_00_E045_00_DEM")
        self.assertEqual(d.tile_name(-3, -70), "Copernicus_DSM_COG_10_S03_00_W070_00_DEM")
        self.assertTrue(d.tile_url(15, 45, base="http://x/").startswith("http://x/Copernicus_DSM_COG_10_N15_00_E045_00_DEM/"))

    def test_edge_on_a_tile_boundary_does_not_add_a_tile(self):
        self.assertEqual(d.tiles_for_bbox(45.0, 15.0, 46.0, 16.0), [(15, 45)])
        self.assertEqual(len(d.tiles_for_bbox(44.5, 14.5, 45.5, 15.5)), 4)

    def test_negative_coordinates_floor_correctly(self):
        self.assertEqual(d.tiles_for_bbox(-0.5, -0.5, 0.5, 0.5), [(-1, -1), (-1, 0), (0, -1), (0, 0)])

    def test_centre_box_is_symmetric(self):
        w, s, e, n = d.bbox_from_centre(15.0, 45.0, 10)
        self.assertAlmostEqual((w + e) / 2, 45.0)
        self.assertAlmostEqual((s + n) / 2, 15.0)
        self.assertAlmostEqual((n - s) * 111.32 / 2, 10, places=3)

    def test_bad_boxes_are_refused(self):
        self.assertIsNotNone(d.validate_bbox(46, 15, 45, 16))
        self.assertIsNotNone(d.validate_bbox("a", 1, 2, 3))
        self.assertIsNone(d.validate_bbox(45, 15, 46, 16))

    def test_oversized_areas_are_refused_with_the_numbers(self):
        problem, _ = d.plan_download(40, 10, 50, 20)
        self.assertIn("tiles", problem)
        problem, tiles = d.plan_download(45.0, 15.0, 46.9, 16.4)
        self.assertIsNone(problem)
        self.assertEqual(len(tiles), 2 * 2)
        self.assertIsNone(d.plan_download(45.0, 15.0, 45.5, 15.5)[0])

    def test_cell_limit(self):
        old = d.MAX_CELLS
        d.MAX_CELLS = 1000
        try:
            self.assertIn("cells", d.plan_download(45, 15, 45.5, 15.5)[0])
        finally:
            d.MAX_CELLS = old


if __name__ == "__main__":
    unittest.main()
