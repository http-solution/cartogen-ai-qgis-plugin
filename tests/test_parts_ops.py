"""PLAN-023 R9-2: the pure part-and-ring helpers, with the plan's square and hole as the known answer. No QGIS and no numpy needed."""
import unittest

from cartogen_ai.core.agent.tools import parts_ops as po
from cartogen_ai.core.agent.tools.vertex_ops import ring_area

HOLE = "POLYGON((3 3,3 7,7 7,7 3,3 3))"                           # side 4, area 16, inside a 10 x 10 square


class TestKnownAnswers(unittest.TestCase):
    def test_a_hole_of_side_4_takes_the_square_from_100_to_84_and_filling_it_restores_100(self):
        kind, rings, problem = po.parse_wkt(HOLE)
        self.assertEqual((kind, problem), ("POLYGON", None))
        hole = ring_area(rings[0])
        self.assertEqual(hole, 16.0)
        self.assertEqual(100.0 - hole, 84.0)
        self.assertEqual(84.0 + hole, 100.0)

    def test_a_line_and_two_rings_are_read(self):
        self.assertEqual(po.parse_wkt("linestring(0 0, 3 4)")[:2], ("LINESTRING", [[(0.0, 0.0), (3.0, 4.0)]]))
        kind, rings, _ = po.parse_wkt("POLYGON((0 0,10 0,10 10,0 0),(1 1,2 1,2 2,1 1))")
        self.assertEqual((kind, len(rings)), ("POLYGON", 2))


class TestParse(unittest.TestCase):
    def test_what_is_not_supported_is_refused_with_the_reason(self):
        for text in ("", None, "POINT(1 1)", "MULTIPOLYGON(((0 0,1 0,1 1,0 0)))", "POLYGON Z((0 0 0,1 0 0,1 1 0,0 0 0))", "POLYGON((0 0,1 a,1 1,0 0))", "POLYGON((0 0 5,1 0 5,1 1 5,0 0 5))"):
            self.assertIsNotNone(po.parse_wkt(text)[2], text)


class TestCheckRequest(unittest.TestCase):
    def test_valid_requests_pass(self):
        self.assertIsNone(po.check_request("add_ring", HOLE))
        self.assertIsNone(po.check_request("add_part", HOLE))
        self.assertIsNone(po.check_request("add_part", "LINESTRING(0 0,1 1)"))
        self.assertIsNone(po.check_request("fill_ring", x=5, y=5))
        self.assertIsNone(po.check_request("delete_ring", ring_index=1))
        self.assertIsNone(po.check_request("delete_part", part_index=0))

    def test_bad_requests_say_what_is_missing(self):
        cases = [
            ("explode", {}), ("add_ring", {}), ("add_ring", {"geometry_wkt": "LINESTRING(0 0,1 1)"}),
            ("add_ring", {"geometry_wkt": "POLYGON((0 0,1 0,1 1,0 1))"}), ("add_ring", {"geometry_wkt": "POLYGON((0 0,1 0,2 0,0 0))"}),
            ("add_part", {"geometry_wkt": HOLE, "part_index": 0}), ("add_ring", {"geometry_wkt": HOLE, "part_index": 0}), ("add_part", {"geometry_wkt": "LINESTRING(0 0)"}),
            ("fill_ring", {}), ("fill_ring", {"x": 1}), ("delete_ring", {}), ("delete_ring", {"ring_index": 0}), ("delete_ring", {"ring_index": -1}),
            ("delete_part", {}), ("delete_part", {"part_index": 1.5}), ("delete_part", {"part_index": 0, "ring_index": 1}),
        ]
        for action, kwargs in cases:
            self.assertIsNotNone(po.check_request(action, **kwargs), (action, kwargs))

    def test_describe(self):
        self.assertEqual(po.describe("add_ring", area=16.0), "Cut a hole (area 16)")
        self.assertEqual(po.describe("fill_ring", part_index=1, x=5, y=5.5), "Fill the hole at (5, 5.5) in part 1")
        self.assertEqual(po.describe("delete_ring", ring_index=2), "Delete hole 2 of part 0")
        self.assertEqual(po.describe("delete_part", part_index=3), "Delete part 3")
        self.assertEqual(po.describe("add_part"), "Add a new part")


if __name__ == "__main__":
    unittest.main()
