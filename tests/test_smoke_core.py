"""Offline tests of tools/smoke_core.py (the pure half of the agent-run smoke runner) and of docs/AGENT_RUN_ROWS.json's shape. The rule they pin: a row is PASS only when at least one machine check ran and every
check held, and an evidence folder that is missing a file is reported, not skipped."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import smoke_core as core  # noqa: E402


class TestEvaluate(unittest.TestCase):
    def test_result_checks(self):
        results = [{"loaded": "a"}, {"success": True, "overall_rate": 1000.0000004, "classes": ["x", "y"], "error": "Refused: no"}]
        self.assertTrue(core.evaluate({"step": 2, "path": "success", "op": "true"}, results)[0])
        self.assertTrue(core.evaluate({"step": 2, "path": "overall_rate", "op": "approx", "value": 1000.0}, results)[0])
        self.assertTrue(core.evaluate({"step": 2, "path": "classes.1", "op": "eq", "value": "y"}, results)[0])
        self.assertTrue(core.evaluate({"step": "last", "path": "error", "op": "contains", "value": "refused"}, results)[0])
        self.assertFalse(core.evaluate({"step": 2, "path": "overall_rate", "op": "approx", "value": 999.0}, results)[0])

    def test_unevaluable_checks_fail(self):
        results = [{"a": 1}]
        for bad in ({"step": 5, "path": "a", "op": "eq", "value": 1}, {"step": 1, "path": "missing", "op": "eq", "value": 1},
                    {"step": 1, "path": "a", "op": "weird", "value": 1}, {"step": 1, "path": "a", "op": "ge", "value": "text"}):
            ok, detail = core.evaluate(bad, results)
            self.assertFalse(ok, bad)
            self.assertTrue(detail)
        self.assertFalse(core.evaluate({"layer": "x", "field": "f", "op": "all_approx", "value": 1}, results)[0])
        self.assertFalse(core.evaluate({"layer": "x", "field": "f", "op": "all_approx", "value": 1}, results, lambda n, f: None)[0])

    def test_a_layer_that_must_be_absent(self):
        absent = {"layer": "mapping_tasks", "field": "name", "op": "absent"}
        self.assertTrue(core.evaluate(absent, [], lambda n, f: None)[0])
        self.assertFalse(core.evaluate(absent, [], lambda n, f: ["x"])[0])

    def test_layer_checks(self):
        values = lambda n, f: [1000.0, 1000.0, 1000.0]  # noqa: E731
        self.assertTrue(core.evaluate({"layer": "l", "field": "f", "op": "all_approx", "value": 1000.0}, [], values)[0])
        self.assertTrue(core.evaluate({"layer": "l", "field": "f", "op": "count_eq", "value": 3}, [], values)[0])
        self.assertFalse(core.evaluate({"layer": "l", "field": "f", "op": "all_approx", "value": 1.0}, [], values)[0])
        self.assertFalse(core.evaluate({"layer": "l", "field": "f", "op": "all_approx", "value": 1.0}, [], lambda n, f: [None, None])[0])
        self.assertTrue(core.evaluate({"layer": "l", "field": "f", "op": "max_approx", "value": 2.0, "tol": 1e-3}, [], lambda n, f: [0, 2.0004, 1])[0])


class TestVerdict(unittest.TestCase):
    def test_pass_needs_checks_that_all_held(self):
        self.assertEqual(core.verdict([(True, "")]), "PASS")
        self.assertEqual(core.verdict([]), "NO-CHECKS")
        self.assertEqual(core.verdict([(True, ""), (False, "")]), "FAIL")
        self.assertEqual(core.verdict([(True, "")], error="trace"), "ERROR")
        self.assertEqual(core.verdict([(True, "")], needs_eyes=True), "NEEDS-EYES")


class TestEvidenceFolder(unittest.TestCase):
    def test_write_and_verify(self):
        with tempfile.TemporaryDirectory() as tmp:
            row = {"id": "H9-x", "checks": [{"what": "w"}]}
            core.write_row(tmp, row, {"steps": [], "results": []}, [(True, "ok")], "PASS")
            self.assertEqual(core.verify_evidence(tmp, ["H9-x"]), [])
            self.assertIn("H8-missing: row.json missing", core.verify_evidence(tmp, ["H8-missing"]))
            core.write_row(tmp, {"id": "H7-none"}, {}, [], "PASS")
            self.assertIn("H7-none: PASS with no checks", core.verify_evidence(tmp, ["H7-none"]))
            core.write_results(tmp, [row], {"H9-x": "PASS"})
            self.assertIn("H9-x,,PASS", (Path(tmp) / "RESULTS.csv").read_text(encoding="utf-8"))


class TestRowsFile(unittest.TestCase):
    def test_every_row_has_steps_and_checks_that_name_real_steps(self):
        rows = json.loads((ROOT / "docs" / "AGENT_RUN_ROWS.json").read_text(encoding="utf-8"))["rows"]
        self.assertGreaterEqual(len(rows), 15)
        ids = [r["id"] for r in rows]
        self.assertEqual(len(ids), len(set(ids)))
        import make_full_smoke_fixtures as fx
        for r in rows:
            self.assertTrue(r["steps"] and r["checks"], r["id"])
            for s in r["steps"]:
                self.assertIn(s["do"], ("load", "load_raster", "tag", "tool", "validate_workflow"))
                if s["do"] in ("load", "load_raster", "validate_workflow"):
                    self.assertIn(s["file"], fx.FILES)
            for c in r["checks"]:
                self.assertIn("what", c)
                if "step" in c and c["step"] != "last":
                    self.assertLessEqual(c["step"], len(r["steps"]), r["id"])

    def test_the_six_broken_workflow_files_are_each_refused_with_the_sentence_the_row_expects(self):
        # LR-15: hand row W10 needed a typed command, so a click-only agent could not run it. The headless row H21 does the same
        # check with the plugin's own validator; this runs that exact validator over the generated files with no QGIS at all,
        # so the expected sentences cannot drift from what the plugin says.
        import tempfile
        import check_workflow_file as cwf
        import make_full_smoke_fixtures as fx
        row = next(r for r in json.loads((ROOT / "docs" / "AGENT_RUN_ROWS.json").read_text(encoding="utf-8"))["rows"] if r["id"] == "H21-workflow-files-refused")
        module, validate = cwf.validator(["x"])
        with tempfile.TemporaryDirectory() as tmp:
            fx.write_all(tmp)
            for index, step in enumerate(row["steps"], 1):
                report = cwf.check_file(Path(tmp) / step["file"], validate, module)
                self.assertFalse(report["accepted"], step["file"])
                wanted = [c["value"] for c in row["checks"] if c["step"] == index and c["path"] == "first_problem"]
                self.assertEqual(len(wanted), 1)
                self.assertIn(wanted[0], report["problems"][0], step["file"])
        self.assertEqual(len(row["steps"]), 6)

    def test_tool_steps_name_registered_tools(self):
        rows = json.loads((ROOT / "docs" / "AGENT_RUN_ROWS.json").read_text(encoding="utf-8"))["rows"]
        text = "".join(p.read_text(encoding="utf-8") for p in (ROOT / "src" / "cartogen_ai" / "core" / "agent" / "tools").glob("*.py"))
        for r in rows:
            for s in r["steps"]:
                if s["do"] == "tool":
                    self.assertIn(f"def {s['name']}(", text, s["name"])


if __name__ == "__main__":
    unittest.main()
