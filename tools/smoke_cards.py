"""Pure half of the computer-use smoke package (no QGIS, no Qt): turns smoke rows into one short card each, keeps the result log, and runs the one-row-at-a-time session the in-QGIS dock drives.

Why: the 2026-11-13/14 run asked a small agent to follow a long hand sheet AND to remember the evidence (console commands, screenshots, file names). It forgot. Here the agent only
does the steps on one card and writes ONE line into results/RESULTS_GUI.csv; a background watcher inside QGIS (tools/smoke_watch.py, no window, nothing to click) sees the new line and
takes the evidence by itself (window picture, layers, project state, the plugin's own tool record), so the agent has nothing to remember."""
import contextlib
import csv
import json
import os
import re
import sys
import time

STATUSES = ("PASS", "PARTIAL", "FAIL", "SKIP")
CONSOLE = re.compile(r"snap\(|shot\(|begin\(|collect_evidence|Python console|exec\(open|EVIDENCE_HOWTO|\bsnap\b", re.I)
_NO = re.compile(r"\bno (?:real )?(?:model|key|network|internet)\b|\bwithout (?:a )?(?:model|key|network|internet)\b", re.I)       # "QGIS only (no model, no key, no network)" is not a need for a model, a key or a network: A1 was flagged as needing all three
HUMAN_ONLY = re.compile(r"fluent|GeoDa|MCP client|Antigravity|Claude Code, Codex|second tool", re.I)
HUMAN_IDS = {
    "V1-update": "it needs an older plugin version to update from, which this package does not contain",
    "C18-persona-upgrade": "it needs an older plugin build to install the new one over, which this package does not contain",
    "F3-check-evidence": "it checks the results file of the hand package, not this package (ANALYZE.bat makes this package's report)",
    "W6-mcp-probe": "it needs commands typed in a terminal, which the Claude app's computer use does not allow (click only)",
    "W7-mcp-dialog": "it needs commands typed in a terminal, which the Claude app's computer use does not allow (click only)",
    "W8-export": "it needs a command typed in a terminal, which the Claude app's computer use does not allow (click only)",
    "C12-run-processing-model": "it asks you to BUILD two models in the Graphical Modeler (dragging steps and wiring them), which is not something a click-by-click agent can do reliably; a person builds them in about ten minutes",
    "W12-guide": "it needs a second person who has not seen the guide, and a stopwatch: there is no such reader in an agent run",
    "W10-import-bad": "its terminal command is now run by the program as row H21 (the validator's six refusal sentences); only clicking each file in the Open workflow dialog is left to a person",
}
SLOW = re.compile(r"overpass|osm|download|geofabrik|worldpop|stac|sentinel|isochrone|service area|large|mirror", re.I)
RESULT_FIELDS = ["row", "status", "note", "started", "finished", "seconds", "evidence_error"]


_DOC_REF = re.compile(r"\s*\((?:see )?(?:EVIDENCE_HOWTO|3_SHEET|CHECKLIST)[^)]*\)", re.I)
_EVIDENCE_SETTING = re.compile(r"'Save an evidence folder for each request' ticked( in Settings)?", re.I)
_FILLED = re.compile(r"\(replace <(?:PACKAGE|bundle)> with the full path of the (?:unzipped )?(?:package|bundle) folder\)", re.I)       # the watcher writes CARDS_FILLED.md with <PACKAGE> already replaced; telling the agent to do it too made it hunt for a path
_PY = re.compile(r"\bpython3? (?=(?:6_tools|2_layout_check|tools)[\\/])")


def fill_paths(text):
    """The terminal commands in the rows say `python 6_tools/x.py`: in this package they run through PY.bat (QGIS's own Python, always present), and <bundle> is the package folder. Pure."""
    text = _DOC_REF.sub("", str(text or ""))
    text = _FILLED.sub("(the package path is already filled in)", text)
    text = _EVIDENCE_SETTING.sub("evidence saving already switched on for you", text)
    # <bundle> first: the rows write r"<bundle>\\3_test_files\\x" and the next line prefixes every "3_test_files\\" with <PACKAGE>, so replacing <bundle> last (as before
    # 2026-11-24) left "<PACKAGE>\\<PACKAGE>\\3_test_files" in the console lines of C20 to C27: every load in those rows pointed at a folder that does not exist.
    text = text.replace("<bundle>", "<PACKAGE>").replace("\\\\", "\\")
    text = text.replace("results\\outputs\\", "<PACKAGE>\\results\\outputs\\").replace("3_test_files\\", "<PACKAGE>\\3_test_files\\")
    text = text.replace("<PACKAGE>\\<PACKAGE>\\", "<PACKAGE>\\").replace("<PACKAGE>\\<PACKAGE>\\", "<PACKAGE>\\")
    return _PY.sub("PY.bat ", text)


def clean(text):
    """Drops every sentence that tells the reader to run snap() or collect evidence by hand: the watcher does that. Pure."""
    parts = re.split(r"(?<=[.;])\s+(?=[A-Z(0-9'\"])", _DOC_REF.sub("", str(text or "")))       # a pointer to a document that is not in this package is removed BEFORE sentences are judged, so the sentence it sat in survives
    return fill_paths(" ".join(p for p in parts if not CONSOLE.search(p)).strip())


DO_OVERRIDES = {
    "A1-layout-script": ("In QGIS: Plugins > Python Console. Type this ONE line (it is the only console command you type in this whole test) and press Enter: "
                         "exec(open(r\"<PACKAGE>\\2_layout_check\\layout_check_script.py\", encoding=\"utf-8\").read())   "
                         "It runs by itself; wait for the table (if nothing prints after 2 minutes, type run() once and say so in the note). The pages are exported into the package folder, in "
                         "<PACKAGE>\\results\\outputs\\A1-layout-script. Open that folder in File Explorer, press Alt+P to switch on the Preview pane, and click each .png in turn (the script writes a .png beside every .pdf; there are about ten): its picture shows in the preview "
                         "pane, so no other program is needed. Do not open the .pdf files (they open in a browser, which you cannot use). Look at each page: footer complete and inside the page, "
                         "legend entries not cut, logo left of the title, sign-off readable, disclaimer not overlapping. If the Preview pane stays empty or there is no .png at all, say so and give Partial."),
}


# Text added to a card for a step this agent cannot do as the hand sheet wrote it (2026-11-24 review of every card after the first rc4 run: the agent stopped on A1 because the
# promised PNG pages did not exist, and the same kind of gap sat in other rows). key -> sentence. tests/test_smoke_cards.py proves every row id here exists.
APPEND = {
    "C28-large-download-card": {
        "do": (" EVIDENCE FOR BOTH CLICKS (added 2026-11-26): the 2026-11-25 run wrote that Cancel and Apply worked, but the plugin log has no line for either click, so that note could not be "
               "trusted. After you press Cancel, and again after you press Apply, take a screenshot straight away and write in the observations what you SAW on screen (did the card disappear, "
               "did a line starting with Cancelled or Confirmed appear in the chat). Then read the last lines of the plugin log (the card's evidence folder, log_cartogenai.txt): after an Apply "
               "there must be a line with tool_call, via=apply, status=done or failed. Write that line, or 'no apply line in the log'. If a click is blocked or does nothing, write SKIP for the "
               "row with the words 'click did not reach the plugin' and do not mark it Fail or Pass."),
        "pass_if": " A Pass needs the screenshot after Apply and the via=apply log line; a row written without them is a Skip, not a Pass or a Fail.",
    },
    "A2-settings-connections": {
        "do": (" 6. (added for 1.20.0-rc4) On the Claude Code CLI, Codex CLI and Antigravity CLI pages look at the Model box: it must show a small drop-down arrow at its right end. Click the "
               "arrow: a list opens with 'auto (recommended)' and at least one more name; pick one and the box shows it. 7. If Antigravity (or another CLI) is installed on this PC: press its "
               "Check connection button; when the status line says it answered, its entry in the list on the left must show a tick, not a filled dot. If no CLI is installed, write 'no CLI installed' "
               "for step 7. Typing the plain text bad-key in step 3 is allowed: it is not a key. Never type a real key."),
        "pass_if": " Steps 6 and 7 count too: a model box with no arrow or an empty list is a Fail; step 7 without a CLI installed is not a Fail.",
    },
    "R1-H1-persona-panel": {
        "do": (" For step (6) 'reset the profile': in Plugins > Python Console type this line exactly and press Enter: "
               "from qgis.core import QgsSettings; s = QgsSettings(); [s.remove(k) for k in ('cartogen_ai/onboarding_completed', 'cartogen_ai/user_profile', 'cartogen_ai/persona_primary', 'cartogen_ai/persona_secondary')]  "
               "Then close and reopen Cartogen AI Settings and press Edit My Profile to start the onboarding. You may change these settings: that is the test. "
               "Scroll the mouse wheel only over empty space (over a number box it changes the number: a scroll once changed Max tool-call rounds from 49 to 44). "
               "At the end type the same console line once more so the persona is back to the default."),
        "pass_if": " All six steps as Expect. Settings you changed during the row are put back at the end.",
    },
    "C1-load-and-scripts": {"do": " For step 6 you cannot use a browser or switch the internet off: confirm the dashboard HTML file exists (File Explorer) and write its name; then read the first lines of the file with your file tools and look for the sentence that says it needs an internet connection."},
    "C16-charts-and-file-info": {"do": " You cannot open a browser: for (1) and (2) check that the reply gives the path of a .html file and that the file exists in File Explorer; the chart picture itself is not checked (Partial at best for that part)."},
    "C8-table-and-map-display": {"do": " For (5) the browser opens by itself: you may only look at it. If it comes to the front, click the QGIS button on the taskbar. For (6) the plugin must refuse; you do not open Notepad."},
    "W5-hdx-ranked": {"do": " You cannot use a browser: do not open the HDX page. Write the first result's title and its HDX link from the reply in the note."},
    "W13-environment": {"do": " You cannot use a text editor: skip the paste. Instead press Copy in the Settings Diagnostics section and say in the note that the paste was not checked."},
    "C23-cluster-scan": {"do": " Skip step 5 (SaTScan is another program): write 'SaTScan comparison not done' in the note; steps 1 to 4 decide the row."},
    "C13-processing-batch": {"do": " For step (4) use the raster 3_test_files\\smoke_dem.tif."},
    "C10-raster-inspection": {"do": " The DEM is 3_test_files\\smoke_dem.tif and the classified (land-cover) raster is 3_test_files\\smoke_worldcover.asc."},
    "C15-points-to-path-and-relief": {"do": " The elevation GeoTIFF is 3_test_files\\smoke_dem.tif (name the layer dem)."},
}


def _apply_append(row_id, key, text):
    return fill_paths(str(text or "") + APPEND.get(row_id, {}).get(key, "")).strip()


def make_cards(rows, machine_rows=None):
    """One card per row, in running order. machine_rows maps a hand row id to the ids of the agent-run rows that already check its numbers. Pure."""
    machine_rows = machine_rows or {}
    cards = []
    for row in rows:
        needs = str(row.get("needs", ""))
        human = bool(HUMAN_ONLY.search(needs)) or row["id"] in HUMAN_IDS
        cards.append({
            "id": row["id"], "session": row.get("session", ""), "title": row.get("title", ""), "needs": needs,
            "model_needed": bool(re.search(r"model|key", _NO.sub("", needs), re.I)), "internet_needed": bool(re.search(r"internet|network", _NO.sub("", needs), re.I)),
            "can_run": not human, "why_not": HUMAN_IDS.get(row["id"], "needs a second program or a fluent reader a computer-use agent does not have") if human else "",
            "slow": bool(SLOW.search(" ".join([needs, str(row.get("do", ""))]))),
            "starts_from": clean(row.get("starts_from", "")), "do": _apply_append(row["id"], "do", fill_paths(DO_OVERRIDES.get(row["id"]) or clean(row.get("do", "")))), "expect": clean(row.get("expect", "")),
            "pass_if": _apply_append(row["id"], "pass_if", clean(row.get("pass_if", ""))), "also_capture": clean(row.get("evidence", "")), "files": list(row.get("files", [])),
            "machine_checked_by": machine_rows.get(row["id"], []),
        })
    return cards


_BROWSER = re.compile(r"\bbrowser\b|chrome|firefox|\bedge\b|web page|HDX page", re.I)


WRITES_SOURCE_FILE = {"C7-field-rules", "D2-damage-and-risk"}        # rows whose tools wrote into 3_test_files\\smoke_data.gpkg in the 2026-11-20 run


def helps(card):
    """The general rules a card relies on (the hand sheet held them; the cards had lost them). Pure."""
    body = " ".join(str(card.get(k, "")) for k in ("starts_from", "do", "expect", "pass_if"))
    out = []
    if re.search(r"fresh chat|new chat", body, re.I):
        out.append("FRESH CHAT: click the New chat button in the chat's message row (next to the layer-context button); it empties the conversation and the model's memory. "
                   "Opening a different project (File > New or the row's project file) also starts a fresh chat. If the old conversation is still on screen after that, say so in the note and carry on.")
    if re.search(r"save the project", body, re.I):
        out.append(f"SAVE FIRST: File > Save As into <PACKAGE>\\results\\outputs\\{card['id']}\\ BEFORE the first request; the plugin writes its evidence next to a saved project (an unsaved project leaves none).")
    if re.search(r"a copy of", str(card.get("starts_from", "")), re.I):
        out.append(f"COPY: you do not need to copy files. Open the project, then File > Save As into <PACKAGE>\\results\\outputs\\{card['id']}\\ before you change anything, so the original in 3_test_files is never altered.")
    if card.get("id") in WRITES_SOURCE_FILE:
        out.append("WORK ON A COPY: this row's tools change the data file they load (a new field, a changed value). In File Explorer copy the whole 3_test_files folder to "
                   f"<PACKAGE>\\results\\work\\{card['id']}_copy (click the folder, Ctrl+C, Ctrl+V, rename the copy) and load every file from THAT copy, never from 3_test_files. "
                   "The 2026-11-20 run changed smoke_data.gpkg in 3_test_files during C7 and D2 and had to restore it.")
    if re.search(r"iface\.add|\bfrom cartogen_ai\b|QgsSettings\(\)", body):
        out.append("CONSOLE: this row gives you exact lines to type in Plugins > Python Console. Type ONLY those lines, character for character (the package folder path is already filled in), press Enter once per line and read the output. Never type any other command there.")
    if _BROWSER.search(body):
        out.append("BROWSERS: the Claude app lets you only LOOK at a web browser, not click or type in it. Skip any step that needs one, say so in the note, and give the row Partial at best.")
    if re.search(r"\bNotepad\b|\bExcel\b|\bLibreOffice\b", body):
        out.append("OTHER PROGRAMS: a step that needs a program other than QGIS and File Explorer: skip that step, say so in the note, and give the row Partial at best.")
    return out


def card_text(card):
    """The text of one card (CARDS.md holds every card in this form). Pure."""
    lines = [f"ROW {card['id']}  -  {card['title']}", ""]
    if not card["can_run"]:
        return "\n".join([*lines, f"NOT FOR THIS AGENT: {card['why_not']}. Write SKIP with the note 'human row' (the program has already written that line)."])
    for label, key in (("START FROM", "starts_from"), ("DO", "do"), ("EXPECT", "expect"), ("PASS ONLY IF", "pass_if"), ("EXTRA EVIDENCE (the program saves a window picture, the layer list and the plugin's tool record by itself when your result line appears; do this only if easy)", "also_capture")):
        if card.get(key):
            lines += [f"{label}: {card[key]}", ""]
    for line in helps(card):
        lines += [line, ""]
    if card.get("slow"):
        lines.append("SLOW ROW: a tool here can run for up to 6 minutes and QGIS then looks frozen ('Not Responding'). That is normal: wait, do NOT click, do NOT restart QGIS. "
                     "If nothing has changed after 8 minutes, write FAIL with the note 'no reply'.")
        lines.append("")
    if card["machine_checked_by"]:
        lines.append(f"(A program already checks the numbers of this row: {', '.join(card['machine_checked_by'])}. You judge what you can see.)")
    return "\n".join(lines)


def append_result(out_dir, record):
    path = os.path.join(out_dir, "RESULTS_GUI.csv")
    new = not os.path.isfile(path)
    with open(path, "a", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, RESULT_FIELDS, extrasaction="ignore")
        if new:
            w.writeheader()
        w.writerow(record)


def load_results(out_dir):
    path = os.path.join(out_dir, "RESULTS_GUI.csv")
    if not os.path.isfile(path):
        return {}
    with open(path, encoding="utf-8", newline="") as fh:
        return {r["row"]: r for r in csv.DictReader(fh)}                   # a later line for the same row replaces the earlier one


class Session:
    """One row at a time. start() opens a row, finish() takes the evidence through `snapshot(row_id, note)` and only then writes the result line.
    A result with no start, a second start while a row is open, an unknown status or an unknown row is refused with a message. Pure apart from files."""

    def __init__(self, out_dir, cards, snapshot, clock=time.time):
        self.out_dir, self.cards, self.snapshot, self.clock = out_dir, {c["id"]: c for c in cards}, snapshot, clock
        self.current, self.started = None, None
        os.makedirs(out_dir, exist_ok=True)

    def start(self, row_id):
        if row_id not in self.cards:
            return False, f"no such row {row_id}"
        if self.current and self.current != row_id:
            return False, f"row {self.current} is still open: finish it first (or click Skip)"
        self.current, self.started = row_id, self.clock()
        with open(os.path.join(self.out_dir, "CURRENT_ROW.txt"), "w", encoding="utf-8") as fh:
            fh.write(row_id)
        return True, f"started {row_id}"

    def finish(self, status, note=""):
        """The result line is written FIRST (evidence_error 'pending'), then the evidence is taken, then the line is rewritten with the outcome. In the 2026-11-17 run pressing a result
        button crashed QGIS while the evidence was being taken and the verdict was lost with it; now a crash leaves a line the analysis reads as unsupported, never nothing."""
        if status not in STATUSES:
            return False, f"status must be one of {', '.join(STATUSES)}"
        if not self.current:
            return False, "press Start on a row first"
        row_id = self.current
        now = self.clock()
        record = {"row": row_id, "status": status, "note": note, "started": round(self.started, 1), "finished": round(now, 1),
                  "seconds": round(now - self.started, 1), "evidence_error": "pending"}
        append_result(self.out_dir, record)
        self._clear_current()
        self.current = self.started = None
        error = ""
        try:
            self.snapshot(row_id, note)
        except Exception as e:                         # the result stays recorded, but marked so the analysis does not trust it
            error = f"{type(e).__name__}: {e}"
        append_result(self.out_dir, {**record, "evidence_error": error})
        return True, f"{row_id}: {status}" + (f" (evidence problem: {error})" if error else "")

    def _clear_current(self):
        with contextlib.suppress(OSError):
            os.remove(os.path.join(self.out_dir, "CURRENT_ROW.txt"))


MAX_INTERRUPTIONS = 2


def finished_rows(out_dir):
    """Rows that have a result and need nothing more. A row recorded as 'interrupted' (QGIS closed while it was open) is NOT finished until it has been interrupted MAX_INTERRUPTIONS times, so a row
    that was only cut short is offered again, and one that really crashes QGIS cannot loop forever. Pure apart from reads."""
    return {row for row, rec in load_results(out_dir).items() if rec.get("evidence_error") != "interrupted"}


def recover_interrupted(out_dir, clock=time.time):
    """If QGIS closed or crashed while a row was open, CURRENT_ROW.txt is still there at the next start: record that row as FAIL 'interrupted' so it is never silently lost, remove the
    marker, and return the row id (or None). Pure apart from files."""
    marker = os.path.join(out_dir, "CURRENT_ROW.txt")
    if not os.path.isfile(marker):
        return None
    with open(marker, encoding="utf-8") as fh:
        row_id = fh.read().strip()
    os.remove(marker)
    previous = load_results(out_dir).get(row_id)
    if not row_id or (previous and previous.get("evidence_error") != "interrupted"):
        return None
    attempts = 1 + (int(re.search(r"attempt (\d+)", previous.get("note", "")).group(1)) if previous and re.search(r"attempt (\d+)", previous.get("note", "")) else 0)
    now = round(clock(), 1)
    append_result(out_dir, {"row": row_id, "status": "FAIL", "note": f"QGIS closed or crashed while this row was open (attempt {attempts}; recorded automatically at the next start)",
                            "started": now, "finished": now, "seconds": 0,
                            "evidence_error": "interrupted" if attempts < MAX_INTERRUPTIONS else "interrupted-final"})
    return row_id


def canonical_row_id(row_id, card_ids):
    """The card id a result line means. An agent wrote 'C6', 'C7', 'C10' (the part before the first dash) in the owner's rc5 run, so the report showed those rows as 'no result'
    and the evidence went into a folder the report did not look at. An exact id wins; a short one is accepted only when exactly one card starts with it. Pure."""
    row_id = str(row_id or "").strip()
    ids = list(card_ids)
    if row_id in ids:
        return row_id
    matches = [c for c in ids if c.split("-", 1)[0] == row_id or c.startswith(row_id + "-")]
    return matches[0] if len(matches) == 1 else row_id


def new_result_rows(out_dir, seen):
    """The result lines written since the last look: [(row_id, line_dict)] for every row in RESULTS_GUI.csv whose id is not in `seen` (a set the caller keeps). The watcher in QGIS calls
    this every few seconds and takes the evidence for each new row. A row the agent corrects later is not re-snapped. Pure apart from reading the file."""
    fresh = []
    for row_id, line in load_results(out_dir).items():
        if row_id not in seen:
            fresh.append((row_id, line))
    return fresh


def record_human_rows(out_dir, cards, clock=time.time):
    """Records every row that is not for the agent as SKIP (with the reason) unless it already has a result, so the agent only ever has real work left. Returns the ids recorded. Pure apart from files."""
    have = load_results(out_dir)
    now = round(clock(), 1)
    recorded = []
    for card in cards:
        if not card["can_run"] and card["id"] not in have:
            append_result(out_dir, {"row": card["id"], "status": "SKIP", "note": f"human row: {card['why_not']}", "started": now, "finished": now, "seconds": 0, "evidence_error": ""})
            recorded.append(card["id"])
    return recorded


def start_log(out_dir, text, clock=time.time):
    """Appends one line to results/watcher.log. The 2026-11-20 Haiku run (package 7cef7bc4, QGIS 4.2.3) left no trace of whether the dock ever appeared: an error while the start-up
    timer built it went only to the QGIS Python console, which nobody could read, and no dock_errors.txt existed because the button handler never ran. Never raises. Pure apart from files."""
    try:
        os.makedirs(out_dir, exist_ok=True)
        with open(os.path.join(out_dir, "watcher.log"), "a", encoding="utf-8") as fh:
            fh.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S', time.localtime(clock()))} {text}\n")
    except OSError:
        pass


def start_error(out_dir, where, exc, clock=time.time):
    """Writes a start-up failure to watcher.log AND watcher_errors.txt with the full traceback, so the report can say the watcher did not start and why. Never raises."""
    import traceback
    trace = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    start_log(out_dir, f"START-UP FAILED in {where}: {type(exc).__name__}: {exc}", clock)
    try:
        with open(os.path.join(out_dir, "watcher_errors.txt"), "a", encoding="utf-8") as fh:
            fh.write(f"--- start-up failure in {where} ---\n{trace}\n")
    except OSError:
        pass


def screen_capture_command(path, platform=sys.platform):
    """argv that saves the whole screen to `path` from OUTSIDE QGIS (Windows PowerShell + System.Drawing), or None off Windows. Pure."""
    if not platform.startswith("win"):
        return None
    target = str(path).replace("'", "''")
    script = ("Add-Type -AssemblyName System.Windows.Forms,System.Drawing; $b=[System.Windows.Forms.SystemInformation]::VirtualScreen; "
              "$bmp=New-Object System.Drawing.Bitmap $b.Width,$b.Height; $g=[System.Drawing.Graphics]::FromImage($bmp); "
              "$g.CopyFromScreen($b.Location,[System.Drawing.Point]::Empty,$b.Size); "
              f"New-Item -ItemType Directory -Force -Path (Split-Path '{target}') | Out-Null; $bmp.Save('{target}'); $g.Dispose(); $bmp.Dispose()")
    return ["powershell", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-Command", script]


def write_cards(path, cards):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(cards, fh, indent=1, ensure_ascii=False)
