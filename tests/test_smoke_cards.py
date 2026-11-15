"""Offline tests of the computer-use smoke package: the card cleaner, the one-row-at-a-time session, the analysis that refuses an unsupported PASS, and the built zip. Rules pinned:
a result cannot be recorded without a started row, a result line is written only after the evidence step ran (and says so if it failed), an agent's PASS counts only with program-made evidence, and no card
tells the agent to type a console command (the 2026-11-13/14 run failed on exactly that)."""
import csv
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import analyze_smoke_run as an  # noqa: E402
import build_computer_use as bcu  # noqa: E402
import build_full_smoke as full  # noqa: E402
import smoke_cards as sc  # noqa: E402


def _cards():
    return sc.make_cards(full.all_rows(full.load()), bcu.machine_map()[0])


class TestCards(unittest.TestCase):
    def test_clean_drops_console_sentences_only(self):
        text = "Open Settings. Type snap('B1') in the console. Then press OK. Run begin(x) now. Send (1) Hello."
        self.assertEqual(sc.clean(text), "Open Settings. Then press OK. Send (1) Hello.")

    def test_every_row_has_one_card_without_console_instructions(self):
        cards = _cards()
        self.assertEqual(len(cards), len(full.all_rows(full.load())))
        for c in cards:
            body = " ".join([c["do"], c["expect"], c["pass_if"], c["starts_from"], c["also_capture"]])
            self.assertNotRegex(body, r"snap\(|shot\(|begin\(|collect_evidence|Python console", c["id"])
            self.assertTrue(c["do"] or not c["can_run"], c["id"])

    def test_rows_that_need_a_second_program_are_human_rows(self):
        by_id = {c["id"]: c for c in _cards()}
        for rid in ("A3-cli-bridge", "B3-language", "F1-mcp-size"):
            self.assertFalse(by_id[rid]["can_run"], rid)
            self.assertIn("NOT FOR THIS AGENT", sc.card_text(by_id[rid]))
        self.assertTrue(by_id["B1-routing-plain"]["can_run"])

    def test_machine_checked_rows_are_named_on_their_cards(self):
        by_id = {c["id"]: c for c in _cards()}
        self.assertIn("H7-cluster-scan", by_id["C23-cluster-scan"]["machine_checked_by"])
        self.assertIn("H7-cluster-scan", sc.card_text(by_id["C23-cluster-scan"]))


class TestSession(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.taken = []
        self.t = [1000.0]
        cards = [{"id": "X1", "can_run": True}, {"id": "X2", "can_run": True}]
        self.s = sc.Session(self.tmp.name, cards, lambda row, note: self.taken.append((row, note)), clock=lambda: self.t[0])

    def test_no_result_without_start_and_evidence_is_taken_before_the_line_is_written(self):
        self.assertFalse(self.s.finish("PASS")[0])
        self.assertEqual(sc.load_results(self.tmp.name), {})
        self.assertTrue(self.s.start("X1")[0])
        self.assertFalse(self.s.start("X2")[0])                      # one row at a time
        self.t[0] += 42
        self.assertTrue(self.s.finish("PASS", "saw 3 layers")[0])
        self.assertEqual(self.taken, [("X1", "saw 3 layers")])
        r = sc.load_results(self.tmp.name)["X1"]
        self.assertEqual((r["status"], r["seconds"], r["evidence_error"]), ("PASS", "42.0", ""))
        self.assertEqual(self.s.current, None)

    def test_bad_status_and_unknown_row_are_refused_and_an_evidence_failure_is_recorded(self):
        self.assertFalse(self.s.start("nope")[0])
        self.s.start("X1")
        self.assertFalse(self.s.finish("MAYBE")[0])
        self.s.snapshot = lambda row, note: (_ for _ in ()).throw(RuntimeError("no screen"))
        ok, msg = self.s.finish("PASS")
        self.assertTrue(ok)
        self.assertIn("evidence problem", msg)
        self.assertIn("RuntimeError", sc.load_results(self.tmp.name)["X1"]["evidence_error"])


def _cardfor(**kw):
    base = {"id": "X1", "can_run": True, "why_not": "", "model_needed": False}
    base.update(kw)
    return base


class TestAnalysis(unittest.TestCase):
    @property
    def ev_ok(self):
        return {"window": True, "layers": True, "plugin_evidence": True, "tools": ["a"]}

    def test_judge(self):
        claim = {"status": "PASS", "note": "", "evidence_error": ""}
        self.assertEqual(an.judge(_cardfor(), claim, self.ev_ok)[0], "VERIFIED")
        self.assertEqual(an.judge(_cardfor(), claim, {**self.ev_ok, "window": False})[0], "UNSUPPORTED")
        self.assertEqual(an.judge(_cardfor(model_needed=True), claim, {**self.ev_ok, "plugin_evidence": False})[0], "UNSUPPORTED")
        self.assertEqual(an.judge(_cardfor(), {**claim, "evidence_error": "boom"}, self.ev_ok)[0], "UNSUPPORTED")
        self.assertEqual(an.judge(_cardfor(), {**claim, "status": "FAIL", "note": "x"}, self.ev_ok)[0], "CLAIMED")
        self.assertEqual(an.judge(_cardfor(), None, self.ev_ok)[0], "NO RESULT")
        self.assertEqual(an.judge(_cardfor(can_run=False, why_not="needs GeoDa"), None, self.ev_ok)[0], "HUMAN ROW")

    def test_report_and_exit_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "evidence" / "X1" / "X1"
            folder.mkdir(parents=True)
            (folder / "window.png").write_bytes(b"png")
            (folder / "layers.json").write_text("[]")
            sc.append_result(tmp, {"row": "X1", "status": "PASS", "note": "ok", "seconds": 5})
            sc.append_result(tmp, {"row": "X2", "status": "PASS", "note": "ok", "seconds": 9})        # no evidence for X2
            (Path(tmp) / "RESULTS.csv").write_text("row,covers_row,status,evidence_folder\nH1,C24,PASS,e\n")
            text, counts, mc = an.build_report(tmp, [_cardfor(id="X1"), _cardfor(id="X2"), _cardfor(id="X3")])
            self.assertEqual(counts, {"VERIFIED": 1, "UNSUPPORTED": 1, "NO RESULT": 1})
            self.assertEqual(mc, {"PASS": 1})
            self.assertIn("| X2 | PASS | UNSUPPORTED |", text)


class TestTheBuiltPackage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        plugin = Path(cls.tmp.name) / f"cartogen_ai_v{full.v2.version()}.zip"
        with zipfile.ZipFile(plugin, "w") as z:
            z.writestr("stub.txt", "stand-in")
        cls.path, cls.n, cls.k = bcu.build(plugin, cls.tmp.name)
        cls.zip = zipfile.ZipFile(cls.path)
        cls.addClassCleanup(cls.zip.close)
        cls.top = cls.zip.namelist()[0].split("/")[0]

    def names(self):
        return {n[len(self.top) + 1:] for n in self.zip.namelist()}

    def test_the_package_has_everything_it_promises(self):
        names = self.names()
        for need in ("README.txt", "HAIKU_PROMPT.md", "cards.json", "CARDS.md", "START_QGIS.bat", "RUN_HEADLESS.bat", "ANALYZE.bat", "docs/AGENT_RUN_ROWS.json", "3_test_files/SHA256SUMS.txt",
                     "tools/smoke_dock.py", "tools/smoke_dock_start.py", "tools/smoke_cards.py", "tools/smoke_core.py", "tools/analyze_smoke_run.py", "tools/collect_evidence.py"):
            self.assertIn(need, names)
        self.assertTrue(any(n.startswith("1_plugin/") for n in names))
        self.assertTrue(any(n.startswith("plugin/cartogen_ai/core/") for n in names))
        self.assertTrue(any(n.startswith("3_test_files/smoke_districts_cases") for n in names))

    def test_cards_json_matches_the_rows_and_the_prompt_forbids_console_commands(self):
        cards = json.loads(self.zip.read(f"{self.top}/cards.json"))
        self.assertEqual(len(cards), self.n)
        self.assertGreater(self.k, 50)
        prompt = self.zip.read(f"{self.top}/HAIKU_PROMPT.md").decode()
        self.assertIn("Do not type any command into the QGIS Python console", prompt)
        self.assertIn("Never claim a result you did not see", prompt)

    def test_every_file_a_card_needs_is_shipped(self):
        names = {Path(n).name for n in self.names() if n.startswith("3_test_files/")}
        for c in json.loads(self.zip.read(f"{self.top}/cards.json")):
            for f in c["files"]:
                self.assertIn(Path(f).name, names, c["id"])

    def test_csv_of_results_header_is_stable(self):
        self.assertEqual(sc.RESULT_FIELDS[:3], ["row", "status", "note"])
        with tempfile.TemporaryDirectory() as tmp:
            sc.append_result(tmp, {"row": "A", "status": "SKIP"})
            self.assertEqual(next(csv.reader((Path(tmp) / "RESULTS_GUI.csv").read_text(encoding="utf-8").splitlines()))[:2], ["row", "status"])


if __name__ == "__main__":
    unittest.main()
