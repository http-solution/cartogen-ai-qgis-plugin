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


if __name__ == "__main__":
    unittest.main()
