"""PLAN-005 gives every file-writing Processing algorithm exactly one wave. If the processing matrix gains or loses one (a re-export of the QGIS registry,
or an algorithm moved to the allow-list), this fails until the plan's disposition table is updated, so none is silently forgotten."""
import csv
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WAVES = {"E1-REPORT": 6, "E1-GDAL-VECTOR": 2, "COVERED-ELSEWHERE": 8, "E2-INFO": 4, "E2-PLOT": 9, "E2-EXPORT": 17, "E3-NOT-PLANNED": 14}


def _rows(path):
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


class TestPlan005Dispositions(unittest.TestCase):
    def test_every_file_writing_algorithm_has_exactly_one_wave(self):
        everything = _rows(ROOT / "docs" / "qgis_coverage" / "processing_matrix.csv")
        matrix = {r["id"] for r in everything if r["disposition"] == "NEEDS-OUTPUT-HANDLING"}
        moved_on = {r["id"] for r in everything if r["disposition"] == "ALLOWLISTED"}
        planned = [r["id"] for r in _rows(ROOT / "docs" / "plans" / "PLAN-005-dispositions.csv")]
        self.assertEqual(sorted(planned), sorted(set(planned)), "an id appears twice")
        self.assertEqual(sorted(matrix - set(planned)), [], "a file-writing algorithm has no wave")
        # an id that moved on (now allow-listed, matrix regenerated) may stay in the table; an id that was never file-writing may not
        self.assertEqual(sorted(set(planned) - matrix - moved_on), [], "the table names an id the matrix does not list as file-writing")

    def test_wave_counts_match_the_plan(self):
        counts = Counter(r["wave"] for r in _rows(ROOT / "docs" / "plans" / "PLAN-005-dispositions.csv"))
        self.assertEqual(dict(counts), WAVES)
        text = (ROOT / "docs" / "plans" / "PLAN-005-file-writing-algorithms.md").read_text(encoding="utf-8")
        for wave, count in WAVES.items():
            self.assertRegex(text, rf"\*\*{wave}\*\* \| {count} \|", wave)

    def test_every_row_has_a_reason(self):
        for row in _rows(ROOT / "docs" / "plans" / "PLAN-005-dispositions.csv"):
            self.assertGreater(len(row["reason"]), 20, row["id"])


if __name__ == "__main__":
    unittest.main()
