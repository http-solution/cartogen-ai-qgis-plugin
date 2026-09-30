# -*- coding: utf-8 -*-
"""rc7 smoke test F15: ~130 'There is no route from start point ... to end point ...' lines were logged at CRITICAL
for facilities the road network never reaches. They are counted instead (see _CollectingFeedback)."""
import unittest

from cartogen_ai.core.agent.tools import _background_processing as bg


class TestNoRouteMessage(unittest.TestCase):
    def test_the_qgis_message_is_recognised(self):
        self.assertTrue(bg.is_no_route_message("There is no route from start point (44.0, 15.9) to end point (54.0, 12.6)."))

    def test_other_errors_are_not(self):
        self.assertFalse(bg.is_no_route_message("Could not load source layer for INPUT"))
        self.assertFalse(bg.is_no_route_message(""))
        self.assertFalse(bg.is_no_route_message(None))

    def test_new_feedback_is_none_outside_qgis(self):
        if not bg.QGIS_AVAILABLE:
            self.assertIsNone(bg.new_feedback())


if __name__ == "__main__":
    unittest.main()
