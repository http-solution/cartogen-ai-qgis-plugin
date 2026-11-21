"""Pure parts of delineate_watershed (tools/watershed_tools.py): outlet parsing, design-input wording, warnings, routing of the reported query."""
import unittest

from cartogen_ai.core.agent.tools import TOOLS_SCHEMA
from cartogen_ai.core.agent.tools import watershed_tools as wt
from cartogen_ai.core.services.tool_router import ToolRouter

REPORTED_QUERY = ('determine watershed area, steam length, h, slope, return period 20 year, intensity, tc, and peak flow at this location '
                  '32° 1\'47.39"N, 35°48\'21.00"E')


class TestParseOutlet(unittest.TestCase):
    def test_the_reported_dms_location(self):
        (lon, lat), err = wt.parse_outlet("32° 1'47.39\"N, 35°48'21.00\"E")
        self.assertIsNone(err)
        self.assertAlmostEqual(lat, 32.0298305556, places=7)
        self.assertAlmostEqual(lon, 35.8058333333, places=7)

    def test_decimal_text_and_numbers(self):
        self.assertEqual(wt.parse_outlet("32.03, 35.81")[0], (35.81, 32.03))
        self.assertEqual(wt.parse_outlet(None, 32.03, 35.81)[0], (35.81, 32.03))
        self.assertEqual(wt.parse_outlet("32.03 35.81")[0], (35.81, 32.03))

    def test_decimal_degrees_with_hemisphere_letters(self):
        self.assertEqual(wt.parse_outlet("31.0297 N 35.8058 E"), ((35.8058, 31.0297), None))

    def test_bad_locations(self):
        for args in (("somewhere near Amman",), (None, None, None), (None, 95, 10), (None, 10, 200), (None, "x", 1)):
            self.assertIsNone(wt.parse_outlet(*args)[0], args)
            self.assertTrue(wt.parse_outlet(*args)[1], args)


class TestLargestRadius(unittest.TestCase):
    def test_the_named_radius_builds_a_window_inside_the_limit(self):
        """The refusal now says which radius_km fits; building the window the way delineate_watershed does must stay within MAX_CELLS."""
        for cell in (10.0, 12.3, 30.0, 90.0):
            radius = wt.largest_radius_km(cell, cell)
            half = max(5, round(radius * 1000.0 / cell))
            self.assertLessEqual((2 * half + 1) ** 2, wt.MAX_CELLS, cell)
            # and it is not needlessly small: 0.2 km more would already be over
            half_more = round((radius + 0.2) * 1000.0 / cell)
            self.assertGreater((2 * half_more + 1) ** 2, wt.MAX_CELLS - 4 * (2 * half_more + 1), cell)

    def test_the_run_that_failed_gets_an_answer(self):
        # row C19: 1,100,143 cells for radius 8 km means about 15.4 m cells; the fitting radius is then about 4.8 km
        self.assertAlmostEqual(wt.largest_radius_km(15.4, 15.4), 4.8, delta=0.2)

    def test_a_tiny_cell_or_a_huge_one_never_returns_zero(self):
        self.assertGreaterEqual(wt.largest_radius_km(0.01, 0.01), 0.1)


class TestDesignInputsAndWarnings(unittest.TestCase):
    def test_design_inputs_name_what_is_needed_and_do_not_apply_a_value(self):
        needed = wt.design_inputs_needed(37.5, 20)
        self.assertIn("20-year", needed["rainfall_intensity"])
        self.assertIn("37.5 min", needed["rainfall_intensity"])
        self.assertIn("source", needed["rainfall_intensity"])
        self.assertIn("single-family residential", needed["reference_c_ranges_not_applied"])
        self.assertIn("confirm", needed["reference_note"])
        self.assertNotIn("runoff_coefficient_value", needed)

    def _result(self, **kw):
        base = {"area_km2": 0.3, "touches_dem_edge": False, "snapped_to_channel": True, "snap_moved_m": 30.0, "H_m": 40.0}
        base.update(kw)
        return base

    def test_a_clean_small_basin_has_only_the_standing_surface_model_note(self):
        warnings = wt.hydrology_warnings(self._result(), 30)
        self.assertEqual(len(warnings), 1)
        self.assertIn("surface model", warnings[0])

    def test_each_problem_is_called_out(self):
        text = " ".join(wt.hydrology_warnings(self._result(touches_dem_edge=True, snapped_to_channel=False, snap_moved_m=280.0, area_km2=3.0,
                                                          H_m=0.0), 30))
        for expected in ("cut off", "No drainage channel", "moved 280 m", "Rational Method", "Kirpich", "no elevation drop"):
            self.assertIn(expected, text)


class TestRouting(unittest.TestCase):
    def test_the_reported_request_is_offered_the_whole_chain(self):
        names = {t["function"]["name"] for t in ToolRouter(TOOLS_SCHEMA).filter_relevant_tools(REPORTED_QUERY)}
        for tool in ("parse_dms_location", "fetch_dem", "delineate_watershed", "calculate_rational_watershed_peak_flow"):
            self.assertIn(tool, names)


if __name__ == "__main__":
    unittest.main()
