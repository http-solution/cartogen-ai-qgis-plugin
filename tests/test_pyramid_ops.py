"""PLAN-023 R10-4: the pure pyramid levels, cell lookup and attribute-table helpers, with hand-computed known answers. No QGIS, GDAL or numpy needed."""
import unittest

from cartogen_ai.core.agent.tools import pyramid_ops as po


class TestLevels(unittest.TestCase):
    def test_default_levels_halve_while_the_smaller_side_stays_at_least_256(self):
        self.assertEqual(po.default_levels(1024, 1024), [2, 4])
        self.assertEqual(po.default_levels(4000, 3000), [2, 4, 8])        # 3000 / 8 = 375, 3000 / 16 = 187
        self.assertEqual(po.default_levels(300, 300), [])
        self.assertEqual(po.default_levels(100000, 100000), [2, 4, 8, 16, 32, 64, 128, 256])      # capped at 8 levels
        self.assertEqual(po.default_levels(100000, 600), [2])               # the smaller side decides

    def test_check_build(self):
        self.assertEqual(po.check_build(None, "average", 1024, 1024), ([2, 4], None))
        self.assertEqual(po.check_build([2, 8], "MODE", 5000, 5000), ([2, 8], None))
        self.assertEqual(po.check_build([2.0, 4], "nearest", 5000, 5000), ([2, 4], None))
        for args in ((None, "average", 300, 300), (None, "fancy", 1024, 1024), ([1, 2], "average", 5000, 5000), ([4, 2], "average", 5000, 5000), ([2, 2], "average", 5000, 5000),
                     ([2.5], "average", 5000, 5000), (["2"], "average", 5000, 5000), ([], "average", 5000, 5000), (list(range(2, 12)), "average", 5000, 5000),
                     (None, "average", 20000, 20000), ([True], "average", 5000, 5000)):
            self.assertIsNotNone(po.check_build(*args)[1], args)


class TestCell(unittest.TestCase):
    gt = (500000.0, 10.0, 0.0, 4000040.0, 0.0, -10.0)

    def test_the_known_cell(self):
        self.assertEqual(po.cell_index(self.gt, 500025.0, 4000015.0, 4, 4), (2, 2))
        self.assertEqual(po.cell_index(self.gt, 500000.0, 4000040.0, 4, 4), (0, 0))              # the top-left corner belongs to the first cell
        self.assertEqual(po.cell_index(self.gt, 500039.9, 4000000.1, 4, 4), (3, 3))

    def test_outside_has_no_cell(self):
        for point in ((499999.0, 4000020.0), (500040.0, 4000020.0), (500010.0, 4000041.0), (500010.0, 4000000.0)):
            self.assertIsNone(po.cell_index(self.gt, *point, 4, 4), point)


class TestRat(unittest.TestCase):
    def test_rows_are_named_and_capped(self):
        out = po.rat_table(["Value", "Class"], [[1, "Forest"], [2, "Crops"]])
        self.assertEqual(out, {"columns": ["Value", "Class"], "rows": [{"Value": 1, "Class": "Forest"}, {"Value": 2, "Class": "Crops"}], "total_rows": 2, "truncated": False})
        big = po.rat_table(["v"], [[i] for i in range(250)])
        self.assertEqual((len(big["rows"]), big["total_rows"], big["truncated"]), (200, 250, True))


if __name__ == "__main__":
    unittest.main()
