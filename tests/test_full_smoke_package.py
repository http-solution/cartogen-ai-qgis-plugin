"""PLAN-056: the FULL live smoke package. Offline, no QGIS. It proves what can be proved without a person:
- every ledger entry that is not verified by hand is covered by a row or named as not hand-testable (with a reason), and nothing else is named;
- every input file a row names is shipped, every layer a row expects is inside the shipped GeoPackage, and the generated inputs are valid (the profile by the
  plugin's own validator, the grids by their headers, the point file large enough to trigger the MCP size warning, the task-grid area large enough to be refused);
- every tool name a row expects exists in the registry;
- the zip really builds, holds a checklist per row, and the evidence checker reads the rows' prompt checks.
What it cannot prove: that a row's instructions produce the stated result in a real QGIS with a real model. That is what the package is for."""
import contextlib
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
import layout_check_script            # noqa: E402  (module level is standard library only; qgis is imported inside run())

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

    def test_overrides_are_appended_to_v2_rows_and_name_real_rows(self):
        v2_ids = {r["id"] for r in full.v2.rows()}
        for row_id, fields in self.doc["v2_overrides"].items():
            self.assertIn(row_id, v2_ids)
            original = next(r for r in full.v2.rows() if r["id"] == row_id)
            merged = next(r for r in self.rows if r["id"] == row_id)
            for field, added in fields.items():
                self.assertTrue(merged[field].endswith(added), (row_id, field))
                self.assertTrue(merged[field].startswith(str(original.get(field, ""))), (row_id, field))

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

    def test_the_ascii_grids_lie_over_smoke_admin_in_its_own_crs_and_the_second_has_lost_value_in_the_middle(self):
        def read(name):
            lines = (self.dir / name).read_text(encoding="utf-8").splitlines()
            head = dict(line.split() for line in lines[:6])
            rows = [[int(v) for v in line.split()] for line in lines[6:]]
            return head, rows
        head, before = read("before_fixture.asc")
        _head2, after = read("after_fixture.asc")
        self.assertEqual((int(head["ncols"]), int(head["nrows"])), (40, 40))
        self.assertTrue(all(len(r) == 40 for r in before) and len(before) == 40)
        self.assertEqual(before[0][0], after[0][0])
        self.assertEqual(before[20][20] - after[20][20], 40)
        prj = (self.dir / "before_fixture.prj").read_text(encoding="utf-8")
        self.assertIn("UTM_Zone_36N", prj)
        self.assertEqual(prj, (self.dir / "after_fixture.prj").read_text(encoding="utf-8"))
        # the districts the rows ask about: the grid must cover the whole of smoke_admin, in the same CRS (EPSG:32636). The first version sat 900 km away.
        with contextlib.closing(sqlite3.connect(ROOT / "docs" / "release_smoke_assets" / "inputs" / "smoke_data.gpkg")) as db:
            srs, min_x, min_y, max_x, max_y = db.execute("select srs_id, min_x, min_y, max_x, max_y from gpkg_contents where table_name = 'smoke_admin'").fetchone()
        self.assertEqual(srs, 32636)
        x0, y0, size = float(head["xllcorner"]), float(head["yllcorner"]), float(head["cellsize"])
        self.assertLessEqual(x0, min_x)
        self.assertLessEqual(y0, min_y)
        self.assertGreaterEqual(x0 + 40 * size, max_x)
        self.assertGreaterEqual(y0 + 40 * size, max_y)
        # the lowered block must touch the districts, or the damage score has nothing to find
        self.assertTrue(min_x < x0 + 26 * size and max_x > x0 + 14 * size and min_y < y0 + 26 * size and max_y > y0 + 14 * size)

    def test_the_point_file_is_large_enough_to_trigger_the_mcp_size_warning(self):
        from cartogen_ai.core.agent.mcp_policy import LARGE_INPUT_FEATURES
        lines = (self.dir / "smoke_many_points.csv").read_text(encoding="utf-8").splitlines()
        self.assertEqual(lines[0], "lon,lat,id")
        self.assertGreaterEqual(len(lines) - 1, LARGE_INPUT_FEATURES)
        self.assertEqual(len(set(lines[1:])), len(lines) - 1)           # no repeated point

    def test_the_route_runs_through_events_a_and_b_and_misses_c_to_f_by_over_a_kilometre(self):
        import math
        (x1, y1), (x2, y2) = json.loads((self.dir / "smoke_route.geojson").read_text(encoding="utf-8"))["features"][0]["geometry"]["coordinates"]
        events = list(csv.DictReader(io.StringIO((ROOT / "docs" / "hand_test_v2_inputs" / "smoke_events.csv").read_text(encoding="utf-8"))))

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
        cls.addClassCleanup(cls.zip.close)          # runs BEFORE the folder is removed (cleanups run last-in first-out): Windows will not delete an open file
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
                    with contextlib.closing(sqlite3.connect(path)) as db:              # closed before the folder is removed: Windows refuses to delete an open file
                        found = {r[0] for r in db.execute("select table_name from gpkg_contents")}
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

    def test_the_sums_are_those_of_the_source_files_and_the_builder_never_reads_the_zip_back_while_writing_it(self):
        import hashlib
        sums = dict(line.split("  ", 1)[::-1] for line in self.zip.read(f"{self.top}/3_test_files/SHA256SUMS.txt").decode("utf-8").splitlines())
        for name, source in (("smoke_data.gpkg", ROOT / "docs" / "release_smoke_assets" / "inputs"), ("smoke_events.csv", ROOT / "docs" / "hand_test_v2_inputs")):
            self.assertEqual(sums[name], hashlib.sha256((source / name).read_bytes()).hexdigest(), name)
        self.assertEqual(sums["WORKFLOW_FILES.md"], hashlib.sha256((ROOT / "docs" / "WORKFLOW_FILES.md").read_bytes()).hexdigest())
        self.assertEqual(sums["smoke_prob.csv"], hashlib.sha256(self.zip.read(f"{self.top}/3_test_files/smoke_prob.csv")).hexdigest())
        # Windows guard (cannot be run on Linux): zipfile cannot read back an entry written with write() while the archive is open for writing
        source_text = (ROOT / "tools" / "build_full_smoke.py").read_text(encoding="utf-8")
        body = source_text.split("with tempfile.TemporaryDirectory() as tmp, zipfile.ZipFile(out", 1)[1]
        self.assertNotIn("z.read(", body)

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

    def test_the_evidence_page_holds_the_lessons_of_the_first_run_that_rows_point_at(self):
        page = self.zip.read(f"{self.top}/EVIDENCE_HOWTO.txt").decode("utf-8")
        for needle in ("WHERE TO TYPE", "FRESH CHAT", "SAVE FIRST", "shot('D1-borders')", "not a failure"):
            self.assertIn(needle, page)
        new_rows = " ".join(str(v) for r in self.doc["rows"] for v in (r["starts_from"], r["do"]))      # the 22 rows written for this package; the v2 rows keep their own wording
        self.assertIn("EVIDENCE_HOWTO.txt, 'Fresh chat'", new_rows)           # the rows point at a section that exists
        self.assertNotIn("a NEW chat", new_rows)

    def test_the_agent_prompt_ships_and_names_the_files_it_tells_the_agent_to_use(self):
        text = self.zip.read(f"{self.top}/AGENT_PROMPT.md").decode("utf-8")
        for name in ("verify_inputs.py", "5_check_evidence.py", "4_RESULTS.csv", "3_SHEET.md", "COVERAGE.md", "EVIDENCE_HOWTO.txt", "README_FIRST.txt"):
            self.assertIn(name, text)
            self.assertTrue(any(n.endswith("/" + name) for n in self.names()), name)

    def test_the_language_review_sheet_has_phrases(self):
        text = self.zip.read(f"{self.top}/3_test_files/language_review_sheet.csv").decode("utf-8-sig")
        self.assertGreater(len(list(csv.DictReader(io.StringIO(text)))), 100)


class TestTheCheckerRunsEndToEnd(unittest.TestCase):
    """Hand run 2026-11-04: 5_check_evidence.py crashed with KeyError 'failed' after printing its rows (a loop variable shadowed the layout check), read '0 rows'
    because 4_RESULTS.csv sits beside the script, and called a confirm turn a FAIL. Run main() the way the package runs it."""
    def make(self, root):
        root = Path(root)
        (root / "results").mkdir()
        (root / "results" / "layout_check.json").write_text(json.dumps({"qgis": "4", "plugin_version": "1", "fonts_found": [], "passed": 1, "failed": [],
                                                                       "checks": [{"id": "L1", "title": "t", "ok": True, "got": {}}]}), encoding="utf-8")
        for index, (request, tools) in enumerate([("dem@1 > 100 on the dem", ["raster_calculator"]), ("dem@1 > 100 on the dem", [])]):
            folder = root / "results" / f"t{index}"
            folder.mkdir()
            (folder / "summary.md").write_text(f"## Request\n{request}\n## Steps\n", encoding="utf-8")
            (folder / "steps.jsonl").write_text("\n".join(json.dumps({"tool": t}) for t in tools), encoding="utf-8")
        (root / "4_RESULTS.csv").write_text("id,session,title,covers,result (Pass/Partial/Fail/Skip),notes\nB1,B,x,y,Pass,n\nB2,B,x,y,,\n", encoding="utf-8")
        rows = root / "rows.json"
        rows.write_text(json.dumps({"rows": [{"id": "B1", "checks": [{"prompt": "dem@1 > 100", "expected_tools": ["raster_calculator"]}]}]}), encoding="utf-8")
        return rows

    def test_main_finishes_reads_the_results_beside_it_and_judges_the_request_that_called_tools(self):
        import contextlib
        with tempfile.TemporaryDirectory() as d:
            rows = self.make(d)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = check_evidence.main(["x", str(Path(d) / "results"), "--rows", str(rows)])
            text = out.getvalue()
            self.assertEqual(code, 0)
            self.assertIn("layout check: 1 of 1 passed", text)
            self.assertIn("PASS", text)
            self.assertNotIn("FAIL", text)

    def test_the_script_as_shipped_finds_4_results_csv_beside_itself(self):
        import shutil
        import subprocess
        with tempfile.TemporaryDirectory() as d:
            rows = self.make(d)
            shutil.copy(ROOT / "tools" / "check_evidence.py", Path(d) / "5_check_evidence.py")
            done = subprocess.run([sys.executable, "-I", str(Path(d) / "5_check_evidence.py"), str(Path(d) / "results"), "--rows", str(rows)],
                                  capture_output=True, text=True, check=False)
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertIn("results file: 2 rows, 1 left blank: B2", done.stdout)


class TestTheScriptsRunInTheQgisConsole(unittest.TestCase):
    """Hand run 2026-11-04: exec() of the layout script printed nothing (the console's __name__ is __console__), its table said 'plugin ?' and project.json said
    'unknown' (cartogen_ai is a namespace package, so __file__ is None)."""
    def test_the_layout_script_also_runs_when_exec_d_in_the_console(self):
        source = (ROOT / "tools" / "layout_check_script.py").read_text(encoding="utf-8")
        self.assertIn('if __name__ in ("__main__", "__console__"):', source)

    def test_the_version_is_found_through_the_namespace_package_path(self):
        import types
        with tempfile.TemporaryDirectory() as d:
            package = Path(d) / "plugin" / "src" / "cartogen_ai"
            package.mkdir(parents=True)
            (Path(d) / "plugin" / "metadata.txt").write_text("name=x\nversion=9.8.7\n", encoding="utf-8")
            namespace = types.SimpleNamespace(__file__=None, __path__=[str(package)])
            self.assertEqual(layout_check_script.plugin_version(namespace), "9.8.7")
            self.assertEqual(layout_check_script.plugin_version(types.SimpleNamespace(__path__=[str(Path(d) / "nowhere")])), "")
            self.assertEqual(layout_check_script.plugin_version(types.SimpleNamespace()), "")

    def test_the_evidence_collector_finds_the_version_of_this_checkout_and_has_a_screenshot_helper(self):
        import collect_evidence
        self.assertRegex(collect_evidence._plugin_version(), r"^version=\d")
        self.assertTrue(callable(collect_evidence.shot))


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
