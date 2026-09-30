# -*- coding: utf-8 -*-
"""F08 (rc7 smoke test, 2026-09-30): 'health facilities beyond one hour' took 43 min 48 s because
travel_time_matrix ran a shortest-path search per destination (3,369). classify_facilities_by_access
answers it from one service area; tests/test_rc8_live.py checks it against routed costs in real QGIS."""
import unittest
from unittest.mock import MagicMock

from cartogen_ai.core.agent.tools import logistics_tools as lt


class TestClassification(unittest.TestCase):
    def test_within_is_inclusive_of_the_snap_distance(self):
        self.assertEqual(lt._classify_by_distance([0, 499.9, 500, 500.1, 9000], 500),
                         ["within", "within", "within", "beyond", "beyond"])

    def test_no_reached_road_is_beyond(self):
        self.assertEqual(lt._classify_by_distance([None], 500), ["beyond"])

    def test_summary_counts(self):
        self.assertEqual(lt._access_summary(["within", "beyond", "beyond"]), {"within": 1, "beyond": 2, "total": 3})
        self.assertEqual(lt._access_summary([]), {"within": 0, "beyond": 0, "total": 0})


class TestMatrixSizeGuard(unittest.TestCase):
    def test_reads_a_real_count(self):
        layer = MagicMock()
        layer.featureCount.return_value = 3369
        self.assertEqual(lt._matrix_destination_count(layer), 3369)

    def test_unreadable_counts_never_block(self):
        bare = MagicMock()                       # featureCount() returns a MagicMock, not an int
        self.assertEqual(lt._matrix_destination_count(bare), 0)
        broken = MagicMock()
        broken.featureCount.side_effect = RuntimeError("layer deleted")
        self.assertEqual(lt._matrix_destination_count(broken), 0)

    def test_threshold_is_well_below_the_observed_slow_case(self):
        self.assertLess(lt.MATRIX_LARGE_DESTINATIONS, 3369)


class TestToolIsWired(unittest.TestCase):
    def test_registered_with_an_operation_type_and_in_the_road_network_set(self):
        from cartogen_ai.core.agent import tool_operations, local_data_sources
        from cartogen_ai.core.agent.tools import TOOLS_SCHEMA
        names = {t["function"]["name"] for t in TOOLS_SCHEMA}
        self.assertIn("classify_facilities_by_access", names)
        self.assertIn("classify_facilities_by_access", tool_operations.TOOL_OPERATION_TYPES)
        self.assertIn("classify_facilities_by_access", local_data_sources.ROAD_NETWORK_TOOLS)

    def test_matrix_description_points_at_the_fast_tool(self):
        from cartogen_ai.core.agent.tools import TOOLS_SCHEMA
        desc = next(t["function"]["description"] for t in TOOLS_SCHEMA if t["function"]["name"] == "travel_time_matrix")
        self.assertIn("classify_facilities_by_access", desc)


if __name__ == "__main__":
    unittest.main()


class TestReachGeometryHelpers(unittest.TestCase):
    """F09: population is summed inside the buffered roads, not the convex hull (rc7 smoke test)."""

    def test_utm_zone_for_sanaa(self):
        self.assertEqual(lt._utm_epsg_for(44.036, 15.958), 32638)

    def test_southern_hemisphere_uses_the_327xx_series(self):
        self.assertEqual(lt._utm_epsg_for(151.2, -33.9), 32756)

    def test_antimeridian_and_extremes_stay_in_range(self):
        self.assertEqual(lt._utm_epsg_for(-180, 0), 32601)
        self.assertEqual(lt._utm_epsg_for(180, 0), 32660)
        self.assertEqual(lt._utm_epsg_for(0, 0), 32631)

    def test_hull_note_says_upper_bound_and_buffer_note_names_the_distance(self):
        self.assertIn("UPPER BOUND", lt.CONVEX_HULL_REACH_NOTE)
        self.assertIn("500 m", lt.ROAD_BUFFER_REACH_NOTE.format(m=500))
