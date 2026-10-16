import unittest

from cartogen_ai.core.agent.tools.layout_extra_options import check_atlas, check_export_extras, check_guides_grid, check_overview


class OverviewTests(unittest.TestCase):
    def test_overview(self):
        out, err = check_overview("MAP_INSET", "MAP_MAIN", color="red", width_mm=0.5)
        self.assertIsNone(err)
        self.assertEqual(out["extent_map_id"], "MAP_MAIN")
        self.assertIsNone(check_overview(None, "MAP_MAIN", inset_box={"x_mm": 5, "y_mm": 5, "width_mm": 50, "height_mm": 40})[1])
        for args in (("A", "A"), (None, None), ("bad id!", "B"), ("A", "B", None, 99), (None, "B", None, None, {"x_mm": 1}),
                     (None, "B", None, None, "box")):
            self.assertIsNotNone(check_overview(*args)[1], args)


class GuidesTests(unittest.TestCase):
    def test_guides_and_grid(self):
        out, err = check_guides_grid(guides=[{"orientation": "V", "position_mm": 20}, {"orientation": "horizontal", "position_mm": 10.5}],
                                     grid_mm=5, snap_to_grid=True)
        self.assertIsNone(err)
        self.assertEqual(out["guides"][0]["orientation"], "Vertical")
        for kwargs in ({}, {"guides": "x"}, {"guides": [{"orientation": "diagonal", "position_mm": 1}]},
                       {"guides": [{"orientation": "v", "position_mm": -3}]}, {"guides": [{"orientation": "v"}] * 31}, {"grid_mm": 0},
                       {"snap_to_grid": "yes"}):
            self.assertIsNotNone(check_guides_grid(**kwargs)[1], kwargs)


class AtlasTests(unittest.TestCase):
    def test_atlas(self):
        out, err = check_atlas("districts", page_name_field="name", margin_percent=10, scaling="Auto", hide_coverage=True)
        self.assertIsNone(err)
        self.assertEqual(out["scaling"], "auto")
        self.assertTrue(check_atlas("x", disable=True)[0]["disable"])
        for kwargs in ({"coverage_layer": ""}, {"coverage_layer": "a", "page_name_field": "a;b"}, {"coverage_layer": "a", "scaling": "zoom"},
                       {"coverage_layer": "a", "margin_percent": -1}, {"coverage_layer": "a", "hide_coverage": 1},
                       {"coverage_layer": "a", "map_item_id": "bad id!"}):
            self.assertIsNotNone(check_atlas(**kwargs)[1], kwargs)


class ExportTests(unittest.TestCase):
    def test_extras(self):
        self.assertIsNone(check_export_extras("image", True, False))
        self.assertIsNone(check_export_extras("pdf", False, True))
        self.assertIsNotNone(check_export_extras("pdf", True, False))
        self.assertIsNotNone(check_export_extras("svg", False, True))


if __name__ == "__main__":
    unittest.main()
