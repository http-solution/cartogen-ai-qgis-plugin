"""Live run of the agent-run smoke runner (tools/run_smoke_headless.py) on real QGIS: every row of docs/AGENT_RUN_ROWS.json must come out PASS with a complete evidence folder, and a row whose number is wrong must come out FAIL
(the runner must be able to say no). Written without a QGIS install: CI's first run is its first execution."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

try:
    from qgis.core import QgsProject
    LIVE = True
except ImportError:
    LIVE = False

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestAgentRunSmoke(unittest.TestCase):
    def setUp(self):
        from tests.test_chat_widget_live import _boot_qgis
        _boot_qgis()
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        self.rows = json.loads((ROOT / "docs" / "AGENT_RUN_ROWS.json").read_text(encoding="utf-8"))["rows"]

    def test_every_shipped_row_passes_with_complete_evidence(self):
        import run_smoke_headless as runner
        with tempfile.TemporaryDirectory() as tmp:
            statuses, problems = runner.run_rows(self.rows, Path(tmp))
            self.assertEqual(problems, [])
            self.assertEqual(statuses, {r["id"]: "PASS" for r in self.rows}, statuses)
            self.assertTrue((Path(tmp) / "RESULTS.csv").is_file())
            record = json.loads((Path(tmp) / "evidence" / "H1-rates-crude" / "row.json").read_text(encoding="utf-8"))
            self.assertEqual(len(record["results"]), 2)
            self.assertTrue(any(layer["name"] == "rates3_rates" for layer in record["layers"]))

    def test_a_wrong_expectation_fails_the_row(self):
        import run_smoke_headless as runner
        wrong = json.loads(json.dumps(self.rows[0]))
        wrong["id"] = "H1-wrong"
        wrong["checks"][1]["value"] = 999.0
        with tempfile.TemporaryDirectory() as tmp:
            statuses, problems = runner.run_rows([wrong], Path(tmp))
            self.assertEqual(statuses["H1-wrong"], "FAIL")
            self.assertEqual(problems, [])
            self.assertIn("FAIL", (Path(tmp) / "evidence" / "H1-wrong" / "checks.txt").read_text(encoding="utf-8"))

    def test_a_missing_tool_is_an_error_not_a_pass(self):
        import run_smoke_headless as runner
        bad = {"id": "H1-bad", "steps": [{"do": "tool", "name": "no_such_tool", "args": {}}], "checks": [{"what": "x", "step": 1, "path": "success", "op": "true"}]}
        with tempfile.TemporaryDirectory() as tmp:
            statuses, _ = runner.run_rows([bad], Path(tmp))
            self.assertEqual(statuses["H1-bad"], "FAIL")


if __name__ == "__main__":
    unittest.main()
