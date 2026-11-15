# -*- coding: utf-8 -*-
"""
Tests for antimeridian bounding-box support in hazard monitoring tools.
"""

import unittest
from cartogen_ai.core.agent.tools.hazard_monitoring_tools import _validate_bbox, _point_in_bbox


class TestAntimeridianBbox(unittest.TestCase):
    def test_standard_bbox(self):
        bbox = [10.0, 20.0, 30.0, 40.0]
        self.assertIsNone(_validate_bbox(bbox))
        self.assertTrue(_point_in_bbox(20.0, 30.0, bbox))
        self.assertFalse(_point_in_bbox(5.0, 30.0, bbox))

    def test_antimeridian_crossing_bbox(self):
        # Fiji / Pacific region: spans from 170°E to -170°W (190°E)
        bbox = [170.0, -25.0, -170.0, -10.0]
        # Should now be valid (not rejected with min_lon >= max_lon error)
        self.assertIsNone(_validate_bbox(bbox))
        
        # Point in eastern hemisphere portion (e.g. 175°E, -15°S) -> should be inside
        self.assertTrue(_point_in_bbox(175.0, -15.0, bbox))
        # Point in western hemisphere portion (e.g. -175°W, -15°S) -> should be inside
        self.assertTrue(_point_in_bbox(-175.0, -15.0, bbox))
        # Point outside (e.g. 150°E, -15°S or 0°E, -15°S) -> should be outside
        self.assertFalse(_point_in_bbox(150.0, -15.0, bbox))
        self.assertFalse(_point_in_bbox(0.0, -15.0, bbox))


if __name__ == "__main__":
    unittest.main()
