"""PLAN-023 R3-3: per-pixel time-series statistics, hand-computed known answers. Pure numpy: skipped where numpy is missing (the CI test job installs it)."""
import unittest

try:
    import numpy as np
    HAVE_NUMPY = True
except ImportError:
    HAVE_NUMPY = False

from cartogen_ai.core.agent.tools import raster_series as rs


def cell(value):
    return np.array([[value]], dtype=np.float64)


def fill(acc, series, times=None):
    for i, value in enumerate(series):
        valid = value is not None
        acc.add(cell(0.0 if value is None else value), np.array([[valid]]), (times or [0] * len(series))[i])
    return acc


@unittest.skipUnless(HAVE_NUMPY, "numpy not installed")
class TestKnownAnswers(unittest.TestCase):
    def test_trend_of_1_2_3_4_at_t_0_1_2_3_is_exactly_one(self):
        # n = 4, sum t = 6, sum t^2 = 14, sum y = 10, sum t y = 0 + 2 + 6 + 12 = 20: slope = (4 x 20 - 6 x 10) / (4 x 14 - 36) = 20 / 20 = 1
        acc = fill(rs.SeriesAccumulator((1, 1), "trend"), [1, 2, 3, 4], [0, 1, 2, 3])
        slope, ok = acc.trend()
        self.assertTrue(bool(ok[0, 0]))
        self.assertEqual(float(slope[0, 0]), 1.0)

    def test_trend_is_in_value_units_per_year_whatever_the_time_origin(self):
        # the same line y = 2 t + 5 observed in 2018 to 2021: slope 2 per year
        acc = fill(rs.SeriesAccumulator((1, 1), "trend"), [5 + 2 * 2018, 5 + 2 * 2019, 5 + 2 * 2020, 5 + 2 * 2021], [2018, 2019, 2020, 2021])
        self.assertAlmostEqual(float(acc.trend()[0][0, 0]), 2.0, places=3)

    def test_a_decreasing_series_has_a_negative_slope(self):
        acc = fill(rs.SeriesAccumulator((1, 1), "trend"), [9, 7, 5, 3], [0, 1, 2, 3])
        self.assertEqual(float(acc.trend()[0][0, 0]), -2.0)

    def test_anomaly_baseline_mean_10_sd_2_and_value_14_gives_z_2(self):
        # baseline 8, 10, 12: mean 10, sample variance (4 + 0 + 4) / 2 = 4, sd 2; z = (14 - 10) / 2 = 2
        acc = fill(rs.SeriesAccumulator((1, 1), "baseline"), [8, 10, 12])
        z, ok = acc.anomaly(cell(14.0), np.array([[True]]))
        self.assertTrue(bool(ok[0, 0]))
        self.assertAlmostEqual(float(z[0, 0]), 2.0, places=6)

    def test_a_value_below_the_baseline_has_a_negative_z(self):
        acc = fill(rs.SeriesAccumulator((1, 1), "baseline"), [8, 10, 12])
        self.assertAlmostEqual(float(acc.anomaly(cell(7.0), np.array([[True]]))[0][0, 0]), -1.5, places=6)

    def test_mean(self):
        acc = fill(rs.SeriesAccumulator((1, 1), "mean"), [2, 4, 9])
        self.assertAlmostEqual(float(acc.mean()[0][0, 0]), 5.0, places=6)


@unittest.skipUnless(HAVE_NUMPY, "numpy not installed")
class TestNoData(unittest.TestCase):
    def test_mean_skips_nodata_observations_and_is_undefined_with_none(self):
        acc = fill(rs.SeriesAccumulator((1, 1), "mean"), [2, None, 4])
        self.assertAlmostEqual(float(acc.mean()[0][0, 0]), 3.0, places=6)
        empty = fill(rs.SeriesAccumulator((1, 1), "mean"), [None, None])
        self.assertFalse(bool(empty.mean()[1][0, 0]))

    def test_trend_needs_the_minimum_number_of_valid_observations(self):
        acc = fill(rs.SeriesAccumulator((1, 1), "trend"), [1, None, 3, None], [0, 1, 2, 3])        # only 2 valid
        self.assertFalse(bool(acc.trend()[1][0, 0]))
        self.assertTrue(bool(acc.trend(min_obs=2)[1][0, 0]))
        self.assertEqual(float(acc.trend(min_obs=2)[0][0, 0]), 1.0)                                  # a line through (0, 1) and (2, 3)

    def test_trend_is_undefined_when_every_observation_has_the_same_time(self):
        acc = fill(rs.SeriesAccumulator((1, 1), "trend"), [1, 2, 3], [5, 5, 5])
        self.assertFalse(bool(acc.trend()[1][0, 0]))

    def test_anomaly_is_undefined_for_a_flat_baseline_a_short_baseline_or_a_nodata_value(self):
        flat = fill(rs.SeriesAccumulator((1, 1), "baseline"), [5, 5, 5])
        self.assertFalse(bool(flat.anomaly(cell(6.0), np.array([[True]]))[1][0, 0]))
        short = fill(rs.SeriesAccumulator((1, 1), "baseline"), [5, 7])
        self.assertFalse(bool(short.anomaly(cell(6.0), np.array([[True]]))[1][0, 0]))
        good = fill(rs.SeriesAccumulator((1, 1), "baseline"), [8, 10, 12])
        self.assertFalse(bool(good.anomaly(cell(6.0), np.array([[False]]))[1][0, 0]))

    def test_nan_input_counts_as_no_data(self):
        acc = rs.SeriesAccumulator((1, 2), "mean")
        acc.add(np.array([[np.nan, 4.0]]), np.ones((1, 2), dtype=bool))
        _values, ok = acc.mean()
        self.assertEqual(ok.tolist(), [[False, True]])

    def test_each_cell_is_independent(self):
        acc = rs.SeriesAccumulator((1, 2), "trend")
        for t, row in enumerate([[1.0, 4.0], [2.0, 3.0], [3.0, 2.0]]):
            acc.add(np.array([row]), np.ones((1, 2), dtype=bool), float(t))
        self.assertEqual(acc.trend()[0].tolist(), [[1.0, -1.0]])

    def test_unknown_kind_is_refused(self):
        with self.assertRaises(ValueError):
            rs.SeriesAccumulator((1, 1), "median")


class TestTimes(unittest.TestCase):
    def test_numbers_years_and_dates_become_decimal_years(self):
        self.assertEqual(rs.parse_time(2021), 2021.0)
        self.assertEqual(rs.parse_time("2021"), 2021.0)
        self.assertEqual(rs.parse_time("2021-01-01"), 2021.0)
        self.assertAlmostEqual(rs.parse_time("2021-07-02"), 2021 + 182 / 365, places=6)       # day 183 of a 365-day year
        self.assertAlmostEqual(rs.parse_time("2020-07-02"), 2020 + 183 / 366, places=6)       # day 184 of a leap year
        self.assertEqual(rs.parse_time("2021-01-01T10:30:00Z"), 2021.0)
        self.assertEqual(rs.parse_time(2021.5), 2021.5)

    def test_junk_is_not_a_time(self):
        for junk in ("", None, "last spring", "2021-13-40", True, float("nan"), float("inf")):
            self.assertIsNone(rs.parse_time(junk), repr(junk))

    def test_parse_times_names_the_first_bad_value(self):
        years, error = rs.parse_times(["2020", "later", "2022"])
        self.assertIsNone(years)
        self.assertIn("'later'", error)
        self.assertEqual(rs.parse_times(["2020", 2021]), ([2020.0, 2021.0], None))


class TestCheckRequest(unittest.TestCase):
    def test_what_each_statistic_needs(self):
        names = ["a", "b", "c", "d"]
        self.assertIsNone(rs.check_request("mean", names))
        self.assertIsNone(rs.check_request("trend", names, times=[2018, 2019, 2020, 2021]))
        self.assertIn("one time per raster", rs.check_request("trend", names, times=[2018, 2019]))
        self.assertIn("at least 3 rasters", rs.check_request("trend", ["a", "b"], times=[1, 2]))
        self.assertIn("two different times", rs.check_request("trend", names, times=[5, 5, 5, 5]))
        self.assertIsNone(rs.check_request("anomaly", names))                                   # last raster against the three before it
        self.assertIsNone(rs.check_request("anomaly", names, target="d"))
        self.assertIn("at least 3 baseline", rs.check_request("anomaly", ["a", "b", "c"]))
        self.assertIn("not one of the rasters", rs.check_request("anomaly", names, target="z"))
        self.assertIn("cannot also be part", rs.check_request("anomaly", names, target="d", baseline=["a", "b", "d"]))

    def test_bad_statistic_empty_list_and_bad_minimum(self):
        self.assertIn("statistic must be", rs.check_request("median", ["a"]))
        self.assertIn("list of raster", rs.check_request("mean", []))
        self.assertIn("1 or more", rs.check_request("mean", ["a"], min_observations=0))
        self.assertIn("whole number", rs.check_request("mean", ["a"], min_observations="x"))


if __name__ == "__main__":
    unittest.main()
