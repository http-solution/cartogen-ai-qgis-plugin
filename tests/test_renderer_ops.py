"""PLAN-023 R10-3: the pure request check for set_renderer. No QGIS and no numpy needed."""
import unittest

from cartogen_ai.core.agent.tools import renderer_ops as ro


class TestCheck(unittest.TestCase):
    def test_valid_requests(self):
        self.assertIsNone(ro.check_request("merged_features", None, "polygon"))
        self.assertIsNone(ro.check_request("merged_features", None, "line"))
        self.assertIsNone(ro.check_request("inverted_polygons", {}, "polygon"))
        self.assertIsNone(ro.check_request("embedded", None, "point"))
        self.assertIsNone(ro.check_request("No_Symbols", None, "line"))
        self.assertIsNone(ro.check_request("2_5d", {"roof_color": "#ff0000", "wall_color": "grey", "shadow": False}, "polygon"))
        self.assertIsNone(ro.check_request("single_symbol", None, "point"))

    def test_the_wrong_geometry_is_refused_with_the_reason(self):
        self.assertIn("polygon layers; this is a line layer", ro.check_request("inverted_polygons", None, "line"))
        self.assertIn("this is a point layer", ro.check_request("merged_features", None, "point"))
        self.assertIn("2_5d is for polygon", ro.check_request("2_5d", None, "line"))

    def test_bad_kinds_and_options(self):
        for args in (("", None, "polygon"), ("fancy", None, "polygon"), ("2_5d", {"height": 5}, "polygon"), ("2_5d", {"roof_color": "#12"}, "polygon"),
                     ("2_5d", {"shadow": "yes"}, "polygon"), ("merged_features", {"x": 1}, "polygon"), ("2_5d", [1], "polygon")):
            self.assertIsNotNone(ro.check_request(*args), args)

    def test_every_kind_has_a_geometry_rule_and_a_qgis_type_name(self):
        for kind in ro.KINDS:
            self.assertIn(kind, ro.APPLIES_TO)
            self.assertIn(kind, ro.RENDERER_TYPES)


if __name__ == "__main__":
    unittest.main()
