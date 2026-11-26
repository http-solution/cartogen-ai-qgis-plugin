"""Offline tests of the computer-use smoke package: the card cleaner, the one-row-at-a-time session, the analysis that refuses an unsupported PASS, and the built zip. Rules pinned:
a result cannot be recorded without a started row, a result line is written only after the evidence step ran (and says so if it failed), an agent's PASS counts only with program-made evidence, and no card
tells the agent to type a console command (the 2026-11-13/14 run failed on exactly that)."""
import csv
import json
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from typing import ClassVar

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
        for rid in ("V1-update", "F3-check-evidence", "A3-cli-bridge", "W6-mcp-probe", "W7-mcp-dialog", "W8-export", "W10-import-bad", "C18-persona-upgrade", "C12-run-processing-model", "W12-guide"):
            self.assertFalse(by_id[rid]["can_run"], rid)
        slow = [c["id"] for c in by_id.values() if c["slow"] and c["can_run"]]
        self.assertIn("B4-long-request", slow)
        self.assertIn("SLOW ROW", sc.card_text(by_id["B4-long-request"]))
        self.assertNotIn("SLOW ROW", sc.card_text(by_id["A2-settings-connections"]))


class TestCardReview20261124(unittest.TestCase):
    """The review of every card after the first rc4 agent run (2026-11-24), each test one defect found by reading the cards the agent actually got."""

    def test_no_card_has_a_doubled_or_unfilled_package_path(self):
        for c in _cards():
            body = " ".join(str(c[k]) for k in ("starts_from", "do", "expect", "pass_if", "also_capture"))
            self.assertNotIn("<PACKAGE>\\<PACKAGE>", body, c["id"])            # C20 to C27 pointed every console load at a folder that does not exist
            self.assertNotIn("<bundle>", body, c["id"])
            self.assertNotIn("\\\\3_test_files", body, c["id"])

    def test_the_console_loads_of_the_environment_and_health_rows_name_the_real_folder(self):
        by_id = {c["id"]: c for c in _cards()}
        self.assertIn('r"<PACKAGE>\\3_test_files\\smoke_worldcover.asc"', by_id["C20-environment-looks"]["do"])
        self.assertIn("CONSOLE:", sc.card_text(by_id["C20-environment-looks"]))

    def test_no_card_tells_the_agent_to_fill_in_the_package_path_the_watcher_already_fills(self):
        for c in _cards():
            self.assertNotIn("replace <PACKAGE>", c["do"], c["id"])
            self.assertNotIn("replace <bundle>", c["do"], c["id"])

    def test_a1_is_not_flagged_as_needing_a_model_a_key_or_a_network(self):
        a1 = {c["id"]: c for c in _cards()}["A1-layout-script"]
        self.assertFalse(a1["model_needed"])
        self.assertFalse(a1["internet_needed"])

    def test_the_fresh_chat_rule_matches_the_plugin_which_has_a_new_chat_button(self):
        text = sc.card_text({c["id"]: c for c in _cards()}["B1-routing-plain"])
        self.assertIn("New chat button", text)
        self.assertNotIn("has no 'New chat' button", text)

    def test_every_appended_sentence_belongs_to_a_real_row_and_reaches_its_card(self):
        by_id = {c["id"]: c for c in _cards()}
        for rid, parts in sc.APPEND.items():
            self.assertIn(rid, by_id)
            for key, sentence in parts.items():
                self.assertIn(sc.fill_paths(sentence).strip(), by_id[rid][key], rid)
        self.assertIn("drop-down arrow", by_id["A2-settings-connections"]["do"])         # the 1.20.0-rc4 Connections fixes are on a card
        self.assertIn("bad-key", by_id["A2-settings-connections"]["do"])

    def test_a1_promises_png_pages_only_because_the_script_writes_them(self):
        script = (Path(__file__).resolve().parent.parent / "tools" / "layout_check_script.py").read_text(encoding="utf-8")
        self.assertIn('output_format="png"', script)


class TestNewResultRows(unittest.TestCase):
    """The watcher in QGIS takes evidence for every row that gets a new line in RESULTS_GUI.csv; this is the pure part that finds them."""

    def test_only_rows_not_yet_seen_are_new_and_a_corrected_line_is_not_new_again(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(sc.new_result_rows(tmp, set()), [])                      # no file yet is not an error
            sc.append_result(tmp, {"row": "A1", "status": "PASS", "note": "ok"})
            sc.append_result(tmp, {"row": "A2", "status": "FAIL", "note": "no"})
            fresh = sc.new_result_rows(tmp, {"A1"})
            self.assertEqual([r for r, _ in fresh], ["A2"])
            self.assertEqual(fresh[0][1]["status"], "FAIL")
            sc.append_result(tmp, {"row": "A2", "status": "PASS", "note": "corrected"})
            self.assertEqual(sc.new_result_rows(tmp, {"A1", "A2"}), [])               # the same row again is not snapped twice

    def test_the_filled_path_replaces_the_placeholder_in_card_text(self):
        card = {"id": "X1", "title": "t", "can_run": True, "why_not": "", "do": r'iface.addVectorLayer(r"<PACKAGE>\3_test_files\a.geojson")', "starts_from": "", "expect": "", "pass_if": "",
                "also_capture": "", "slow": False, "machine_checked_by": [], "model_needed": False, "internet_needed": False, "files": []}
        text = sc.card_text(card).replace("<PACKAGE>", r"C:\pkg")
        self.assertIn(r'r"C:\pkg\3_test_files\a.geojson"', text)
        self.assertNotIn("<PACKAGE>", text)


class TestPrepareRun(unittest.TestCase):
    """tools/prepare_run.py runs before QGIS opens (plain Python), so the agent has its cards and its results file even when QGIS or the watcher fails to start."""

    CARDS: ClassVar[list] = [{"id": "A1", "title": "one", "can_run": True, "why_not": "", "do": r'open <PACKAGE>\3_test_files\a.gpkg', "starts_from": "", "expect": "", "pass_if": "", "also_capture": "", "slow": False,
              "machine_checked_by": [], "model_needed": False, "internet_needed": False, "files": []},
             {"id": "H1", "title": "human", "can_run": False, "why_not": "needs a person", "do": "", "starts_from": "", "expect": "", "pass_if": "", "also_capture": "", "slow": False,
              "machine_checked_by": [], "model_needed": False, "internet_needed": False, "files": []}]

    def _package(self, tmp):
        (Path(tmp) / "cards.json").write_text(json.dumps(self.CARDS), encoding="utf-8")
        import prepare_run
        return prepare_run

    def test_it_writes_the_filled_cards_and_a_results_file_with_header_and_the_human_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            prepare_run = self._package(tmp)
            filled, recorded = prepare_run.prepare(tmp)
            text = Path(filled).read_text(encoding="utf-8")
            self.assertIn(os.path.abspath(tmp), text)               # abspath, not resolve(): on Windows the temp folder has a short 8.3 name (RUNNER~1) that resolve() expands and the code rightly does not
            self.assertNotIn("<PACKAGE>", text)
            self.assertEqual(recorded, ["H1"])
            lines = (Path(tmp) / "results" / "RESULTS_GUI.csv").read_text(encoding="utf-8").splitlines()
            self.assertEqual(lines[0], ",".join(sc.RESULT_FIELDS))
            self.assertTrue(lines[1].startswith("H1,SKIP,"))

    def test_running_it_again_never_rewrites_or_duplicates_a_result_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            prepare_run = self._package(tmp)
            prepare_run.prepare(tmp)
            sc.append_result(str(Path(tmp) / "results"), {"row": "A1", "status": "PASS", "note": "done by the agent"})
            before = (Path(tmp) / "results" / "RESULTS_GUI.csv").read_text(encoding="utf-8")
            _filled, recorded = prepare_run.prepare(tmp)
            self.assertEqual(recorded, [])
            self.assertEqual((Path(tmp) / "results" / "RESULTS_GUI.csv").read_text(encoding="utf-8"), before)

    def test_a_package_with_no_human_rows_still_gets_its_header(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "cards.json").write_text(json.dumps(self.CARDS[:1]), encoding="utf-8")
            import prepare_run
            prepare_run.prepare(tmp)
            self.assertEqual((Path(tmp) / "results" / "RESULTS_GUI.csv").read_text(encoding="utf-8").splitlines(), [",".join(sc.RESULT_FIELDS)])


class TestShortRowIds(unittest.TestCase):
    """The owner's rc5 run: the agent wrote 'C6', 'C7', 'C10' instead of the full card ids, so the report called nine rows 'no result' and filed their evidence under names it did not read."""

    IDS: ClassVar[list] = ["C1-load-and-scripts", "C10-raster-inspection", "C6-identify-at-point", "R1-H1-persona-panel", "A1-layout-script"]

    def test_a_short_id_means_the_one_card_that_starts_with_it(self):
        self.assertEqual(sc.canonical_row_id("C6", self.IDS), "C6-identify-at-point")
        self.assertEqual(sc.canonical_row_id("C1", self.IDS), "C1-load-and-scripts")          # C1 is not C10
        self.assertEqual(sc.canonical_row_id("C10", self.IDS), "C10-raster-inspection")
        self.assertEqual(sc.canonical_row_id("R1-H1", self.IDS), "R1-H1-persona-panel")
        self.assertEqual(sc.canonical_row_id("C6-identify-at-point", self.IDS), "C6-identify-at-point")
        self.assertEqual(sc.canonical_row_id("C99", self.IDS), "C99")                         # unknown stays as written

    def test_an_ambiguous_short_id_is_left_alone(self):
        self.assertEqual(sc.canonical_row_id("C1", ["C1-a", "C1-b"]), "C1")

    def test_the_report_counts_a_line_written_under_a_short_id_and_finds_its_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            sc.append_result(tmp, {"row": "C6", "status": "PASS", "note": "done"})
            folder = Path(tmp) / "evidence" / "C6"
            folder.mkdir(parents=True)
            (folder / "window.png").write_bytes(b"png")
            (folder / "layers.json").write_text("[]")
            sc.start_log(tmp, "watcher running (rows=1)")
            card = _cardfor(id="C6-identify-at-point")
            text, counts, _mc = an.build_report(tmp, [card])
            self.assertEqual(counts, {"VERIFIED": 1})
            sc.append_result(tmp, {"row": "C7", "status": "FAIL", "note": "no layer"})
            text, counts, _mc = an.build_report(tmp, [card, _cardfor(id="C7-field-rules")])
            self.assertEqual(counts, {"VERIFIED": 1, "CLAIMED": 1})
            self.assertIn("(written as 'C7') no layer", text)                 # the report says the line was written under a short name


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
            sc.start_log(tmp, "watcher running (rows=3)")                  # a run in which the watcher reported: the strict rules apply
            sc.append_result(tmp, {"row": "X1", "status": "PASS", "note": "ok", "seconds": 5})
            sc.append_result(tmp, {"row": "X2", "status": "PASS", "note": "ok", "seconds": 9})        # no evidence for X2
            (Path(tmp) / "RESULTS.csv").write_text("row,covers_row,status,evidence_folder\nH1,C24,PASS,e\n")
            text, counts, mc = an.build_report(tmp, [_cardfor(id="X1"), _cardfor(id="X2"), _cardfor(id="X3")])
            self.assertEqual(counts, {"VERIFIED": 1, "UNSUPPORTED": 1, "NO RESULT": 1})
            self.assertEqual(mc, {"PASS": 1})
            self.assertIn("| X2 | PASS | typed | UNSUPPORTED |", text)
            self.assertIn("Result lines written by the agent: 2", text)

    def test_written_by_tells_the_docks_lines_from_typed_ones(self):
        dock = {"row": "X1", "status": "PASS", "started": "2026-11-20T10:00:00", "finished": "2026-11-20T10:01:00", "seconds": "60"}
        self.assertEqual(an.written_by(dock), "dock")
        self.assertEqual(an.written_by({"row": "X1", "status": "PASS", "started": "", "finished": "", "seconds": ""}), "typed")
        self.assertEqual(an.written_by({"row": "X1", "status": "PASS", "seconds": "5"}), "typed")      # a number alone is not the dock's signature
        self.assertEqual(an.written_by(None), "")


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
                     "FIRST_MESSAGE.txt", "tools/smoke_watch.py", "tools/smoke_watch_start.py", "tools/smoke_cards.py", "tools/smoke_core.py", "tools/analyze_smoke_run.py", "tools/request_costs.py", "tools/routing_requests.json", "tools/collect_evidence.py"):
            self.assertIn(need, names)
        self.assertTrue(any(n.startswith("1_plugin/") for n in names))
        self.assertTrue(any(n.startswith("plugin/cartogen_ai/core/") for n in names))
        self.assertTrue(any(n.startswith("3_test_files/smoke_districts_cases") for n in names))

    def test_cards_json_matches_the_rows_and_the_prompt_gives_full_authority_with_limits(self):
        cards = json.loads(self.zip.read(f"{self.top}/cards.json"))
        self.assertEqual(len(cards), self.n)
        self.assertGreater(self.k, 50)
        prompt = self.zip.read(f"{self.top}/HAIKU_PROMPT.md").decode()
        self.assertIn("ONLY for lines that a card gives you word for word", prompt)           # 2026-11-24: about 12 cards need console lines, so "exactly one line" made the agent refuse them
        self.assertNotIn("exactly one thing", prompt)
        self.assertIn("Never claim a result you did not see", prompt)
        for need in ("Windows 11", "RUN_EVERYTHING.bat", "up to 6 minutes", "qgiscrashhandler", "Task Manager", "PERMISSION PROMPTS", "first row with no line", "Never enter, read out",
                     "never need to type in Command Prompt", "Preview pane", "look-only"):
            self.assertIn(need, prompt)
        self.assertNotIn("Do not paste anything", prompt)                                      # the type tool may use the clipboard inside; only Ctrl+V by hand is banned
        self.assertIn("Do not paste with Ctrl+V yourself", prompt)
        self.assertNotIn("RECORD.bat", prompt)               # Haiku cannot type in a terminal, so the prompt must not rely on it
        self.assertNotIn("at most 6 rows", prompt)
        self.assertNotIn("Never restart QGIS yourself", prompt)

    def test_the_prompt_has_no_panel_and_the_agent_writes_the_csv_itself(self):
        """2026-11-25: the owner asked for the panel to go and for the agent to report straight into the CSV. The dock's buttons were also blocked by the Claude app's own safety check."""
        prompt = self.zip.read(f"{self.top}/HAIKU_PROMPT.md").decode()
        self.assertNotIn("dock", prompt.lower())
        self.assertNotIn("Start this row", prompt)
        self.assertIn("there is no panel to use", prompt)
        self.assertIn("CARDS_FILLED.md", prompt)
        self.assertIn("blocked by the Claude app", prompt)          # a refused action ends the row with a SKIP, it does not stall the run
        self.assertIn("you MAY change Cartogen AI's settings", prompt)
        for need in ("results\\outputs\\<ROW>\\", "results\\RESULTS_GUI.csv", "observations.txt", "WORK ON A COPY", "row,status,note,started,finished,seconds,evidence_error",
                     "never edit another line", "watcher.log"):
            self.assertIn(need.lower(), prompt.lower(), need)
        first = self.zip.read(f"{self.top}/FIRST_MESSAGE.txt").decode()
        stamp = self.zip.read(f"{self.top}/BUILD.txt").decode().strip()
        self.assertIn(stamp, first)                                                       # the message names the very build it ships in
        self.assertIn("I AM THE OWNER OF THIS PC", first)
        self.assertIn("PACKAGE FOLDER:", first)
        self.assertIn("there is no panel", first)
        self.assertIn(prompt.strip().splitlines()[0], first)                              # the same instructions, not a second copy that can drift
        self.assertNotIn("{stamp}", first)
        self.assertNotIn("{prompt}", first)

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

    def test_the_supervisor_takes_its_own_timed_screenshots_without_ever_stopping_the_run(self):
        # LR-16: the computer-use agent's screenshot tool cannot save files (25 pictures lost on 2026-11-20), so the
        # supervisor saves one a minute and one at each new result line, from outside QGIS. Source-text guard only:
        # PowerShell is not available in this sandbox, so the capture itself is unverified until a Windows run.
        sup = self.zip.read(f"{self.top}/tools/supervisor.ps1").decode()
        for need in ("screens\\timed", "CopyFromScreen", "row_change", "-ge 60", "timed screenshot failed", "WaitForExit(2000)"):
            self.assertIn(need, sup)
        self.assertEqual(sup.count("Capture \""), 2)              # the row-change and the timer call sites
        capture = sup[sup.index("function Capture"):sup.index("function ResultLines")]
        self.assertIn("try {", capture)                            # a failed picture is logged, never fatal
        self.assertIn("catch", capture)

    def test_every_file_a_card_needs_is_shipped(self):
        names = {Path(n).name for n in self.names() if n.startswith("3_test_files/")}
        for c in json.loads(self.zip.read(f"{self.top}/cards.json")):
            for f in c["files"]:
                self.assertIn(Path(f).name, names, c["id"])

    def test_the_watcher_start_is_logged_and_a_failure_is_never_silent(self):
        sup = self.zip.read(f"{self.top}/tools/supervisor.ps1").decode()
        for need in ("watcher.log", "watcher running", "WARNING: QGIS has run 90 s", "smoke_watch_start.py"):
            self.assertIn(need, sup)
        start = self.zip.read(f"{self.top}/tools/smoke_watch_start.py").decode()
        for need in ("start_error(", "starting the watcher", "start_log("):
            self.assertIn(need, start)
        self.assertIn("watcher running", self.zip.read(f"{self.top}/tools/smoke_watch.py").decode())
        self.assertNotIn("tools/smoke_dock.py", self.names())            # the panel is gone from the package
        self.assertIn("tools/prepare_run.py", self.names())
        for bat in ("START_QGIS.bat", "RUN_EVERYTHING.bat"):
            text = self.zip.read(f"{self.top}/{bat}").decode()
            self.assertIn("prepare_run.py", text, bat)                    # the cards and the results file exist before QGIS opens
            self.assertIn("QGIS is still open", text, bat)                # the packaged plugin replaces an older copy only when its files are not locked
            self.assertIn("rmdir /s /q", text, bat)
            self.assertLess(text.index("setlocal\r\ncall \"%PKG%\\PY.bat\""), text.index("\r\nendlocal"), bat)      # QGIS's python setup must not leak its settings into the QGIS that is started next

    def test_csv_of_results_header_is_stable(self):
        self.assertEqual(sc.RESULT_FIELDS[:3], ["row", "status", "note"])
        with tempfile.TemporaryDirectory() as tmp:
            sc.append_result(tmp, {"row": "A", "status": "SKIP"})
            self.assertEqual(next(csv.reader((Path(tmp) / "RESULTS_GUI.csv").read_text(encoding="utf-8").splitlines()))[:2], ["row", "status"])


if __name__ == "__main__":
    unittest.main()


class TestWorkOnACopy(unittest.TestCase):
    def test_rows_that_write_into_their_data_file_say_to_use_a_copy(self):
        for rid in ("C7-field-rules", "D2-damage-and-risk"):
            self.assertTrue(any("WORK ON A COPY" in h and rid in h for h in sc.helps({"id": rid, "starts_from": "", "do": "", "expect": "", "pass_if": ""})), rid)
        self.assertFalse(any("WORK ON A COPY" in h for h in sc.helps({"id": "A2-settings-connections", "starts_from": "", "do": "", "expect": "", "pass_if": ""})))


class TestWatcherStartLog(unittest.TestCase):
    """The 2026-11-20 run left no trace of whether the start-up program ran; these pin the files that now say so."""

    def test_log_lines_and_a_failure_with_its_traceback(self):
        with tempfile.TemporaryDirectory() as tmp:
            sc.start_log(tmp, "watcher running (rows=2)")
            try:
                raise TypeError("boom")
            except TypeError as e:
                sc.start_error(tmp, "starting the watcher", e)
            log = (Path(tmp) / "watcher.log").read_text(encoding="utf-8")
            self.assertIn("watcher running", log)
            self.assertIn("START-UP FAILED in starting the watcher: TypeError: boom", log)
            self.assertIn("Traceback", (Path(tmp) / "watcher_errors.txt").read_text(encoding="utf-8"))

    def test_logging_never_raises_when_the_folder_cannot_be_written(self):
        with tempfile.NamedTemporaryFile() as f:
            sc.start_log(f.name, "x")                     # a file where a folder is expected

    def test_the_report_warns_when_the_watcher_never_reported_and_is_quiet_when_it_did(self):
        with tempfile.TemporaryDirectory() as tmp:
            text, _, _ = an.build_report(tmp, [])
            self.assertIn("never reported that it was running", text)
            sc.start_log(tmp, "watcher running (rows=2)")
            text, _, _ = an.build_report(tmp, [])
            self.assertIn("reported that it was running", text)
            self.assertNotIn("never reported", text)


class TestReportWithoutTheDock(unittest.TestCase):
    """The owner dropped the dock on 2026-11-20: a PASS is then supported by the agent's notes plus the plugin's own tool record, and only from a folder that belongs to that row."""
    CARD: ClassVar[dict] = {"id": "D5-task-grid", "can_run": True, "why_not": "", "model_needed": True}

    def _row(self, tmp, where, notes=True):
        base = Path(tmp) / where / "cartogen_evidence" / "20261120-000000_t1"
        base.mkdir(parents=True)
        (base / "steps.jsonl").write_text(json.dumps({"n": 1, "tool": "generate_mapping_task_grid"}) + "\n", encoding="utf-8")
        if notes:
            (Path(tmp) / "evidence" / "D5-task-grid").mkdir(parents=True)
            (Path(tmp) / "evidence" / "D5-task-grid" / "observations.txt").write_text("saw it", encoding="utf-8")

    def _judge(self, tmp, dock_shown=False):
        ev = an.evidence_for(tmp, "D5-task-grid")
        return an.judge(self.CARD, {"status": "PASS"}, ev, dock_shown=dock_shown), ev

    def test_a_row_folder_with_notes_and_a_plugin_record_is_supported(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._row(tmp, "outputs/D5-task-grid")
            (trust, why), ev = self._judge(tmp)
            self.assertEqual(trust, "SUPPORTED", why)
            self.assertEqual(ev["tools"], ["generate_mapping_task_grid"])

    def test_a_record_found_only_in_a_work_copy_is_not_attributed(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._row(tmp, "work/D5_copy")
            (trust, why), _ = self._judge(tmp)
            self.assertEqual(trust, "UNSUPPORTED")
            self.assertIn("cannot be attributed", why)

    def test_no_notes_means_unsupported(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._row(tmp, "outputs/D5-task-grid", notes=False)
            self.assertEqual(self._judge(tmp)[0][0], "UNSUPPORTED")

    def test_when_the_dock_did_report_the_old_strict_rules_still_apply(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._row(tmp, "outputs/D5-task-grid")
            self.assertEqual(self._judge(tmp, dock_shown=True)[0][0], "UNSUPPORTED")       # no window.png / layers.json
