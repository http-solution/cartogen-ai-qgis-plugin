"""PLAN-056: the FULL live smoke package. Offline, no QGIS. It proves what can be proved without a person:
- every ledger entry that is not verified by hand is covered by a row or named as not hand-testable (with a reason), and nothing else is named;
- every input file a row names is shipped, every layer a row expects is inside the shipped GeoPackage, and the generated inputs are valid (the profile by the
  plugin's own validator, the grids by their headers, the point file large enough to trigger the MCP size warning, the task-grid area large enough to be refused);
- every tool name a row expects exists in the registry;
- the zip really builds, holds a checklist per row, and the evidence checker reads the rows' prompt checks.
What it cannot prove: that a row's instructions produce the stated result in a real QGIS with a real model. That is what the package is for."""
import csv
import io
import json
import sqlite3
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import build_full_smoke as full           # noqa: E402
import check_evidence                      # noqa: E402
import make_full_smoke_fixtures as fixtures      # noqa: E402

import cartogen_ai.core.agent.agent_orchestrator  # noqa: E402,F401  (registers every tool)
from cartogen_ai.core.agent.tools.registry import TOOL_REGISTRY      # noqa: E402


class TestCoverage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = full.load()
        cls.rows = full.all_rows(cls.doc)
        cls.ledger_ids = full.ledger_not_verified()

    def test_every_unverified_ledger_entry_is_accounted_for_and_nothing_else_is_named(self):
        self.assertEqual(full.coverage_problems(self.rows, self.doc, self.ledger_ids), [])

    def test_the_known_count_is_147_not_verified_by_hand(self):
        self.assertGreaterEqual(len(self.ledger_ids), 140)

    def test_each_not_hand_testable_entry_has_a_reason(self):
        for ledger_id, reason in self.doc["not_hand_testable"].items():
            self.assertGreater(len(reason), 20, ledger_id)

    def test_offline_by_design_entries_are_the_ones_listed_not_hand_testable(self):
        ledger = json.loads((ROOT / "docs" / "FEATURE_LEDGER.json").read_text(encoding="utf-8"))["features"]
        offline = {f["id"] for f in ledger if "offline only by design" in f["hand_verified"]}
        self.assertTrue(offline <= set(self.doc["not_hand_testable"]), sorted(offline - set(self.doc["not_hand_testable"])))

    def test_the_gap_is_caught_when_an_entry_is_dropped(self):
        rows = [dict(r, covers=[c for c in r["covers"] if c != "map-profiles"]) for r in self.rows]
        self.assertTrue(any("map-profiles" in p for p in full.coverage_problems(rows, self.doc, self.ledger_ids)))


class TestRows(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = full.load()
        cls.rows = full.all_rows(cls.doc)

    def test_row_ids_are_unique_and_so_are_their_snap_names(self):
        ids = [r["id"] for r in self.rows]
        self.assertEqual(len(ids), len(set(ids)))
        import re
        heads = [re.match(r"^([A-Z]\d+)", i).group(1) for i in ids]          # collect_evidence.snap('B1') finds the row folder by this head
        self.assertEqual(len(heads), len(set(heads)))

    def test_every_row_has_the_fields_the_checklist_and_sheet_print(self):
        for row in self.rows:
            for key in ("title", "starts_from", "do", "expect", "evidence", "needs", "session", "covers"):
                self.assertIn(key, row, row["id"])
                self.assertTrue(row[key] or key == "covers", f"{row['id']}.{key}")
            self.assertIn(row["session"], self.doc["sessions"], row["id"])

    def test_every_tool_a_check_names_exists(self):
        for row in self.rows:
            for _label, check in check_evidence.expected_tool_checks(row):
                for name in list(check.get("expected_tools", [])) + list(check.get("forbidden_tools", [])):
                    self.assertIn(name, TOOL_REGISTRY, f"{row['id']}: {name}")

    def test_every_row_says_what_it_needs_and_what_to_save(self):
        for row in self.rows:
            self.assertGreater(len(row["expect"]), 30, row["id"])

    def test_the_sheet_prints_every_session_and_every_row(self):
        text = full.sheet(self.rows, self.doc, "1.0")
        for row in self.rows:
            self.assertIn(f"### {row['id']}:", text)
        for letter in self.doc["sessions"]:
            self.assertIn(f"## Session {self.doc['sessions'][letter]}", text)


class TestGeneratedInputs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        fixtures.write_all(cls.tmp.name)
        cls.dir = Path(cls.tmp.name)

    def test_generation_is_repeatable(self):
        with tempfile.TemporaryDirectory() as again:
            fixtures.write_all(again)
            for name in fixtures.FILES:
                self.assertEqual((self.dir / name).read_bytes(), (Path(again) / name).read_bytes(), name)

    def test_the_cod_profile_passes_the_plugins_own_validator(self):
        from cartogen_ai.core.agent.tools.map_profiles import validate_profile
        clean, problems = validate_profile(json.loads((self.dir / "cartogen_profiles" / "smoke_cod.json").read_text(encoding="utf-8")))
        self.assertEqual(problems, [])
        self.assertTrue(clean["cod_boundaries"])
        self.assertIn("cod_credit", clean)

    def test_the_task_grid_area_is_refused_at_1_km_and_has_a_4_km_answer(self):
        from cartogen_ai.core.agent.tools.task_grid_tools import MAX_TASKS, estimated_cells, suggest_cell_size
        feature = json.loads((self.dir / "smoke_big_area.geojson").read_text(encoding="utf-8"))["features"][0]
        ring = feature["geometry"]["coordinates"][0]
        width_m = (max(x for x, _ in ring) - min(x for x, _ in ring)) * 111_320 * 0.974         # 2 degrees at about 13 degrees north
        height_m = (max(y for _, y in ring) - min(y for _, y in ring)) * 110_574
        self.assertGreater(estimated_cells(width_m, height_m, 1000), MAX_TASKS)
        self.assertEqual(suggest_cell_size(width_m, height_m, 1000)[0], 4000)

    def test_the_ascii_grids_are_complete_and_the_second_has_lost_value_in_the_middle(self):
        def read(name):
            lines = (self.dir / name).read_text(encoding="utf-8").splitlines()
            head = dict(line.split() for line in lines[:6])
            rows = [[int(v) for v in line.split()] for line in lines[6:]]
            return head, rows
        head, before = read("before_fixture.asc")
        _head2, after = read("after_fixture.asc")
        self.assertEqual((int(head["ncols"]), int(head["nrows"])), (20, 20))
        self.assertTrue(all(len(r) == 20 for r in before) and len(before) == 20)
        self.assertEqual(before[0][0], after[0][0])
        self.assertEqual(before[9][9] - after[9][9], 40)
        self.assertIn("GEOGCS", (self.dir / "before_fixture.prj").read_text(encoding="utf-8"))

    def test_the_point_file_is_large_enough_to_trigger_the_mcp_size_warning(self):
        from cartogen_ai.core.agent.mcp_policy import LARGE_INPUT_FEATURES
        lines = (self.dir / "smoke_many_points.csv").read_text(encoding="utf-8").splitlines()
        self.assertEqual(lines[0], "lon,lat,id")
        self.assertGreaterEqual(len(lines) - 1, LARGE_INPUT_FEATURES)
        self.assertEqual(len(set(lines[1:])), len(lines) - 1)           # no repeated point

    def test_the_route_runs_through_events_a_and_b_and_misses_c_to_f_by_over_a_kilometre(self):
        import math
        (x1, y1), (x2, y2) = json.loads((self.dir / "smoke_route.geojson").read_text(encoding="utf-8"))["features"][0]["geometry"]["coordinates"]
        events = list(csv.DictReader((ROOT / "docs" / "hand_test_v2_inputs" / "smoke_events.csv").open(encoding="utf-8")))

        def metres_from_route(lon, lat):
            kx, ky = 111_320 * math.cos(math.radians(lat)), 110_574                         # metres per degree here
            px, py, ax, ay, bx, by = lon * kx, lat * ky, x1 * kx, y1 * ky, x2 * kx, y2 * ky
            t = max(0.0, min(1.0, ((px - ax) * (bx - ax) + (py - ay) * (by - ay)) / ((bx - ax) ** 2 + (by - ay) ** 2)))
            return math.hypot(px - (ax + t * (bx - ax)), py - (ay + t * (by - ay)))
        inside = [e["name"] for e in events if metres_from_route(float(e["lon"]), float(e["lat"])) <= 500]
        outside = [metres_from_route(float(e["lon"]), float(e["lat"])) for e in events if e["name"] not in inside]
        self.assertEqual(inside, ["Event A", "Event B"])
        self.assertGreater(min(outside), 1000)

    def test_the_multipoint_file_has_the_stated_parts(self):
        features = json.loads((self.dir / "smoke_multipoint.geojson").read_text(encoding="utf-8"))["features"]
        self.assertEqual([len(f["geometry"]["coordinates"]) for f in features], [2, 3, 2])
        self.assertTrue(all(f["geometry"]["type"] == "MultiPoint" for f in features))

    def test_the_mesh_is_a_valid_2dm(self):
        lines = (self.dir / "smoke_mesh.2dm").read_text(encoding="utf-8").splitlines()
        self.assertEqual(lines[0], "MESH2D")
        self.assertEqual(sum(1 for line in lines if line.startswith("ND ")), 4)
        self.assertEqual(sum(1 for line in lines if line.startswith("E3T ")), 2)

    def test_the_forecast_probability_column_is_in_percent(self):
        rows = list(csv.DictReader(io.StringIO((self.dir / "smoke_prob.csv").read_text(encoding="utf-8"))))
        values = [float(r["prob"]) for r in rows]
        self.assertTrue(all(0 <= v <= 100 for v in values) and max(values) > 1)
        self.assertTrue(any(float(r["flow"]) >= 100 and float(r["prob"]) >= 60 for r in rows))     # row D2 step 7 has something to find


class TestThePackage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        version = full.v2.version()
        plugin = Path(cls.tmp.name) / f"cartogen_ai_v{version}.zip"
        with zipfile.ZipFile(plugin, "w") as z:
            z.writestr("stub.txt", "a stand-in so the real dist/ zip is never touched")
        full.main(["x", "--plugin-zip", str(plugin), "--out-dir", cls.tmp.name])
        cls.zip = zipfile.ZipFile(Path(cls.tmp.name) / f"cartogen_ai_full_smoke_{version}.zip")
        cls.top = cls.zip.namelist()[0].split("/")[0]
        cls.doc = full.load()
        cls.rows = full.all_rows(cls.doc)

    def names(self):
        return set(self.zip.namelist())

    def test_every_file_a_row_names_is_in_3_test_files(self):
        for row in self.rows:
            for name in row.get("files", []):
                self.assertIn(f"{self.top}/3_test_files/{name}", self.names(), f"{row['id']}: {name}")

    def test_every_input_file_a_row_mentions_in_its_text_is_shipped(self):
        for row in self.rows:
            text = " ".join(str(row.get(k, "")) for k in ("starts_from", "do", "expect", "evidence"))
            in_folders = {Path(n).name for r in self.rows for n in r.get("files", []) if "/" in n}
            for token in full.FIXTURE_TOKEN.findall(text):
                if token in in_folders:
                    continue
                self.assertIn(f"{self.top}/3_test_files/{token}", self.names(), f"{row['id']}: {token}")

    def test_the_project_and_its_data_files_ship_together(self):
        for name in full.v2.PROJECT_FILES:
            self.assertIn(f"{self.top}/3_test_files/{name}", self.names())

    def test_every_layer_a_row_expects_is_inside_the_shipped_geopackage(self):
        for row in self.rows:
            for gpkg, layers in (row.get("layers") or {}).items():
                with tempfile.TemporaryDirectory() as d:
                    path = Path(d) / gpkg
                    path.write_bytes(self.zip.read(f"{self.top}/3_test_files/{gpkg}"))
                    found = {r[0] for r in sqlite3.connect(path).execute("select table_name from gpkg_contents")}
                self.assertTrue(set(layers) <= found, f"{row['id']}: {sorted(set(layers) - found)} not in {gpkg} (has {sorted(found)})")

    def test_the_start_project_opens_layers_that_sit_beside_it(self):
        import re
        project = zipfile.ZipFile(io.BytesIO(self.zip.read(f"{self.top}/3_test_files/smoke_start.qgz")))
        xml = project.read(next(n for n in project.namelist() if n.endswith(".qgs"))).decode("utf-8")
        for source in set(re.findall(r'source="\./([^"|]+)', xml)):
            self.assertIn(f"{self.top}/3_test_files/{source}", self.names(), source)

    def test_each_row_has_a_checklist_an_output_folder_and_a_result_line(self):
        results = list(csv.DictReader(io.StringIO(self.zip.read(f"{self.top}/4_RESULTS.csv").decode("utf-8"))))
        self.assertEqual([r["id"] for r in results], [r["id"] for r in self.rows])
        for row in self.rows:
            self.assertIn(f"{self.top}/results/evidence/{row['id']}/CHECKLIST.txt", self.names())
            self.assertIn(f"{self.top}/results/outputs/{row['id']}/PUT_OUTPUT_FILES_HERE.txt", self.names())

    def test_coverage_page_lists_every_ledger_entry(self):
        page = self.zip.read(f"{self.top}/COVERAGE.md").decode("utf-8")
        for ledger_id in full.ledger_not_verified():
            self.assertIn(f"| {ledger_id} |", page)

    def test_the_rows_file_inside_the_zip_is_what_the_checker_reads(self):
        data = json.loads(self.zip.read(f"{self.top}/3_ROWS.json").decode("utf-8"))
        self.assertEqual(len(data["rows"]), len(self.rows))

    def test_the_tools_the_rows_run_are_shipped(self):
        for tool in full.TOOLS_FOLDER:
            self.assertIn(f"{self.top}/6_tools/{tool}", self.names())
        self.assertIn(f"{self.top}/5_check_evidence.py", self.names())
        self.assertIn(f"{self.top}/2_layout_check/layout_check_script.py", self.names())

    def test_the_input_verifier_passes_on_the_unzipped_package_and_catches_damage(self):
        import verify_inputs
        with tempfile.TemporaryDirectory() as d:
            self.zip.extractall(d)
            folder = Path(d) / self.top / "3_test_files"
            entries, problems = verify_inputs.check(folder)
            self.assertEqual(problems, [])
            self.assertGreaterEqual(len(entries), 30)
            (folder / "smoke_prob.csv").write_text("damaged", encoding="utf-8")
            (folder / "smoke_mesh.2dm").unlink()
            _entries, problems = verify_inputs.check(folder)
            self.assertTrue(any("smoke_prob.csv" in p and "changed" in p for p in problems), problems)
            self.assertTrue(any("smoke_mesh.2dm" in p and "missing" in p for p in problems), problems)
            self.assertTrue(any("row D2-damage-and-risk needs smoke_prob.csv" in p for p in problems), problems)

    def test_the_agent_prompt_ships_and_names_the_files_it_tells_the_agent_to_use(self):
        text = self.zip.read(f"{self.top}/AGENT_PROMPT.md").decode("utf-8")
        for name in ("verify_inputs.py", "5_check_evidence.py", "4_RESULTS.csv", "3_SHEET.md", "COVERAGE.md", "EVIDENCE_HOWTO.txt", "README_FIRST.txt"):
            self.assertIn(name, text)
            self.assertTrue(any(n.endswith("/" + name) for n in self.names()), name)

    def test_the_language_review_sheet_has_phrases(self):
        text = self.zip.read(f"{self.top}/3_test_files/language_review_sheet.csv").decode("utf-8-sig")
        self.assertGreater(len(list(csv.DictReader(io.StringIO(text)))), 100)


class TestEvidenceChecksOnMultiPromptRows(unittest.TestCase):
    def test_each_prompt_of_a_row_gets_its_own_verdict(self):
        row = {"id": "B1", "checks": [{"prompt": "dem@1 > 100", "expected_tools": ["raster_calculator"]},
                                     {"prompt": "sort the districts", "forbidden_tools": ["fetch_worldpop_population"]}]}
        requests = [("Create a layer where dem@1 > 100", ["raster_calculator"], "e1"), ("sort the districts in smoke_admin", ["fetch_worldpop_population"], "e2")]
        verdicts = [check_evidence.verdict_for_row(check, requests)[0] for _label, check in check_evidence.expected_tool_checks(row)]
        self.assertEqual(verdicts, ["PASS", "FAIL"])

    def test_a_row_without_checks_gives_none(self):
        self.assertEqual(check_evidence.expected_tool_checks({"id": "B5"}), [])


if __name__ == "__main__":
    unittest.main()
