"""Round-2 row A1 (2026-11-05): the exported legends were cut at the frame bottom while the report said content = frame (88.0 = 88.0 mm, 35.0 = 35.0 mm).
The legend is fixed-size (resizeToContents off), so adjustBoxSize() left the frame size in place and the check compared the frame with itself.
Offline: the legend is a fake that, like QGIS, resizes in adjustBoxSize() only when it resizes to contents."""
import unittest

from cartogen_ai.core.agent.tools.layout_style import legend_height_measured, measure_legend_content


class FakeLegend:
    def __init__(self, frame_h, needs_h, resize_to_contents=False):
        self.height, self.needs, self.resize = frame_h, needs_h, resize_to_contents

    def resizeToContents(self):
        return self.resize

    def setResizeToContents(self, value):
        self.resize = value

    def adjustBoxSize(self):
        if self.resize:
            self.height = self.needs

    def rect(self):
        return self

    def __getattr__(self, name):
        if name == "height":
            raise AttributeError
        raise AttributeError(name)


class _Rect:
    pass


def legend(frame_h, needs_h):
    fake = FakeLegend(frame_h, needs_h)
    fake.rect = lambda: types_rect(fake.height)
    return fake


def types_rect(height):
    rect = _Rect()
    rect.height = lambda: height
    return rect


class TestMeasuringAFixedSizeLegend(unittest.TestCase):
    def test_a_fixed_size_legend_is_measured_at_what_its_content_needs(self):
        fake = legend(35.0, 140.0)
        self.assertEqual(measure_legend_content(fake), 140.0)

    def test_the_resize_switch_is_put_back(self):
        fake = legend(35.0, 140.0)
        measure_legend_content(fake)
        self.assertFalse(fake.resizeToContents())

    def test_the_switch_is_put_back_even_when_sizing_fails(self):
        fake = legend(35.0, 140.0)

        def boom():
            raise RuntimeError("boom")
        fake.adjustBoxSize = boom
        with self.assertRaises(RuntimeError):
            measure_legend_content(fake)
        self.assertFalse(fake.resizeToContents())


class TestAnAnswerEqualToTheFrameIsNotAMeasurement(unittest.TestCase):
    def test_every_height_equal_to_the_frame_means_not_measured(self):
        self.assertFalse(legend_height_measured([(1.0, 88.0), (0.85, 88.0), (0.7, 88.0)], 88.0))

    def test_heights_that_change_with_the_scale_are_a_measurement(self):
        self.assertTrue(legend_height_measured([(1.0, 140.0), (0.85, 120.0), (0.7, 100.0)], 88.0))

    def test_a_legend_smaller_than_the_frame_is_a_measurement(self):
        self.assertTrue(legend_height_measured([(1.0, 40.0)], 88.0))

    def test_nothing_tried_is_not_measured(self):
        self.assertFalse(legend_height_measured([], 88.0))


if __name__ == "__main__":
    unittest.main()
