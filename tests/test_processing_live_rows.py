"""Offline guard for tests/_processing_live_rows.py: every allow-listed Processing id has a live row or a stated reason."""
import unittest

from cartogen_ai.core.agent.tools._processing_allowlist import ALLOWED_ALGORITHM_IDS, FAMILY_NAMES
from tests._processing_live_rows import GEOMETRY_NOT_YET, GEOMETRY_REJECTED, GRASS_REJECTED, LIVE_ROWS, NOT_YET


class TestProcessingLiveRows(unittest.TestCase):
    def test_every_allowlisted_algorithm_is_in_exactly_one_table(self):
        # the geometry family (M6a) is run by tests/test_processing_geometry_family_live.py, which builds each call from the algorithm's own
        # parameter definitions; its failures are listed in GEOMETRY_NOT_YET with the error, never silently dropped.
        both = set(LIVE_ROWS) & set(NOT_YET)
        missing = set(ALLOWED_ALGORITHM_IDS) - set(LIVE_ROWS) - set(NOT_YET) - set(FAMILY_NAMES)
        self.assertEqual((sorted(both), sorted(missing)), ([], []))

    def test_no_row_names_an_algorithm_that_left_the_allowlist(self):
        self.assertEqual(sorted((set(LIVE_ROWS) | set(NOT_YET)) - set(ALLOWED_ALGORITHM_IDS)), [])

    def test_geometry_family_exceptions_are_real_members_with_a_reason(self):
        self.assertEqual(sorted(set(GEOMETRY_NOT_YET) - set(FAMILY_NAMES)), [])
        self.assertEqual([k for k, v in GEOMETRY_NOT_YET.items() if len(v) < 10], [])

    def test_rejected_geometry_algorithms_are_not_allow_listed_and_say_why(self):
        self.assertEqual(sorted(set(GEOMETRY_REJECTED) & set(ALLOWED_ALGORITHM_IDS)), [])
        self.assertEqual([k for k, v in GEOMETRY_REJECTED.items() if len(v) < 10], [])

    def test_rejected_grass_algorithms_are_not_allow_listed_and_say_why(self):
        self.assertEqual(sorted(set(GRASS_REJECTED) & set(ALLOWED_ALGORITHM_IDS)), [])
        self.assertEqual([k for k, v in GRASS_REJECTED.items() if len(v) < 10], [])

    def test_every_not_yet_entry_states_a_reason(self):
        self.assertEqual([k for k, v in NOT_YET.items() if len(v) < 10], [])

    def test_live_coverage_never_drops(self):
        self.assertGreaterEqual(len(LIVE_ROWS), 19)


if __name__ == "__main__":
    unittest.main()
