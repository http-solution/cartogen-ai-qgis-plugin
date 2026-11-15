"""Round-2 row A1 (2026-11-05) and the CI probe of 2026-11-06 (DEF-27): the exported legends were cut at the frame bottom while the report said content = frame
(88.0 = 88.0 mm, 35.0 = 35.0 mm). On real QGIS 4.2.2 adjustBoxSize() does nothing on the legend item, so every earlier "content" number was the frame itself;
the legend renderer's own minimumSize() is the measurement now. Offline: the pure pieces only (the live test needs QGIS)."""
import unittest

from cartogen_ai.core.agent.tools.layout_style import LEGEND_MAX_COLUMNS, LEGEND_SCALES, legend_height_measured, pick_legend_fit


class TestAnAnswerEqualToTheFrameIsNotAMeasurement(unittest.TestCase):
    def test_every_height_equal_to_the_frame_means_not_measured(self):
        self.assertFalse(legend_height_measured([(1.0, 88.0), (0.85, 88.0), (0.7, 88.0)], 88.0))

    def test_heights_that_change_with_the_scale_are_a_measurement(self):
        self.assertTrue(legend_height_measured([(1.0, 140.0), (0.85, 120.0), (0.7, 100.0)], 88.0))

    def test_a_legend_smaller_than_the_frame_is_a_measurement(self):
        self.assertTrue(legend_height_measured([(1.0, 40.0)], 88.0))

    def test_nothing_tried_is_not_measured(self):
        self.assertFalse(legend_height_measured([], 88.0))


class TestPickingScaleAndColumns(unittest.TestCase):
    def test_one_column_at_full_size_wins_when_it_fits(self):
        self.assertEqual(pick_legend_fit([(1.0, 1, 40.0), (0.85, 1, 34.0)], 50.0), (1.0, 1))

    def test_a_smaller_scale_in_one_column_is_preferred_to_more_columns(self):
        candidates = [(1.0, 1, 60.0), (0.85, 1, 51.0), (0.7, 1, 42.0), (1.0, 2, 30.0)]
        self.assertEqual(pick_legend_fit(candidates, 50.0), (0.7, 1))

    def test_columns_are_used_when_no_scale_fits_in_one(self):
        # the numbers of the CI probe: one layer of 14 classes is about 123 mm high in one column, the A3 frame is 49.5 mm
        candidates = [(1.0, 1, 123.0), (0.85, 1, 105.0), (0.7, 1, 86.0), (1.0, 2, 63.0), (0.85, 2, 54.0), (0.7, 2, 45.0)]
        self.assertEqual(pick_legend_fit(candidates, 49.5), (0.7, 2))

    def test_nothing_fits_gives_none(self):
        self.assertIsNone(pick_legend_fit([(1.0, 1, 860.0), (0.7, 4, 300.0)], 49.5))

    def test_the_search_space_is_what_the_fit_loop_assumes(self):
        self.assertEqual(list(LEGEND_SCALES), sorted(LEGEND_SCALES, reverse=True))
        self.assertGreaterEqual(LEGEND_MAX_COLUMNS, 2)


if __name__ == "__main__":
    unittest.main()
