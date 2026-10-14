"""The golden suites may grow but never shrink.

Why: a golden table is only a safety net while its rows exist. Deleting a row that fails is the cheapest way to make a build green, so
the row counts are pinned. Raise a number when you add rows; lowering one needs a stated reason in the PR."""
import json
import os
import unittest

from tests.test_qgis_vocabulary_coverage import VOCAB
from tests.test_processing_allowlist_routing import ROWS
from tests.test_tool_router_basics import GOLDEN, GOLDEN_LONG

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


class TestGoldenSuiteSizePins(unittest.TestCase):
    def test_basic_requests_table(self):
        self.assertGreaterEqual(len(GOLDEN), 32)

    def test_long_requests_table(self):
        self.assertGreaterEqual(len(GOLDEN_LONG), 16)

    def test_qgis_vocabulary_table(self):
        self.assertGreaterEqual(len(VOCAB), 91)

    def test_processing_allowlist_rows(self):
        self.assertGreaterEqual(len(ROWS), 42)

    def test_recorded_sessions_fixture(self):
        with open(os.path.join(FIXTURES, "recorded_sessions_rc40.json"), encoding="utf-8") as fh:
            data = json.load(fh)
        self.assertGreaterEqual(len(data), 26)


if __name__ == "__main__":
    unittest.main()
