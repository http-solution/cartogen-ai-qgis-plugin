"""Rows C20 to C27 of the full smoke package (PLAN-056 / PLAN-023 R2): the inputs they ship are what the rows say, every number the rows quote is recomputed here from the shipped files with the plugin's own
pure code (so a row cannot drift from the code or from its file), every console command a row tells a person to type names a real function with arguments it really has, and EVERY row of the package asks for its
evidence. Offline, no QGIS. What it cannot prove: that QGIS loads these files the way the rows say (tests/test_full_smoke_fixtures_live.py reads them back in CI's QGIS job)."""
import ast
import importlib
import inspect
import itertools
import json
import re
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import build_full_smoke as full           # noqa: E402
import make_full_smoke_fixtures as fx     # noqa: E402

from cartogen_ai.core.agent.tools import _health_rates as hr          # noqa: E402
from cartogen_ai.core.agent.tools import _kulldorff as kd             # noqa: E402
from cartogen_ai.core.agent.tools import _spatial_stats as ss         # noqa: E402
from cartogen_ai.core.agent.tools import _spatial_weights as sw       # noqa: E402
from cartogen_ai.core.representation import epi_look                  # noqa: E402

ROW_IDS = ("C20-environment-looks", "C21-spatial-autocorrelation", "C22-hotspots-gi-star", "C23-cluster-scan", "C24-health-rates", "C25-public-health-look", "C26-r2-routing", "C27-geocode-protected")


def _rows():
    return {r["id"]: r for r in full.all_rows(full.load())}


class Inputs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        fx.write_all(cls.tmp.name)
        cls.dir = Path(cls.tmp.name)

    def load(self, name):
        return json.loads((self.dir / name).read_text(encoding="utf-8"))

    def features(self, name):
        return self.load(name)["features"]

    def rings(self, name):
        return [[[(x, y) for x, y in ring] for ring in f["geometry"]["coordinates"]] for f in self.features(name)]


class TestTheFilesAreWhatTheRowsSay(Inputs):
    def test_the_district_layer_has_100_squares_in_a_projected_crs_with_the_planted_block_and_four_small_numbers(self):
        doc = self.load("smoke_districts_cases.geojson")
        self.assertEqual(doc["crs"]["properties"]["name"], "urn:ogc:def:crs:EPSG::32636")
        props = {f["properties"]["name"]: f["properties"] for f in doc["features"]}
        self.assertEqual(len(props), 100)
        self.assertEqual(sorted(props)[:3], ["D00", "D01", "D02"])
        self.assertTrue(all(p["population"] == 1000 for p in props.values()))
        block = [f"D{r}{c}" for r in (3, 4, 5) for c in (3, 4, 5)]
        self.assertEqual([props[n]["cases"] for n in block], [15] * 9)
        self.assertEqual(sorted(n for n, p in props.items() if p["cases"] < 5), ["D00", "D09", "D90", "D99"])
        total = sum(p["cases"] for p in props.values())
        self.assertEqual(total, 707)
        self.assertEqual(props["D44"]["expected"], round(total / 100000 * 1000, 2))           # expected = overall rate x population, said to be a stand-in
        for n, p in props.items():
            if n not in block:
                self.assertLessEqual(p["cases"], 8, n)
        for field in ("burglaries", "vacant_buildings", "price_index", "pm25"):
            inside = min(props[n][field] for n in block)
            outside = max(p[field] for n, p in props.items() if n not in block)
            self.assertGreater(inside, outside, field)                                         # the block really is the high area in every field

    def test_the_squares_are_one_kilometre_and_touch_exactly(self):
        rings = self.rings("smoke_districts_cases.geojson")
        xs = sorted({x for r in rings for ring in r for x, _ in ring})
        self.assertEqual(xs[0], 775000.0)
        self.assertEqual([b - a for a, b in itertools.pairwise(xs)], [1000.0] * 10)
        self.assertEqual(sw.islands(sw.contiguity(rings, "queen")), [])

    def test_the_checkerboard_the_single_high_cell_and_the_three_rate_areas(self):
        checker = self.features("smoke_checker4.geojson")
        self.assertEqual(sorted({f["properties"]["v"] for f in checker}), [-1.0, 1.0])
        self.assertEqual(len(checker), 16)
        high = self.features("smoke_one_high5.geojson")
        self.assertEqual(len(high), 25)
        self.assertEqual({f["properties"]["name"]: f["properties"]["v"] for f in high if f["properties"]["v"]}, {"H22": 10.0})
        rates = [f["properties"] for f in self.features("smoke_rates3.geojson")]
        self.assertEqual([(p["cases"], p["population"]) for p in rates], [(10, 1000), (20, 2000), (30, 3000)])
        self.assertEqual([p["expected"] for p in rates], [8.0, 25.0, 30.0])

    def test_the_land_cover_raster_has_the_stated_classes_geometry_and_prj(self):
        lines = (self.dir / "smoke_worldcover.asc").read_text(encoding="utf-8").splitlines()
        header = dict(line.split() for line in lines[:6])
        self.assertEqual((header["ncols"], header["nrows"], header["xllcorner"], header["yllcorner"], header["cellsize"]), ("40", "40", "775400", "3537600", "100"))
        grid = [[int(v) for v in line.split()] for line in lines[6:]]
        self.assertEqual((len(grid), {len(r) for r in grid}), (40, {40}))
        values = {v for r in grid for v in r}
        self.assertEqual(values, {10, 30, 40, 50, 80, 11})
        self.assertEqual(sum(v == 11 for r in grid for v in r), 4)                              # the 2 x 2 patch of the value that is not a class
        self.assertEqual(grid[0][0], 10)                                                        # north-west: tree cover (row 0 of an ASCII grid is the north)
        self.assertEqual(grid[0][39], 40)                                                       # north-east: cropland
        self.assertEqual(grid[39][20], 80)                                                      # the bottom strip: water
        self.assertIn("UTM_Zone_36N", (self.dir / "smoke_worldcover.prj").read_text(encoding="utf-8"))
        from cartogen_ai.core.representation import style_looks
        codes = {e["code"] for e in style_looks.worldcover_entries()}
        self.assertTrue({10, 30, 40, 50, 80} <= codes and 11 not in codes)

    def test_the_change_classes_use_the_codes_and_words_the_tool_accepts(self):
        from cartogen_ai.core.representation import style_looks
        for f in self.features("smoke_change_classes.geojson"):
            self.assertIsNotNone(style_looks.change_lookup(f["properties"]["change"]), f["properties"])
            self.assertIsNotNone(style_looks.change_lookup(f["properties"]["change_word"]), f["properties"])

    def test_the_geocoding_inputs_are_fictional_or_public_and_in_wgs84(self):
        clients = self.features("smoke_clients.geojson")
        self.assertEqual(len(clients), 4)
        for f in clients:
            self.assertRegex(f["properties"]["address"], r"Example|Sample|Fictional|Test")        # no real person's address
            self.assertEqual(f["geometry"]["type"], "Point")
        self.assertNotIn("crs", self.load("smoke_clients.geojson"))
        self.assertEqual(len(self.features("smoke_clinics.geojson")), 3)

    def test_the_generator_is_repeatable(self):
        again = tempfile.TemporaryDirectory()
        self.addCleanup(again.cleanup)
        fx.write_all(again.name)
        for name in fx.FILES:
            self.assertEqual((Path(again.name) / name).read_bytes(), (self.dir / name).read_bytes(), name)


class TestEveryNumberAYetUnrunRowQuotesIsTheCodesOwn(Inputs):
    def test_morans_i_hotspots_rates_and_look_classes_in_the_rows_are_recomputed(self):
        rows = _rows()
        rings = self.rings("smoke_districts_cases.geojson")
        cases = [f["properties"]["cases"] for f in self.features("smoke_districts_cases.geojson")]
        pops = [f["properties"]["population"] for f in self.features("smoke_districts_cases.geojson")]
        queen, rook = sw.contiguity(rings, "queen"), sw.contiguity(rings, "rook")
        moran = ss.morans_i(cases, queen, "row", 999, 1)
        c21 = rows["C21-spatial-autocorrelation"]["expect"]
        for text in (f"moran_i {moran['I']:.4f}", f"expected_i {moran['expected_I']:.4f}", f"z_permutation about {moran['z_sim']:.2f}", f"p_value {moran['p_value']:.3f}", f"mean_neighbours {sw.mean_neighbours(queen):.2f}",
                     f"rook gives moran_i {ss.morans_i(cases, rook, 'row', 999, 1)['I']:.4f}"):
            self.assertIn(text, c21)
        lisa = ss.local_morans(cases, queen, "row", 999, 1, 0.05)["counts"]
        self.assertIn(f"HH {lisa['HH']}, LL {lisa['LL']}, HL {lisa['HL']}, LH {lisa['LH']}, not significant {lisa['not significant']}", c21)
        checker = self.features("smoke_checker4.geojson")
        nb = sw.contiguity(self.rings("smoke_checker4.geojson"), "rook")
        m4 = ss.morans_i([f["properties"]["v"] for f in checker], nb, "row", 999, 1)
        self.assertAlmostEqual(m4["I"], -1.0, places=12)                                         # the tool prints it rounded to 4 places: -1.0
        self.assertEqual((round(m4["I"], 4), round(m4["expected_I"], 4), sw.link_count(nb)), (-1.0, -0.0667, 48))
        self.assertIn("moran_i -1.0 exactly, expected_i -0.0667", c21)
        c22 = rows["C22-hotspots-gi-star"]["expect"]
        h = ss.hotspots(cases, queen, True, 0.05)
        names = [f["properties"]["name"] for f in self.features("smoke_districts_cases.geojson")]
        hot = [names[i] for i, x in enumerate(h["features"]) if x["class"].startswith("Hot")]
        self.assertEqual(hot, ["D33", "D34", "D35", "D43", "D44", "D45", "D53", "D54", "D55"])
        self.assertIn(f"{h['counts'].get('Hot spot 99%', 0)} 'Hot spot 99%' and {h['counts'].get('Hot spot 95%', 0)} 'Hot spot 95%'", c22)
        self.assertIn(f"D44 has gi_z {h['features'][44]['z']:.4f}", c22)
        self.assertIn(f"gi_p {h['features'][33]['p_value']:.6f} and gi_q {h['features'][33]['p_adjusted']:.6f}", c22)
        one = ss.hotspots([f["properties"]["v"] for f in self.features("smoke_one_high5.geojson")], sw.contiguity(self.rings("smoke_one_high5.geojson"), "rook"), False, 0.05)
        self.assertAlmostEqual(one["features"][12]["z"], 2.0, places=12)
        self.assertAlmostEqual(one["features"][0]["z"], -0.3693, places=4)
        self.assertEqual(one["counts"], {"Not significant": 20, "Hot spot 95%": 5})
        a = hr.analyse(cases, pops, "crude", None, 100000, None, 5)
        c24 = rows["C24-health-rates"]["expect"]
        self.assertEqual(a["flagged"], 4)
        for text in (f"overall_rate {a['overall_rate']:.1f}", f"flagged_small_numbers {a['flagged']}", f"rel_risk {a['areas'][44]['rel_risk']:.4f}", f"rate_lo {round(a['areas'][44]['rate_lo'], 4)}", f"rate_hi {round(a['areas'][44]['rate_hi'], 4)}"):
            self.assertIn(text, c24)
        eb = hr.analyse(cases, pops, "eb", None, 100000, None, 5)["areas"]
        self.assertIn(f"{eb[44]['eb_rate']:.3f}", c24)
        r3 = hr.analyse([10, 20, 30], [1000, 2000, 3000], "smr", [8.0, 25.0, 30.0], 100000, None, 5)["areas"]
        self.assertEqual([x["rate"] for x in r3], [1000.0] * 3)
        self.assertEqual([round(x["smr"], 4) for x in r3], [1.25, 0.8, 1.0])
        plan = epi_look.rate_classes([None if x["flag"] else x["rate"] for x in a["areas"]], 5)
        c25 = rows["C25-public-health-look"]["expect"]
        self.assertIn(f"{len(plan['classes'])} classes", c25)
        for c in plan["classes"]:
            self.assertIn(c["label"], c25)
        self.assertIn(f"classes_dropped {plan['dropped']}", c25)
        self.assertIn(f"shown {plan['shown']}", c25)

    @unittest.skipUnless(kd.HAVE_NUMPY, "numpy not installed")
    def test_the_scan_numbers_in_the_row_are_recomputed(self):
        feats = self.features("smoke_districts_cases.geojson")
        rings = self.rings("smoke_districts_cases.geojson")
        cent = [(sum(x for x, _ in r[0][:4]) / 4, sum(y for _, y in r[0][:4]) / 4) for r in rings]
        cases = [f["properties"]["cases"] for f in feats]
        pops = [f["properties"]["population"] for f in feats]
        c23 = _rows()["C23-cluster-scan"]["expect"]
        best = kd.scan(cases, pops, cent, 0.5, None, 999, 1, 5, 0.05)["clusters"][0]
        names = [f["properties"]["name"] for f in feats]
        self.assertEqual(names[best["centre"]], "D44")
        self.assertEqual((len(best["members"]), best["cases"]), (9, 135))
        self.assertLessEqual(best["p_value"], 0.01)
        for text in (f"{best['expected']:.2f} expected (relative risk {round(best['relative_risk'], 3)})", f"llr {best['llr']:.3f}", f"radius {best['radius']:.3f}", f"total_cases {sum(cases)}"):
            self.assertIn(text, c23)
        capped = kd.scan(cases, pops, cent, 0.05, None, 999, 1, 5, 0.05)["clusters"]
        self.assertTrue(all(len(c["members"]) <= 5 for c in capped))
        self.assertIn(f"{capped[0]['cases']} cases and relative risk {capped[0]['relative_risk']:.3f}", c23)


class TestTheConsoleCommandsInTheRowsAreReal(unittest.TestCase):
    CALLS = re.compile(r"\b(moran|gi|scan|rates|look|lc)\(")
    IMPORT = re.compile(r"from (cartogen_ai[\w.]+) import (\w+) as (\w+)")

    def calls_in(self, text):
        found = []
        for m in self.CALLS.finditer(text):
            depth, i = 0, m.end() - 1
            while i < len(text):
                depth += (text[i] == "(") - (text[i] == ")")
                i += 1
                if depth == 0:
                    break
            found.append(text[m.start():i])
        return found

    def test_every_import_resolves_and_every_call_has_arguments_the_function_takes(self):
        checked = 0
        for rid in ROW_IDS:
            text = _rows()[rid]["do"]
            aliases = {}
            for module, name, alias in self.IMPORT.findall(text):
                aliases[alias] = getattr(importlib.import_module(module), name)
            for call in self.calls_in(text):
                alias = call.split("(")[0]
                self.assertIn(alias, aliases, f"{rid}: {call} uses an alias the row never imports")
                tree = ast.parse(call, mode="eval").body
                params = inspect.signature(aliases[alias]).parameters
                self.assertLessEqual(len(tree.args), len(params), f"{rid}: {call}")
                for kw in tree.keywords:
                    self.assertIn(kw.arg, params, f"{rid}: {call} passes {kw.arg}, which {alias} does not take")
                checked += 1
        self.assertGreater(checked, 25)

    def test_every_layer_name_a_call_uses_is_loaded_by_the_row_or_made_by_a_tool(self):
        for rid in ROW_IDS:
            text = _rows()[rid]["do"] + " " + _rows()[rid]["starts_from"]
            loaded = set(re.findall(r'add(?:Vector|Raster)Layer\([^)]*?, ["\'](\w+)["\']', text))
            made = ("_lisa", "_gi_star", "_scan_clusters", "_rates")
            for call in self.calls_in(_rows()[rid]["do"]):
                first = re.search(r"\(\s*'([\w]+)'", call)
                if first:
                    name = first.group(1)
                    self.assertTrue(name in loaded or any(name.endswith(s) for s in made), f"{rid}: {call} uses layer {name}, which the row neither loads nor makes")

    def test_the_fixture_folder_placeholder_is_the_one_the_evidence_page_explains(self):
        for rid in ROW_IDS:
            text = json.dumps(_rows()[rid])
            if "3_test_files" in text:
                self.assertIn("<bundle>", text, rid)

    def test_the_files_each_row_lists_are_all_generated_and_all_named_in_its_steps(self):
        for rid in ROW_IDS:
            row = _rows()[rid]
            for name in row["files"]:
                self.assertIn(name, fx.FILES, f"{rid}: {name} is not generated")
                if not name.endswith(".prj"):
                    self.assertIn(name, row["do"] + row["starts_from"], f"{rid}: lists {name} but never uses it")


class TestEveryRowAsksForItsEvidence(unittest.TestCase):
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
        cls.addClassCleanup(cls.zip.close)
        cls.top = cls.zip.namelist()[0].split("/")[0]
        cls.rows = full.all_rows(full.load())

    def test_every_row_has_a_save_line_in_the_sheet_the_evidence_table_and_its_checklist_with_the_collect_reminder(self):
        sheet = self.zip.read(f"{self.top}/3_SHEET.md").decode("utf-8")
        table = self.zip.read(f"{self.top}/EVIDENCE_TABLE.md").decode("utf-8")
        self.assertGreater(len(self.rows), 60)
        for row in self.rows:
            reminder = full.evidence_reminder(row)
            self.assertTrue(row["evidence"].strip(), row["id"])
            self.assertEqual(sheet.count(reminder), 1, row["id"])
            self.assertEqual(table.count(reminder), 1, row["id"])
            self.assertIn(reminder, self.zip.read(f"{self.top}/results/evidence/{row['id']}/CHECKLIST.txt").decode("utf-8").replace("\r\n", "\n"), row["id"])

    def test_the_reminder_names_the_snap_the_folders_the_results_file_and_the_failure_protocol(self):
        text = full.evidence_reminder(self.rows[0])
        for part in ("snap('A1')", "results\\outputs\\A1-layout-script\\", "results\\screens\\", "4_RESULTS.csv", "FAILURE_PROTOCOL.md", "Pass / Partial / Fail / Skip"):
            self.assertIn(part, text)

    def test_the_new_rows_name_a_destination_for_every_item_they_ask_to_save(self):
        rows = _rows()
        for rid in ROW_IDS:
            evidence = rows[rid]["evidence"]
            self.assertIn("results\\", evidence, rid)
            self.assertTrue(re.search(r"snap\('C\d+'\)", evidence), rid)
            self.assertTrue(rows[rid].get("outputs"), rid)

    def test_the_package_ships_every_file_the_new_rows_name(self):
        shipped = {n.split("/3_test_files/")[1] for n in self.zip.namelist() if "/3_test_files/" in n}
        for rid in ROW_IDS:
            for name in _rows()[rid]["files"]:
                self.assertIn(name, shipped, f"{rid}: {name}")


if __name__ == "__main__":
    unittest.main()
