"""Offline guard for tests/_processing_live_rows.py: every allow-listed Processing id has a live row or a stated reason."""
import unittest

from cartogen_ai.core.agent.tools._processing_allowlist import ALLOWED_ALGORITHM_IDS
from tests._processing_live_rows import LIVE_ROWS, NOT_YET


class TestProcessingLiveRows(unittest.TestCase):
    def test_every_allowlisted_algorithm_is_in_exactly_one_table(self):
        both = set(LIVE_ROWS) & set(NOT_YET)
        missing = set(ALLOWED_ALGORITHM_IDS) - set(LIVE_ROWS) - set(NOT_YET)
        self.assertEqual((sorted(both), sorted(missing)), ([], []))

    def test_no_row_names_an_algorithm_that_left_the_allowlist(self):
        self.assertEqual(sorted((set(LIVE_ROWS) | set(NOT_YET)) - set(ALLOWED_ALGORITHM_IDS)), [])

    def test_every_not_yet_entry_states_a_reason(self):
        self.assertEqual([k for k, v in NOT_YET.items() if len(v) < 10], [])

    def test_live_coverage_never_drops(self):
        self.assertGreaterEqual(len(LIVE_ROWS), 19)


if __name__ == "__main__":
    unittest.main()
