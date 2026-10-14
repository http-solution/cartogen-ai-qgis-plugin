"""Pure parts of the M2 map-view tools (tools/map_view_tools.py) and that each tool is offered for its plain request."""
import unittest

from cartogen_ai.core.agent.tools import TOOLS_SCHEMA
from cartogen_ai.core.agent.tools import map_view_tools as mv
from cartogen_ai.core.services.tool_router import ToolRouter


class TestScale(unittest.TestCase):
    def test_denominators_and_ratios(self):
        for given, expected in ((25000, 25000.0), ("25000", 25000.0), ("1:25000", 25000.0), ("1:1", 1.0), (1.5, 1.5)):
            self.assertEqual(mv.check_scale(given), (expected, None), given)

    def test_bad_scales(self):
        for bad in (0, -5, "abc", None, "1:0", float("inf"), 1e12, "nan"):
            value, err = mv.check_scale(bad)
            self.assertIsNone(value, bad)
            self.assertTrue(err, bad)


class TestExtent(unittest.TestCase):
    def test_good(self):
        self.assertEqual(mv.check_extent([35, 31, 36, 32]), ([35.0, 31.0, 36.0, 32.0], None))
        self.assertEqual(mv.check_extent(["35", "31", "36", "32"])[1], None)

    def test_bad(self):
        for bad in ([1, 2, 3], [1, 2, 3, "x"], [5, 0, 1, 1], [0, 5, 1, 1], None, [0, 0, float("nan"), 1], [0, 0, 1, 1, 1]):
            self.assertIsNone(mv.check_extent(bad)[0], bad)


class TestRotationAndNames(unittest.TestCase):
    def test_rotation_wraps(self):
        self.assertEqual(mv.check_rotation(370), (10.0, None))
        self.assertEqual(mv.check_rotation(-90), (270.0, None))
        self.assertIsNone(mv.check_rotation("left")[0])
        self.assertIsNone(mv.check_rotation(float("inf"))[0])

    def test_group_names(self):
        self.assertEqual(mv.check_group_name("  Basemaps ")[0], "Basemaps")
        self.assertIsNotNone(mv.check_group_name("")[1])
        self.assertIsNotNone(mv.check_group_name("x" * 121)[1])
        self.assertIsNotNone(mv.check_group_name(None)[1])


class TestToolShapes(unittest.TestCase):
    def test_the_crs_assignment_takes_confirmed_and_the_model_cannot_set_it(self):
        import inspect
        registry = {t["function"]["name"]: t["function"] for t in TOOLS_SCHEMA}
        self.assertIn("confirmed", inspect.signature(mv.assign_layer_crs).parameters)
        self.assertNotIn("confirmed", registry["assign_layer_crs"]["parameters"]["properties"])


class TestOffered(unittest.TestCase):
    ROWS = {  # noqa: RUF012
        "create a group called Basemaps and put roads and rivers in it": "create_layer_group",
        "move the layer roads into the group Basemaps": "move_layers_to_group",
        "hide the group Basemaps": "set_group_options",
        "zoom to scale 1:25000": "set_map_view",
        "rotate the map 30 degrees": "set_map_view",
        "set the project crs to EPSG:3857": "set_project_crs",
        "assign projection EPSG:4326 to the layer": "assign_layer_crs",
        "create a bookmark called Amman": "create_bookmark",
        "list the bookmarks": "list_bookmarks",
        "go to the bookmark Amman": "go_to_bookmark",
        "set the project title to Flood response": "set_project_properties",
        "measure the distance between 35.9 31.9 and 36.1 32.0": "measure_distance",
    }

    def test_each_phrase_is_offered_its_tool(self):
        router = ToolRouter(TOOLS_SCHEMA)
        missing = {q: t for q, t in self.ROWS.items() if t not in {x["function"]["name"] for x in router.filter_relevant_tools(q)}}
        self.assertEqual(missing, {})


if __name__ == "__main__":
    unittest.main()
