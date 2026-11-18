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


class TestWindowsPieces(unittest.TestCase):
    def test_the_screen_capture_runs_outside_qgis_and_only_on_windows(self):
        argv = sc.screen_capture_command(r"C:\Pkg\results\screens\it's.png", platform="win32")
        self.assertEqual(argv[0], "powershell")
        self.assertIn("CopyFromScreen", argv[-1])
        self.assertIn("it''s.png", argv[-1])                                                # a quote in the path is escaped, not executed
        self.assertIsNone(sc.screen_capture_command("x.png", platform="linux"))

    def test_script_rows_are_now_the_agents_and_their_commands_run_through_py_bat(self):
        by_id = {c["id"]: c for c in _cards()}
        for rid in ("A1-layout-script", "W9-import-good"):
            self.assertTrue(by_id[rid]["can_run"], rid)
        self.assertIn("results\\outputs\\A1-layout-script", by_id["A1-layout-script"]["do"])
        self.assertNotRegex(by_id["A1-layout-script"]["do"], r"Temp")
        self.assertIn("layout_check_script.py", by_id["A1-layout-script"]["do"])
        self.assertIn("<PACKAGE>", by_id["A1-layout-script"]["do"])

    def test_no_runnable_card_lost_its_setup_text_and_none_points_at_a_missing_document(self):
        for c in _cards():
            if c["can_run"]:
                self.assertTrue(c["starts_from"], c["id"])
                body = " ".join([c["starts_from"], c["do"], c["expect"], c["pass_if"]])
                self.assertNotRegex(body, r"EVIDENCE_HOWTO|3_SHEET|CHECKLIST|README_FIRST", c["id"])

    def test_the_general_rules_the_cards_rely_on_are_added_where_needed(self):
        by_id = {c["id"]: c for c in _cards()}
        text = sc.card_text(by_id["B1-routing-plain"])
        self.assertIn("FRESH CHAT", text)
        self.assertIn("COPY:", text)
        self.assertIn(r"<PACKAGE>\results\outputs\B1-routing-plain", text)
        self.assertIn("SAVE FIRST", sc.card_text(by_id["D5-task-grid"]))
        self.assertIn("BROWSERS", sc.card_text(by_id["W5-hdx-ranked"]))
        self.assertNotIn("BROWSERS", sc.card_text(by_id["A2-settings-connections"]))
        self.assertIn("Preview pane", by_id["A1-layout-script"]["do"])
        self.assertIn("Alt+P", by_id["A1-layout-script"]["do"])

    def test_human_rows_and_slow_rows(self):
        by_id = {c["id"]: c for c in _cards()}
        for rid in ("V1-update", "F3-check-evidence", "A3-cli-bridge", "W6-mcp-probe", "W7-mcp-dialog", "W8-export", "W10-import-bad", "C18-persona-upgrade"):
            self.assertFalse(by_id[rid]["can_run"], rid)
        slow = [c["id"] for c in by_id.values() if c["slow"] and c["can_run"]]
        self.assertIn("B4-long-request", slow)
        self.assertIn("SLOW ROW", sc.card_text(by_id["B4-long-request"]))
        self.assertNotIn("SLOW ROW", sc.card_text(by_id["A2-settings-connections"]))


class TestHumanRows(unittest.TestCase):
    def test_human_rows_are_recorded_as_skip_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            cards = [{"id": "H1", "can_run": False, "why_not": "needs GeoDa"}, {"id": "R1", "can_run": True, "why_not": ""}]
            self.assertEqual(sc.record_human_rows(tmp, cards), ["H1"])
            self.assertEqual(sc.record_human_rows(tmp, cards), [])                     # already recorded: not repeated
            rec = sc.load_results(tmp)
            self.assertEqual((rec["H1"]["status"], rec["H1"]["note"]), ("SKIP", "human row: needs GeoDa"))
            self.assertNotIn("R1", rec)


class TestRecordResult(unittest.TestCase):
    def test_a_result_can_be_recorded_from_the_command_line_and_a_bad_row_is_refused(self):
        import subprocess
        import shutil
        with tempfile.TemporaryDirectory() as tmp:
            pkg = Path(tmp) / "pkg"
            (pkg / "tools").mkdir(parents=True)
            for f in ("record_result.py", "smoke_cards.py"):
                shutil.copy(ROOT / "tools" / f, pkg / "tools" / f)
            (pkg / "cards.json").write_text(json.dumps([{"id": "X1"}]))
            def run(*a):
                return subprocess.run([sys.executable, "-I", str(pkg / "tools" / "record_result.py"), *a], capture_output=True, text=True, check=False)
            self.assertEqual(run("X9", "PASS", "n").returncode, 2)
            self.assertEqual(run("X1", "MAYBE", "n").returncode, 2)
            ok = run("X1", "fail", "it crashed")
            self.assertEqual(ok.returncode, 0, ok.stderr)
            r = sc.load_results(str(pkg / "results"))["X1"]
            self.assertEqual((r["status"], r["note"]), ("FAIL", "it crashed"))
            self.assertIn("without the dock", r["evidence_error"])


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

    def test_the_result_line_exists_before_the_evidence_step_runs_so_a_crash_cannot_lose_it(self):
        seen = {}

        def snapshot(row, note):
            seen.update(sc.load_results(self.tmp.name).get(row, {}))
            seen["marker_cleared"] = not (Path(self.tmp.name) / "CURRENT_ROW.txt").exists()
        self.s.snapshot = snapshot
        self.s.start("X1")
        self.assertTrue((Path(self.tmp.name) / "CURRENT_ROW.txt").exists())
        self.s.finish("FAIL", "boom")
        self.assertEqual((seen["status"], seen["evidence_error"], seen["marker_cleared"]), ("FAIL", "pending", True))
        self.assertEqual(sc.load_results(self.tmp.name)["X1"]["evidence_error"], "")          # rewritten with the outcome once the evidence step returned

    def test_a_crash_inside_the_evidence_step_leaves_a_pending_line(self):
        def snapshot(row, note):
            raise SystemExit("simulated crash")                                              # not an Exception: nothing below it runs
        self.s.snapshot = snapshot
        self.s.start("X1")
        with self.assertRaises(SystemExit):
            self.s.finish("PARTIAL", "n")
        self.assertEqual(sc.load_results(self.tmp.name)["X1"]["evidence_error"], "pending")

    def test_an_open_row_found_at_the_next_start_is_recorded_as_interrupted(self):
        self.s.start("X2")
        self.assertEqual(sc.recover_interrupted(self.tmp.name, clock=lambda: 5.0), "X2")
        r = sc.load_results(self.tmp.name)["X2"]
        self.assertEqual((r["status"], r["evidence_error"]), ("FAIL", "interrupted"))
        self.assertIsNone(sc.recover_interrupted(self.tmp.name))                             # the marker is gone: recovered once
        self.s.start("X1")
        self.s.finish("PASS")
        self.assertIsNone(sc.recover_interrupted(self.tmp.name))                             # a finished row leaves nothing to recover

    def test_an_interrupted_row_is_offered_again_twice_then_stays_failed(self):
        for attempt, final in ((1, False), (2, True)):
            self.s.start("X2")
            self.assertEqual(sc.recover_interrupted(self.tmp.name), "X2")
            rec = sc.load_results(self.tmp.name)["X2"]
            self.assertIn(f"attempt {attempt}", rec["note"])
            self.assertEqual(rec["evidence_error"], "interrupted-final" if final else "interrupted")
            self.assertEqual("X2" in sc.finished_rows(self.tmp.name), final)
            self.s.current = self.s.started = None                                           # QGIS restarted: a new session knows of no open row
        self.s.start("X1")
        self.s.finish("PASS")
        self.assertIn("X1", sc.finished_rows(self.tmp.name))

    def test_a_real_result_after_an_interruption_finishes_the_row(self):
        self.s.start("X2")
        sc.recover_interrupted(self.tmp.name)
        self.s.current = self.s.started = None
        self.assertNotIn("X2", sc.finished_rows(self.tmp.name))
        self.s.start("X2")
        self.s.finish("PARTIAL", "done properly")
        self.assertIn("X2", sc.finished_rows(self.tmp.name))
        self.assertEqual(sc.load_results(self.tmp.name)["X2"]["status"], "PARTIAL")

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

    def test_the_screen_capture_from_outside_qgis_counts_as_the_window_picture(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertFalse(an.evidence_for(tmp, "X1")["window"])
            (Path(tmp) / "screens").mkdir()
            (Path(tmp) / "screens" / "X1.png").write_bytes(b"png")
            self.assertTrue(an.evidence_for(tmp, "X1")["window"])

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

    def test_cards_json_matches_the_rows_and_the_prompt_gives_full_authority_with_limits(self):
        cards = json.loads(self.zip.read(f"{self.top}/cards.json"))
        self.assertEqual(len(cards), self.n)
        self.assertGreater(self.k, 50)
        prompt = self.zip.read(f"{self.top}/HAIKU_PROMPT.md").decode()
        self.assertIn("exactly one thing: the single line on card A1", prompt)
        self.assertIn("Never claim a result you did not see", prompt)
        for need in ("Windows 11", "RUN_EVERYTHING.bat", "up to 6 minutes", "qgiscrashhandler", "Task Manager", "PERMISSION PROMPTS", "first row with no result", "Never enter, read out",
                     "never need to type in Command Prompt", "Preview pane", "look-only"):
            self.assertIn(need, prompt)
        self.assertNotIn("Do not paste anything", prompt)                                      # the type tool may use the clipboard inside; only Ctrl+V by hand is banned
        self.assertIn("Do not paste with Ctrl+V yourself", prompt)
        self.assertNotIn("RECORD.bat", prompt)               # Haiku cannot type in a terminal, so the prompt must not rely on it
        self.assertNotIn("at most 6 rows", prompt)
        self.assertNotIn("Never restart QGIS yourself", prompt)

    def test_the_launch_and_recovery_scripts_are_shipped_and_do_what_the_prompt_says(self):
        names = self.names()
        self.assertIn("BUILD.txt", names)
        self.assertRegex(self.zip.read(f"{self.top}/BUILD.txt").decode(), r"built \d{4}-\d\d-\d\d")
        for need in ("RUN_EVERYTHING.bat", "PY.bat", "RECORD.bat", "tools/supervisor.ps1", "tools/record_result.py", "6_tools/mcp_probe.py", "6_tools/check_workflow_file.py", "2_layout_check/layout_check_script.py"):
            self.assertIn(need, names)
        sup = self.zip.read(f"{self.top}/tools/supervisor.ps1").decode()
        for need in ("qgiscrashhandler", "$i -le 8", "run_smoke_headless.py", "analyze_smoke_run.py", "CARTOGEN_SMOKE_DIR", "RESULTS_GUI.csv"):
            self.assertIn(need, sup)
        self.assertIn("supervisor.ps1", self.zip.read(f"{self.top}/RUN_EVERYTHING.bat").decode())
        analyze = self.zip.read(f"{self.top}/ANALYZE.bat").decode()
        self.assertIn("PY.bat", analyze)                                                       # no dependency on a separate Python install
        self.assertNotRegex(analyze, r"(?m)^python ")
        self.assertNotIn("smoke_start_work", self.zip.read(f"{self.top}/START_QGIS.bat").decode())

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
