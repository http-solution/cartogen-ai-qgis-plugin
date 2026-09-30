# -*- coding: utf-8 -*-
"""
Tests for agent/coordinates.py -- deterministic coordinate handling (rc7 smoke test,
2026-09-30, findings F04 and F20).

F04: the request point EPSG:3857 (4902068, 1799912) is lon 44.036026, lat 15.958454, but the
analysis origin was placed at lat 15.970136 (~1.3 km north) because the model converted the
coordinates by hand: add_point_layer only accepted lon/lat and no transform tool existed.
F20: the local-data offer read coordinates in a request "as the project CRS" without checking
they were plausible for it.
"""
import math
import unittest

from cartogen_ai.core.agent import coordinates as co

R = 6378137.0


def mercator_inverse(x, y):
    """Spherical web-mercator inverse -- what QGIS/PROJ does for EPSG:3857."""
    return math.degrees(x / R), math.degrees(math.atan(math.sinh(y / R)))


class TestNormalizeCrs(unittest.TestCase):
    def test_common_spellings(self):
        self.assertEqual(co.normalize_crs("epsg:3857"), "EPSG:3857")
        self.assertEqual(co.normalize_crs(" 3857 "), "EPSG:3857")
        self.assertEqual(co.normalize_crs("EPSG:32636"), "EPSG:32636")

    def test_geographic_aliases_collapse_to_4326(self):
        for spelling in ("EPSG:4326", "4326", "WGS84", "wgs 84", "CRS:84", "OGC:CRS84"):
            self.assertEqual(co.normalize_crs(spelling), "EPSG:4326", spelling)

    def test_empty_means_no_crs(self):
        for empty in (None, "", "   "):
            self.assertIsNone(co.normalize_crs(empty))

    def test_unknown_text_passes_through_for_qgis_to_judge(self):
        self.assertEqual(co.normalize_crs("+proj=utm +zone=38 +datum=WGS84"), "+proj=utm +zone=38 +datum=WGS84")


class TestResolveLonLat(unittest.TestCase):
    def test_plain_degrees_are_returned_unchanged(self):
        self.assertEqual(co.resolve_lon_lat({"lon": 35.93, "lat": 31.95}), (35.93, 31.95))

    def test_degrees_with_explicit_4326_need_no_transform(self):
        self.assertEqual(co.resolve_lon_lat({"lon": 35.93, "lat": 31.95}, "EPSG:4326"), (35.93, 31.95))

    def test_projected_values_without_a_crs_are_refused_with_a_helpful_message(self):
        with self.assertRaises(ValueError) as ctx:
            co.resolve_lon_lat({"lon": 4902068, "lat": 1799912})
        msg = str(ctx.exception).lower()
        self.assertIn("projected", msg)
        self.assertIn("crs", msg)

    def test_the_reference_point_transforms_to_the_qgis_value_not_the_hand_converted_one(self):
        lon, lat = co.resolve_lon_lat({"x": 4902068.0, "y": 1799912.0}, "EPSG:3857", transform=mercator_inverse)
        self.assertAlmostEqual(lon, 44.036026, places=5)
        self.assertAlmostEqual(lat, 15.958454, places=5)
        self.assertNotAlmostEqual(lat, 15.970136, places=3)  # the value the model produced by hand

    def test_easting_northing_may_arrive_in_lon_lat_keys(self):
        lon, lat = co.resolve_lon_lat({"lon": 4902068.0, "lat": 1799912.0}, "EPSG:3857", transform=mercator_inverse)
        self.assertAlmostEqual(lat, 15.958454, places=5)

    def test_xy_keys_win_over_lonlat_when_a_projected_crs_is_given(self):
        lon, lat = co.resolve_lon_lat({"x": 4902068.0, "y": 1799912.0, "lon": 0, "lat": 0}, "EPSG:3857",
                                      transform=mercator_inverse)
        self.assertAlmostEqual(lat, 15.958454, places=5)

    def test_a_projected_crs_without_a_transform_is_an_error(self):
        with self.assertRaises(ValueError):
            co.resolve_lon_lat({"x": 1.0, "y": 2.0}, "EPSG:3857", transform=None)

    def test_a_transform_that_lands_outside_the_valid_range_is_an_error(self):
        with self.assertRaises(ValueError):
            co.resolve_lon_lat({"x": 1.0, "y": 2.0}, "EPSG:3857", transform=lambda x, y: (500.0, 95.0))

    def test_missing_coordinates_are_an_error(self):
        with self.assertRaises(ValueError):
            co.resolve_lon_lat({"name": "no coordinates"})

    def test_non_numeric_values_are_an_error(self):
        with self.assertRaises(ValueError):
            co.resolve_lon_lat({"lon": "abc", "lat": 1})

    def test_degrees_just_inside_the_limits_are_accepted(self):
        self.assertEqual(co.resolve_lon_lat({"lon": 180, "lat": -90}), (180.0, -90.0))


class TestInterpretRequestPair(unittest.TestCase):
    """F20: which CRS a coordinate typed into a request can plausibly be in."""

    def test_large_numbers_in_a_projected_project_are_taken_as_project_crs(self):
        self.assertEqual(co.interpret_request_pair((4902068.0, 1799912.0), project_crs_is_geographic=False),
                         ("project_crs", 4902068.0, 1799912.0))

    def test_large_numbers_in_a_geographic_project_cannot_be_degrees(self):
        self.assertIsNone(co.interpret_request_pair((4902068.0, 1799912.0), project_crs_is_geographic=True))

    def test_degrees_in_a_geographic_project_are_fine(self):
        self.assertEqual(co.interpret_request_pair((44.03, 15.95), project_crs_is_geographic=True),
                         ("project_crs", 44.03, 15.95))

    def test_degree_sized_numbers_in_a_projected_project_are_ambiguous(self):
        # 44.03, 15.95 read as metres in EPSG:3857 is a point off the coast of West Africa.
        self.assertIsNone(co.interpret_request_pair((44.03, 15.95), project_crs_is_geographic=False))


class TestAddPointLayerSchema(unittest.TestCase):
    """The tool schema is what tells the model to pass a CRS instead of converting by hand."""

    def _schema(self):
        from cartogen_ai.core.agent.tools import TOOLS_SCHEMA
        for item in TOOLS_SCHEMA:
            if item["function"]["name"] == "add_point_layer":
                return item["function"]["parameters"]
        self.fail("add_point_layer not registered")

    def test_a_crs_argument_exists_and_tells_the_model_not_to_convert(self):
        crs = self._schema()["properties"]["crs"]
        self.assertIn("NEVER convert", crs["description"])

    def test_points_accept_projected_x_and_y(self):
        item = self._schema()["properties"]["points"]["items"]["properties"]
        self.assertIn("x", item)
        self.assertIn("y", item)

    def test_lat_lon_are_no_longer_the_only_way_to_place_a_point(self):
        self.assertEqual(self._schema()["properties"]["points"]["items"]["required"], ["name"])


if __name__ == "__main__":
    unittest.main()
