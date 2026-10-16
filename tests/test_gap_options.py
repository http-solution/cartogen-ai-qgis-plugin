import unittest

from cartogen_ai.core.agent.tools.gap_options import (check_box, check_chart, check_layer_elevation, check_profile_line, check_terrain)


class TestGapOptions(unittest.TestCase):
    def test_box(self):
        self.assertEqual(check_box(10, 20, 100, 80)[0]["width_mm"], 100.0)
        for bad in ((10, 20, 5, 80), (-1, 0, 50, 50), ("a", 0, 50, 50), (0, 0, 50, 5000)):
            self.assertIsNone(check_box(*bad)[0], bad)

    def test_chart(self):
        out, err = check_chart("L", "Bar", "name", "pop", "CHART1")
        self.assertIsNone(err)
        self.assertEqual((out["chart_type"], out["x_field"]), ("bar", "name"))
        for bad in (("L", "radar", "a", "b"), ("L", "bar", '"a" + 1', "b"), ("L", "bar", "a", "b); DROP"), ("L", "bar", "a", "b", "bad id!")):
            self.assertIsNone(check_chart(*bad)[0], bad)

    def test_profile_line(self):
        self.assertEqual(check_profile_line(0, 0, 10, 5)[0], ((0.0, 0.0), (10.0, 5.0)))
        self.assertIsNone(check_profile_line(1, 1, 1, 1)[0])
        self.assertIsNone(check_profile_line("x", 1, 2, 3)[0])

    def test_layer_elevation(self):
        out, err = check_layer_elevation(True, "surface", 1, 5, 2, None, None)
        self.assertIsNone(err)
        self.assertEqual((out["enabled"], out["mode"], out["band"]), (True, "surface", 1.0))
        self.assertIsNone(check_layer_elevation(None, None, None, None, None, None, None)[0])
        self.assertIsNone(check_layer_elevation(None, "weird", None, None, None, None, None)[0])
        self.assertIsNone(check_layer_elevation(None, None, None, None, None, "up", None)[0])
        self.assertIsNone(check_layer_elevation(None, None, 0, None, None, None, None)[0])

    def test_terrain(self):
        self.assertEqual(check_terrain("flat", 10, None)[0], {"source": "flat", "offset": 10.0})
        self.assertEqual(check_terrain("DEM", None, 1.5)[0]["scale"], 1.5)
        self.assertIsNone(check_terrain("sphere", None, None)[0])
        self.assertIsNone(check_terrain("dem", "x", None)[0])


if __name__ == "__main__":
    unittest.main()
