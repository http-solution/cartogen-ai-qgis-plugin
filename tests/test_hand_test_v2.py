"""PLAN-021 WP-G, no QGIS needed: the v2 hand-test sheet is generated, independent and not stale; the evidence checker judges what files show."""
import importlib.util
import json
import re
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestSheetIsGeneratedAndNotStale(unittest.TestCase):
    def setUp(self):
        self.builder = _load("build_hand_test_v2")
        self.version = self.builder.version()

    def test_the_version_comes_from_metadata_not_from_the_rows(self):
        meta = (ROOT / "metadata.txt").read_text(encoding="utf-8")
        self.assertIn(f"version={self.version}", meta)
        raw = (ROOT / "docs" / "HAND_TEST_V2_ROWS.json").read_text(encoding="utf-8")
        self.assertFalse(re.findall(r"\b1\.\d+\.\d+\b", raw), "a typed version number in the rows; use {version}")

    def test_the_sheet_and_readme_name_the_built_version_and_nothing_stale(self):
        text = self.builder.sheet(self.version)
        self.assertIn(self.version, text)
        self.assertEqual(self.builder.stale_words(text + self.builder.readme(self.version, 2)), [])

    def test_every_row_states_where_it_starts_and_none_depends_on_another(self):
        for row in self.builder.rows():
            self.assertTrue(row["starts_from"].strip(), row["id"])
            blob = " ".join(str(row[k]) for k in ("do", "expect", "starts_from")).lower()
            for phrase in ("previous row", "row above", "the row before", "as in the last row", "continue from"):
                self.assertNotIn(phrase, blob, row["id"])
            self.assertTrue({"id", "issue", "title", "do", "expect", "evidence", "needs"} <= set(row), row["id"])

    def test_the_readme_carries_the_update_steps_the_update_row_points_to(self):
        readme = self.builder.readme(self.version, len(self.builder.rows()))
        self.assertIn("UPDATING AN EXISTING INSTALL", readme)
        self.assertIn(f'Version {self.version}', readme)
        self.assertIn("2_layout_check", readme)
        update_row = next(r for r in self.builder.rows() if r["id"] == "V1-update")
        self.assertIn("Updating an existing install", update_row["do"])

    def test_every_row_that_judges_tools_has_a_prompt_to_find_its_evidence_by(self):
        for row in self.builder.rows():
            if row.get("expected_tools") or row.get("forbidden_tools") or row.get("max_calls"):
                self.assertTrue(row.get("prompt", "").strip(), row["id"])
                self.assertIn(row["prompt"].lower().split()[0], row["do"].lower(), row["id"])

    def test_every_input_file_a_row_names_exists(self):
        text = self.builder.sheet(self.version)
        for name in set(re.findall(r"smoke_[A-Za-z_]+\.[a-z]+", text)):
            self.assertTrue((self.builder.INPUTS / name).is_file() or (self.builder.EXTRA_INPUTS / name).is_file(), name)


class TestLayoutCheckScriptShape(unittest.TestCase):
    def test_it_compiles_and_every_check_id_is_unique(self):
        source = (ROOT / "tools" / "layout_check_script.py").read_text(encoding="utf-8")
        compile(source, "layout_check_script.py", "exec")
        ids = re.findall(r'record\(f?"([A-Z0-9-]+)', source)
        self.assertGreaterEqual(len(ids), 10)
        self.assertEqual(len(ids), len(set(ids)), ids)

    def test_it_makes_no_model_call(self):
        source = (ROOT / "tools" / "layout_check_script.py").read_text(encoding="utf-8")
        for word in ("providers", "CartogenAi(", "agent_orchestrator", "requests."):
            self.assertNotIn(word, source)


class TestEvidenceChecker(unittest.TestCase):
    def setUp(self):
        self.checker = _load("check_evidence")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def _evidence(self, name, request, tools):
        folder = self.root / "cartogen_evidence" / name
        folder.mkdir(parents=True)
        (folder / "summary.md").write_text(f"# Evidence\n\n## Request\n\n{request}\n\n## Steps\n", encoding="utf-8")
        (folder / "steps.jsonl").write_text("\n".join(json.dumps({"n": i, "tool": t, "ok": True}) for i, t in enumerate(tools, 1)), encoding="utf-8")

    def test_a_forbidden_tool_fails_the_row_and_the_tools_are_listed(self):
        self._evidence("t1", "draw contour lines of the dem every 100", ["run_steps", "fetch_dem", "generate_contours"])
        row = {"prompt": "contour lines of the dem", "expected_tools": ["generate_contours"], "forbidden_tools": ["fetch_dem", "run_steps"]}
        verdict, note = self.checker.verdict_for_row(row, self.checker.evidence_requests(self.root))
        self.assertEqual(verdict, "FAIL")
        self.assertIn("fetch_dem", note)

    def test_the_expected_tool_alone_passes(self):
        self._evidence("t1", "draw contour lines of the dem every 100", ["generate_contours"])
        row = {"prompt": "contour lines of the dem", "expected_tools": ["generate_contours", "gdal:contour"], "forbidden_tools": ["fetch_dem"]}
        self.assertEqual(self.checker.verdict_for_row(row, self.checker.evidence_requests(self.root))[0], "PASS")

    def test_a_tool_called_more_often_than_its_limit_fails_the_row(self):
        self._evidence("t1", "draw an elevation profile along the road", ["set_layer_elevation", "list_layout_items", "list_layout_items", "list_layout_items"])
        row = {"prompt": "elevation profile", "expected_tools": ["set_layer_elevation"], "max_calls": {"list_layout_items": 2}}
        verdict, note = self.checker.verdict_for_row(row, self.checker.evidence_requests(self.root))
        self.assertEqual(verdict, "FAIL")
        self.assertIn("list_layout_items x3", note)

    def test_a_request_with_no_evidence_is_reported_as_such(self):
        row = {"prompt": "something never asked", "expected_tools": ["x"]}
        self.assertEqual(self.checker.verdict_for_row(row, self.checker.evidence_requests(self.root))[0], "NO EVIDENCE")

    def test_blank_result_rows_and_failed_layout_checks_are_found(self):
        (self.root / "4_RESULTS.csv").write_text("id,row,prompt,result (Pass/Partial/Fail/Skip),notes\nV1,#224,x,Pass,\nV2,#223,y,,\n", encoding="utf-8")
        (self.root / "layout_check.json").write_text(json.dumps({"passed": 1, "failed": ["L2"], "qgis": "4.2.2", "plugin_version": "1.18.0", "fonts_found": [],
                                                                 "checks": [{"id": "L1", "title": "a", "ok": True, "got": {}},
                                                                            {"id": "L2", "title": "b", "ok": False, "got": {"footer_check": {"fits": False}}}]}),
                                                      encoding="utf-8")
        self.assertEqual([r["id"] for r in self.checker.load_results(self.root)], ["V1", "V2"])
        self.assertEqual(self.checker.load_layout_check(self.root)["failed"], ["L2"])


if __name__ == "__main__":
    unittest.main()
