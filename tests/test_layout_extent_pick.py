"""GitHub #129, rc48 OI-129: after Zoom Full the layout's main frame must show the vector layers, not the DEM that fills the project (pure)."""
import unittest

from cartogen_ai.core.agent.tools.layout_tools import pick_layout_extent

FULL = (0.0, 0.0, 100.0, 100.0)          # the DEM
NETWORK = (40.0, 40.0, 60.0, 60.0)       # the roads and facilities


class TestPickLayoutExtent(unittest.TestCase):
    def test_zoom_full_with_a_small_network_frames_the_network_with_a_margin(self):
        box = pick_layout_extent(FULL, FULL, NETWORK)
        self.assertEqual(box, (39.0, 39.0, 61.0, 61.0))

    def test_a_canvas_zoomed_in_by_the_user_is_followed(self):
        self.assertIsNone(pick_layout_extent((45.0, 45.0, 55.0, 55.0), FULL, NETWORK))

    def test_vectors_that_fill_most_of_the_project_leave_the_canvas_alone(self):
        self.assertIsNone(pick_layout_extent(FULL, FULL, (5.0, 5.0, 95.0, 95.0)))

    def test_nothing_to_frame_leaves_the_canvas_alone(self):
        self.assertIsNone(pick_layout_extent(FULL, FULL, None))
        self.assertIsNone(pick_layout_extent(None, FULL, NETWORK))
        self.assertIsNone(pick_layout_extent(FULL, None, NETWORK))

    def test_a_canvas_slightly_wider_than_the_data_still_counts_as_zoom_full(self):
        wide = (-20.0, 0.0, 120.0, 100.0)        # Zoom Full pads to the window's aspect ratio
        self.assertIsNotNone(pick_layout_extent(wide, FULL, NETWORK))

    def test_a_single_point_has_no_area_so_it_is_not_framed_here(self):
        self.assertIsNone(pick_layout_extent(FULL, FULL, (50.0, 50.0, 50.0, 50.0)))


class TestTheSmokeDataExtents(unittest.TestCase):
    """DEF-37, second half (round-3 row E3): the tester saw the main frame show the whole DEM and called it a miss. With the layers the row loaded the rule is
    right to leave it: smoke_admin and smoke_zones cover 92 % of the DEM's area. The extents are those of docs/release_smoke_assets/inputs (EPSG:32636)."""

    DEM = (775566.22, 3537606.55, 778791.50, 3540801.64)
    ADMIN = (775580.06, 3537720.00, 778778.60, 3540688.16)        # smoke_admin and smoke_zones
    ROADS = (775900.0, 3538000.0, 778300.0, 3540400.0)            # smoke_roads: 56 % of the DEM, so not under half either
    POINTS = (776207.24, 3538400.74, 778059.30, 3539893.78)       # smoke_points: 27 % of the DEM

    def test_the_layers_row_e3_loaded_fill_too_much_of_the_project_to_be_framed(self):
        self.assertIsNone(pick_layout_extent(self.DEM, self.DEM, self.ADMIN))
        union = (min(self.ADMIN[0], self.ROADS[0]), min(self.ADMIN[1], self.ROADS[1]), max(self.ADMIN[2], self.ROADS[2]), max(self.ADMIN[3], self.ROADS[3]))
        self.assertIsNone(pick_layout_extent(self.DEM, self.DEM, union))

    def test_roads_alone_are_still_over_half_the_project(self):
        self.assertIsNone(pick_layout_extent(self.DEM, self.DEM, self.ROADS))

    def test_with_only_the_points_and_the_dem_visible_the_frame_follows_the_points(self):
        box = pick_layout_extent(self.DEM, self.DEM, self.POINTS)
        self.assertIsNotNone(box)
        self.assertLess(box[2] - box[0], (self.DEM[2] - self.DEM[0]) * 0.65)
        self.assertLessEqual(box[0], self.POINTS[0])
        self.assertGreaterEqual(box[2], self.POINTS[2])


if __name__ == "__main__":
    unittest.main()
