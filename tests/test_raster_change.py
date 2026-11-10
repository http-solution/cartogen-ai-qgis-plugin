"""PLAN-023 R3-4: from-to change matrix, hand-computed known answers. Pure numpy: skipped where numpy is missing (the CI test job installs it)."""
import math
import unittest

try:
    import numpy as np
    HAVE_NUMPY = True
except ImportError:
    HAVE_NUMPY = False

from cartogen_ai.core.agent.tools import raster_change as rc

ALL = np.ones((2, 2), dtype=bool) if HAVE_NUMPY else None


@unittest.skipUnless(HAVE_NUMPY, "numpy not installed")
class TestKnownAnswers(unittest.TestCase):
    def test_the_plans_two_by_two_example(self):
        # A = [[1, 1], [2, 2]] -> B = [[1, 2], [2, 2]]: the top-right cell changed 1 -> 2
        tab = rc.cross_tab(np.array([[1, 1], [2, 2]]), np.array([[1, 2], [2, 2]]), ALL)
        self.assertEqual(tab["classes"], [1, 2])
        self.assertEqual(tab["counts"].tolist(), [[1, 1], [0, 2]])
        per_class, transitions, totals = rc.summarise(tab)
        one, two = per_class
        self.assertEqual((one["loss"], one["gain"], one["persistence"], one["net"]), (1, 0, 1, -1))     # class 1 lost 1 cell
        self.assertEqual((two["loss"], two["gain"], two["persistence"], two["net"]), (0, 1, 2, 1))      # class 2 gained 1 cell
        self.assertEqual(totals["changed_cells"], 1)
        self.assertEqual(totals["percent_changed"], 25.0)
        self.assertEqual([(t["from"], t["to"], t["cells"]) for t in transitions], [(1, 1, 1), (1, 2, 1), (2, 2, 2)])

    def test_the_net_change_of_all_classes_sums_to_zero(self):
        rng = np.random.RandomState(3)
        a, b = rng.randint(1, 5, (12, 12)), rng.randint(1, 5, (12, 12))
        per_class, _t, totals = rc.summarise(rc.cross_tab(a, b, np.ones((12, 12), dtype=bool)))
        self.assertEqual(sum(c["net"] for c in per_class), 0)
        self.assertEqual(sum(c["loss"] for c in per_class), sum(c["gain"] for c in per_class))
        self.assertEqual(totals["valid_cells"], 144)

    def test_a_class_present_in_only_one_raster_still_gets_a_row(self):
        tab = rc.cross_tab(np.array([[1, 1], [1, 1]]), np.array([[1, 3], [3, 3]]), ALL)
        self.assertEqual(tab["classes"], [1, 3])
        self.assertEqual(tab["counts"].tolist(), [[1, 3], [0, 0]])
        per_class, _t, _totals = rc.summarise(tab)
        self.assertEqual((per_class[1]["cells_before"], per_class[1]["cells_after"], per_class[1]["gain"]), (0, 3, 3))


@unittest.skipUnless(HAVE_NUMPY, "numpy not installed")
class TestHectares(unittest.TestCase):
    def test_projected_cells_30_m_are_0_09_ha(self):
        # 30 m x 30 m = 900 m2 = 0.09 ha
        self.assertEqual(rc.row_areas_ha((500000.0, 30.0, 0.0, 4000000.0, 0.0, -30.0), 3, False), [0.09, 0.09, 0.09])

    def test_projected_cells_in_feet_use_the_unit_factor(self):
        # 100 ft x 100 ft at 0.3048 m per foot = 30.48 x 30.48 = 929.0304 m2 = 0.09290304 ha
        areas = rc.row_areas_ha((0.0, 100.0, 0.0, 0.0, 0.0, -100.0), 1, False, 0.3048)
        self.assertAlmostEqual(areas[0], 0.09290304, places=8)

    def test_a_geographic_one_degree_cell_at_the_equator_is_about_1_236_million_ha(self):
        # R^2 x (pi / 180) x sin(1 degree) with R = 6,371,007.2 m = 1.2364e10 m2 = 1.2364e6 ha
        area = rc.row_areas_ha((0.0, 1.0, 0.0, 1.0, 0.0, -1.0), 1, True)[0]
        self.assertAlmostEqual(area, 6371007.2 ** 2 * math.radians(1.0) * math.sin(math.radians(1.0)) / 1e4, delta=1.0)
        self.assertTrue(1.2360e6 < area < 1.2370e6, area)

    def test_a_geographic_cell_at_60_degrees_is_about_half_the_equatorial_one(self):
        # area is proportional to cos(latitude): the 59.5 to 60.5 degree row is cos(60) = 0.5 of the equatorial row
        equator = rc.row_areas_ha((0.0, 1.0, 0.0, 0.5, 0.0, -1.0), 1, True)[0]
        sixty = rc.row_areas_ha((0.0, 1.0, 0.0, 60.5, 0.0, -1.0), 1, True)[0]
        self.assertAlmostEqual(sixty / equator, 0.5, delta=0.001)

    def test_a_crs_that_is_neither_gives_no_areas(self):
        self.assertIsNone(rc.row_areas_ha((0.0, 1.0, 0.0, 0.0, 0.0, -1.0), 2, None))

    def test_hectares_follow_the_cells_by_row_and_by_class(self):
        # row 0 cells are 1 ha, row 1 cells 3 ha: the one 1 -> 2 cell is in row 0
        tab = rc.cross_tab(np.array([[1, 1], [2, 2]]), np.array([[1, 2], [2, 2]]), ALL, row_ha=[1.0, 3.0])
        self.assertEqual(tab["hectares"].tolist(), [[1.0, 1.0], [0.0, 6.0]])
        per_class, _t, totals = rc.summarise(tab)
        self.assertEqual((per_class[0]["ha_loss"], per_class[1]["ha_gain"], per_class[1]["ha_net"]), (1.0, 1.0, 1.0))
        self.assertEqual((totals["hectares"], totals["changed_hectares"]), (8.0, 1.0))


@unittest.skipUnless(HAVE_NUMPY, "numpy not installed")
class TestNoDataAndErrors(unittest.TestCase):
    def test_cells_invalid_in_either_raster_are_left_out(self):
        valid = np.array([[True, False], [True, True]])
        tab = rc.cross_tab(np.array([[1, 1], [2, 2]]), np.array([[1, 2], [2, np.nan]]), valid)
        self.assertEqual(tab["valid_cells"], 2)
        self.assertEqual(tab["counts"].tolist(), [[1, 0], [0, 1]])

    def test_non_whole_values_and_too_many_classes_are_refused_in_plain_words(self):
        with self.assertRaises(ValueError) as ctx:
            rc.cross_tab(np.array([[1.5, 2.0]]), np.array([[1.0, 2.0]]), np.ones((1, 2), dtype=bool))
        self.assertIn("reclassify", str(ctx.exception))
        with self.assertRaises(ValueError) as ctx:
            rc.cross_tab(np.arange(60).reshape(6, 10), np.arange(60).reshape(6, 10), np.ones((6, 10), dtype=bool))
        self.assertIn("50 classes", str(ctx.exception))

    def test_nothing_valid_gives_an_empty_matrix(self):
        tab = rc.cross_tab(np.array([[1]]), np.array([[1]]), np.array([[False]]))
        self.assertEqual((tab["classes"], tab["valid_cells"]), ([], 0))
        per_class, transitions, totals = rc.summarise(tab)
        self.assertEqual((per_class, transitions, totals["valid_cells"]), ([], [], 0))


class TestParseClasses(unittest.TestCase):
    def test_mappings_lists_and_nothing(self):
        self.assertEqual(rc.parse_classes({"1": "Forest", 2: "Cropland"}), ({1: "Forest", 2: "Cropland"}, None))
        self.assertEqual(rc.parse_classes([{"value": 10, "name": " Tree cover "}]), ({10: "Tree cover"}, None))
        self.assertEqual(rc.parse_classes(None), ({}, None))
        self.assertEqual(rc.parse_classes({}), ({}, None))

    def test_bad_class_tables_are_refused(self):
        self.assertIn("not a number", rc.parse_classes({"forest": "x"})[1])
        self.assertIn("whole number", rc.parse_classes({"1.5": "x"})[1])
        self.assertIn("{\"value\"", rc.parse_classes([{"name": "x"}])[1])
        self.assertIn("mapping", rc.parse_classes("forest")[1])

    def test_long_names_are_cut(self):
        self.assertEqual(len(rc.parse_classes({1: "x" * 100})[0][1]), 60)


if __name__ == "__main__":
    unittest.main()
