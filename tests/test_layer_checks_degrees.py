"""degrees_value_problem: a distance given for a latitude/longitude layer is read in degrees, so 1 or more is refused (self-audit round 2,
2026-10-26; same class as the route-risk buffer in degrees, 1.18.2 hand test C9)."""
import unittest
from unittest.mock import MagicMock

from cartogen_ai.core.agent.tools._layer_checks import degrees_value_problem


def _layer(geographic, valid=True):
    layer = MagicMock()
    layer.name.return_value = "pts"
    layer.crs.return_value.isValid.return_value = valid
    layer.crs.return_value.isGeographic.return_value = geographic
    layer.crs.return_value.authid.return_value = "EPSG:4326" if geographic else "EPSG:32638"
    return layer


class TestDegreesValueProblem(unittest.TestCase):
    def test_a_metre_sized_number_on_a_latlon_layer_is_refused_with_the_conversion(self):
        text = degrees_value_problem(_layer(True), 1000, "the radius")
        self.assertIn("DEGREES", text)
        self.assertIn("0.01 is about 1.1 km", text)
        self.assertIn("111,000 km", text)

    def test_a_degree_sized_number_is_accepted(self):
        self.assertIsNone(degrees_value_problem(_layer(True), 0.01, "the radius"))
        self.assertIsNone(degrees_value_problem(_layer(True), 0.5, "the radius"))

    def test_a_projected_layer_is_never_refused(self):
        self.assertIsNone(degrees_value_problem(_layer(False), 5000, "the radius"))

    def test_an_unreadable_crs_or_value_is_not_an_error(self):
        self.assertIsNone(degrees_value_problem(_layer(True, valid=False), 1000, "the radius"))
        self.assertIsNone(degrees_value_problem(_layer(True), "n/a", "the radius"))
        self.assertIsNone(degrees_value_problem(MagicMock(), 1000, "the radius"))   # a test double is not "geographic"


if __name__ == "__main__":
    unittest.main()
