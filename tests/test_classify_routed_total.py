"""rc48 OI-148: the within/beyond decision of classify_facilities_by_access counts the access leg when it can (pure part, no QGIS)."""
import unittest

from cartogen_ai.core.agent.tools.logistics_tools import _classify_by_routed_total


class TestClassifyByRoutedTotal(unittest.TestCase):
    def test_the_total_decides_not_the_road_cost_alone(self):
        totals = {"1": 370.0, "2": 280.0}               # Inside_the_U (70 m road + 300 m leg), Beside_the_arm (200 m + 80 m)
        self.assertEqual(_classify_by_routed_total([1, 2], totals, 300.0), ["beyond", "within"])

    def test_a_facility_without_a_total_is_beyond(self):
        self.assertEqual(_classify_by_routed_total([1, 2], {"1": 10.0}, 300.0), ["within", "beyond"])

    def test_the_budget_itself_counts_as_within(self):
        self.assertEqual(_classify_by_routed_total([7], {"7": 300.0}, 300.0), ["within"])


if __name__ == "__main__":
    unittest.main()
