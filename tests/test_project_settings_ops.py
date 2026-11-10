"""PLAN-023 R10-5: the pure checks and word tables for the project transform, custom CRS, measurement and decoration settings. No QGIS and no numpy needed."""
import unittest

from cartogen_ai.core.agent.tools import project_settings_ops as ps


class TestUnits(unittest.TestCase):
    def test_words_map_to_qgis_member_names(self):
        self.assertEqual(ps.distance_unit_name("Metres"), "Meters")
        self.assertEqual(ps.distance_unit_name("  nautical   miles "), "NauticalMiles")
        self.assertEqual(ps.area_unit_name("sq km"), "SquareKilometers")
        self.assertEqual(ps.area_unit_name("Sq. Km."), "SquareKilometers")
        self.assertEqual(ps.area_unit_name("hectares"), "Hectares")
        self.assertIsNone(ps.distance_unit_name("furlongs"))
        self.assertIsNone(ps.area_unit_name(None))

    def test_check_measurement(self):
        self.assertIsNone(ps.check_measurement("WGS84", "meters", "hectares"))
        self.assertIsNone(ps.check_measurement(None, None, "acres"))
        for args in ((None, None, None), ("", None, None), (5, None, None), (None, "furlongs", None), (None, None, "sq parsecs"), ("x" * 61, None, None)):
            self.assertIsNotNone(ps.check_measurement(*args), args)


class TestCrs(unittest.TestCase):
    def test_a_proj_string_and_a_wkt_are_told_apart(self):
        self.assertEqual(ps.definition_kind("+proj=utm +zone=36 +datum=WGS84 +units=m +no_defs"), "proj")
        self.assertEqual(ps.definition_kind('PROJCRS["x", BASEGEOGCRS["WGS 84"]]'), "wkt")
        self.assertEqual(ps.definition_kind('  geogcs["WGS 84",DATUM["D"]]'), "wkt")
        for text in ("", None, "EPSG:4326", "+units=m", "proj=utm", "select 1"):
            self.assertIsNone(ps.definition_kind(text), text)

    def test_check_custom_crs(self):
        self.assertEqual(ps.check_custom_crs("Local grid", "+proj=tmerc +lat_0=0 +lon_0=35 +k=0.9996 +x_0=500000 +datum=WGS84"), ("proj", None))
        for args in (("", "+proj=utm"), ("n", ""), ("n", "EPSG:4326"), ("n" * 81, "+proj=utm"), ("n", "+proj=utm" + " +x=1" * 3000), (5, "+proj=utm")):
            self.assertIsNone(ps.check_custom_crs(*args)[0], args)
            self.assertIsNotNone(ps.check_custom_crs(*args)[1], args)


class TestTransform(unittest.TestCase):
    def test_checks(self):
        self.assertIsNone(ps.check_transform("EPSG:4326", "EPSG:32636"))
        self.assertIsNone(ps.check_transform("EPSG:4326", "EPSG:32636", "EPSG:1150"))
        for args in (("", "EPSG:4326"), ("EPSG:4326", None), ("EPSG:4326", "epsg:4326"), ("EPSG:4326", "EPSG:32636", ""), ("EPSG:4326", "EPSG:32636", 5)):
            self.assertIsNotNone(ps.check_transform(*args), args)


class TestDecoration(unittest.TestCase):
    def test_placements_and_scopes(self):
        self.assertEqual((ps.PLACEMENTS["bottom_left"], ps.PLACEMENTS["top_center"]), (0, 4))
        self.assertEqual(ps.DECORATIONS["scale_bar"], "ScaleBar")

    def test_checks(self):
        self.assertIsNone(ps.check_decoration("title", True, "top_center", "Flood response"))
        self.assertIsNone(ps.check_decoration("North_Arrow", None, "top_right"))
        self.assertIsNone(ps.check_decoration("grid", False))
        for args in (("legend", True), ("title",), ("title", "yes"), ("title", True, "middle"), ("grid", True, None, "x"), ("title", None, None, "x" * 501), ("title", None, None, 5)):
            self.assertIsNotNone(ps.check_decoration(*args), args)


if __name__ == "__main__":
    unittest.main()
