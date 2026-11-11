"""PLAN-023 R11-5: every algorithm the processing matrix marks CANDIDATE-EXPRESSION or REVIEW-INPUT has a written, one-by-one decision in docs/qgis_coverage/r11_5_reviews.csv, and a
declined one is not on the allow-list. If the matrix is regenerated and gains or loses one, this fails until the decision table is updated, so none is silently forgotten. Offline."""
import csv
import unittest
from pathlib import Path

from cartogen_ai.core.agent.tools._processing_allowlist import ALLOWED_ALGORITHM_IDS

ROOT = Path(__file__).resolve().parents[1]


def _rows(path):
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


class TestR115Reviews(unittest.TestCase):
    def test_every_candidate_has_a_decision_and_none_is_invented(self):
        matrix = {r["id"]: r["disposition"] for r in _rows(ROOT / "docs/qgis_coverage/processing_matrix.csv") if r["disposition"] in ("CANDIDATE-EXPRESSION", "REVIEW-INPUT")}
        decided = {r["id"]: r for r in _rows(ROOT / "docs/qgis_coverage/r11_5_reviews.csv")}
        self.assertEqual(sorted(set(matrix) - set(decided)), [], "a candidate has no decision")
        self.assertEqual(sorted(set(decided) - set(matrix)), [], "the table names an id the matrix does not list as a candidate")
        self.assertEqual((sum(1 for r in decided.values() if r["kind"] == "expression"), sum(1 for r in decided.values() if r["kind"] == "path")), (11, 17))

    def test_every_decision_is_declined_with_a_reason_and_none_is_approved(self):
        for alg_id, row in ((r["id"], r) for r in _rows(ROOT / "docs/qgis_coverage/r11_5_reviews.csv")):
            self.assertEqual(row["decision"], "declined", alg_id)
            self.assertGreater(len(row["reason"]), 20, alg_id)
            self.assertNotIn(alg_id, ALLOWED_ALGORITHM_IDS, f"{alg_id} is declined here but approved in the allow-list")


if __name__ == "__main__":
    unittest.main()
