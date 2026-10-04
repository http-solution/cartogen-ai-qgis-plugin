# -*- coding: utf-8 -*-
"""H2 generate_mapping_task_grid: grid, ranking, GeoJSON and validation are pure; the layer work is in test_task_grid_tools_live.py."""
import json
import unittest

from cartogen_ai.core.agent.tools import task_grid_tools as g


class TestGridCells(unittest.TestCase):
    def test_exact_fit(self):
        cells = g.grid_cells(0, 0, 4000, 2000, 1000)
        self.assertEqual(len(cells), 8)
        self.assertEqual(cells[0]["bounds"], (0, 0, 1000, 1000))
        self.assertEqual(cells[-1]["bounds"], (3000, 1000, 4000, 2000))

    def test_partial_cells_extend_past_the_box(self):
        cells = g.grid_cells(0, 0, 1500, 500, 1000)
        self.assertEqual(len(cells), 2)
        self.assertEqual(cells[1]["bounds"][2], 2000)

    def test_degenerate_box_still_gives_one_cell(self):
        self.assertEqual(len(g.grid_cells(5, 5, 5, 5, 1000)), 1)

    def test_estimate_matches_the_grid(self):
        for w, h, s in ((4000, 2000, 1000), (1500, 500, 1000), (0, 0, 1000), (12345, 9876, 777)):
            self.assertEqual(g.estimated_cells(w, h, s), len(g.grid_cells(0, 0, w, h, s)))

    def test_row_major_from_south_west(self):
        cells = g.grid_cells(0, 0, 2000, 2000, 1000)
        self.assertEqual([(c["col"], c["row"]) for c in cells], [(0, 0), (1, 0), (0, 1), (1, 1)])


class TestTaskId(unittest.TestCase):
    def test_format_is_stable_and_sortable(self):
        self.assertEqual(g.task_id(0, 0), "r001c001")
        self.assertEqual(g.task_id(11, 2), "r003c012")


class TestPriorityClasses(unittest.TestCase):
    def test_terciles(self):
        self.assertEqual(g.priority_classes([9, 8, 7, 3, 2, 1]), ["High", "High", "Medium", "Medium", "Low", "Low"])

    def test_ties_share_a_class(self):
        self.assertEqual(g.priority_classes([5, 5, 5, 5]), ["High"] * 4)

    def test_none_stays_none_and_all_none_is_all_none(self):
        self.assertEqual(g.priority_classes([None, 4, None]), [None, "High", None])
        self.assertEqual(g.priority_classes([None, None]), [None, None])

    def test_empty(self):
        self.assertEqual(g.priority_classes([]), [])

    def test_order_of_input_does_not_matter(self):
        a = g.priority_classes([1, 9, 3, 8, 2, 7])
        self.assertEqual(a, ["Low", "High", "Medium", "High", "Low", "Medium"])


class TestGeoJson(unittest.TestCase):
    def test_feature_collection(self):
        text = g.to_geojson([({"type": "Polygon", "coordinates": []}, {"task_id": "r001c001"})])
        data = json.loads(text)
        self.assertEqual(data["type"], "FeatureCollection")
        self.assertEqual(data["features"][0]["properties"]["task_id"], "r001c001")


class TestValidate(unittest.TestCase):
    def test_cell_size(self):
        self.assertIsNone(g.validate_options(100))
        self.assertIsNotNone(g.validate_options(99))
        self.assertIsNotNone(g.validate_options("big"))


class TestWiring(unittest.TestCase):
    def test_registered_as_create(self):
        from cartogen_ai.core.agent import tool_operations
        from cartogen_ai.core.agent.tools import TOOL_REGISTRY
        self.assertIn("generate_mapping_task_grid", TOOL_REGISTRY)
        self.assertEqual(tool_operations.get_tool_operation_type("generate_mapping_task_grid"), tool_operations.CREATE)

    def test_validation_runs_before_qgis_is_needed(self):
        if g.QGIS_AVAILABLE:
            self.skipTest("QGIS present")
        self.assertIn("error", g.generate_mapping_task_grid("aoi", cell_size_m=10))


if __name__ == "__main__":
    unittest.main()
