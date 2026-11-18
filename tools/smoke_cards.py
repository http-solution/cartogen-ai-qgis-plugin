"""Pure half of the computer-use smoke package (no QGIS, no Qt): turns smoke rows into one short card each, keeps the result log, and runs the one-row-at-a-time session the in-QGIS dock drives.

Why: the 2026-11-13/14 run asked a small agent to follow a long hand sheet AND to remember the evidence (console commands, screenshots, file names). It forgot. Here the agent only
does the steps on one card and presses a result button; pressing it takes the evidence (tools/smoke_dock.py calls snap), so a result without evidence cannot be recorded."""
import contextlib
import csv
import json
import os
import re
import sys
import time

STATUSES = ("PASS", "PARTIAL", "FAIL", "SKIP")
CONSOLE = re.compile(r"snap\(|shot\(|begin\(|collect_evidence|Python console|exec\(open|EVIDENCE_HOWTO|\bsnap\b", re.I)
HUMAN_ONLY = re.compile(r"fluent|GeoDa|MCP client|Antigravity|Claude Code, Codex|second tool", re.I)
HUMAN_IDS = {
    "V1-update": "it needs an older plugin version to update from, which this package does not contain",
    "C18-persona-upgrade": "it needs an older plugin build to install the new one over, which this package does not contain",
    "F3-check-evidence": "it checks the results file of the hand package, not this package (ANALYZE.bat makes this package's report)",
    "W6-mcp-probe": "it needs commands typed in a terminal, which the Claude app's computer use does not allow (click only)",
    "W7-mcp-dialog": "it needs commands typed in a terminal, which the Claude app's computer use does not allow (click only)",
    "W8-export": "it needs a command typed in a terminal, which the Claude app's computer use does not allow (click only)",
    "W10-import-bad": "it needs a command typed in a terminal, which the Claude app's computer use does not allow (click only)",
}
SLOW = re.compile(r"overpass|osm|download|geofabrik|worldpop|stac|sentinel|isochrone|service area|large|mirror", re.I)
RESULT_FIELDS = ["row", "status", "note", "started", "finished", "seconds", "evidence_error"]


_DOC_REF = re.compile(r"\s*\((?:see )?(?:EVIDENCE_HOWTO|3_SHEET|CHECKLIST)[^)]*\)", re.I)
_EVIDENCE_SETTING = re.compile(r"'Save an evidence folder for each request' ticked( in Settings)?", re.I)
_PY = re.compile(r"\bpython3? (?=(?:6_tools|2_layout_check|tools)[\\/])")


def fill_paths(text):
    """The terminal commands in the rows say `python 6_tools/x.py`: in this package they run through PY.bat (QGIS's own Python, always present), and <bundle> is the package folder. Pure."""
    text = _DOC_REF.sub("", str(text or ""))
    text = _EVIDENCE_SETTING.sub("evidence saving already switched on for you", text)
    text = text.replace("results\\outputs\\", "<PACKAGE>\\results\\outputs\\").replace("3_test_files\\", "<PACKAGE>\\3_test_files\\")
    text = text.replace("<PACKAGE>\\<PACKAGE>\\", "<PACKAGE>\\")
    return _PY.sub("PY.bat ", text).replace("<bundle>", "<PACKAGE>")


def clean(text):
    """Drops every sentence that tells the reader to type a console command or run snap(): the dock does that. Pure."""
    parts = re.split(r"(?<=[.;])\s+(?=[A-Z(0-9'\"])", _DOC_REF.sub("", str(text or "")))       # a pointer to a document that is not in this package is removed BEFORE sentences are judged, so the sentence it sat in survives
    return fill_paths(" ".join(p for p in parts if not CONSOLE.search(p)).strip())


DO_OVERRIDES = {
    "A1-layout-script": ("In QGIS: Plugins > Python Console. Type this ONE line (it is the only console command you type in this whole test) and press Enter: "
                         "exec(open(r\"<PACKAGE>\\2_layout_check\\layout_check_script.py\", encoding=\"utf-8\").read())   "
                         "It runs by itself; wait for the table (if nothing prints after 2 minutes, type run() once and say so in the note). The pages are exported into the package folder, in "
                         "<PACKAGE>\\results\\outputs\\A1-layout-script. Open that folder in File Explorer, press Alt+P to switch on the Preview pane, and click each .png in turn: its picture shows in the preview "
                         "pane, so no other program is needed. Do not open the .pdf files (they open in a browser, which you cannot use). Look at each page: footer complete and inside the page, "
                         "legend entries not cut, logo left of the title, sign-off readable, disclaimer not overlapping. If a picture cannot be seen, say so and give Partial."),
}


def make_cards(rows, machine_rows=None):
    """One card per row, in running order. machine_rows maps a hand row id to the ids of the agent-run rows that already check its numbers. Pure."""
    machine_rows = machine_rows or {}
    cards = []
    for row in rows:
        needs = str(row.get("needs", ""))
        human = bool(HUMAN_ONLY.search(needs)) or row["id"] in HUMAN_IDS
        cards.append({
            "id": row["id"], "session": row.get("session", ""), "title": row.get("title", ""), "needs": needs,
            "model_needed": bool(re.search(r"model|key", needs, re.I)), "internet_needed": bool(re.search(r"internet|network", needs, re.I)),
            "can_run": not human, "why_not": HUMAN_IDS.get(row["id"], "needs a second program or a fluent reader a computer-use agent does not have") if human else "",
            "slow": bool(SLOW.search(" ".join([needs, str(row.get("do", ""))]))),
            "starts_from": clean(row.get("starts_from", "")), "do": DO_OVERRIDES.get(row["id"]) or clean(row.get("do", "")), "expect": clean(row.get("expect", "")),
            "pass_if": clean(row.get("pass_if", "")), "also_capture": clean(row.get("evidence", "")), "files": list(row.get("files", [])),
            "machine_checked_by": machine_rows.get(row["id"], []),
        })
    return cards


_BROWSER = re.compile(r"\bbrowser\b|chrome|firefox|\bedge\b|web page|HDX page", re.I)


def helps(card):
    """The general rules a card relies on (the hand sheet held them; the cards had lost them). Pure."""
    body = " ".join(str(card.get(k, "")) for k in ("starts_from", "do", "expect", "pass_if"))
    out = []
    if re.search(r"fresh chat|new chat", body, re.I):
        out.append("FRESH CHAT: this plugin version has no 'New chat' button. The chat follows the project: start the row from File > New (or open the row's project file) and the chat starts empty. "
                   "If the old conversation is still on screen, say so in the note and carry on.")
    if re.search(r"save the project", body, re.I):
        out.append(f"SAVE FIRST: File > Save As into <PACKAGE>\\results\\outputs\\{card['id']}\\ BEFORE the first request; the plugin writes its evidence next to a saved project (an unsaved project leaves none).")
    if re.search(r"a copy of", str(card.get("starts_from", "")), re.I):
        out.append(f"COPY: you do not need to copy files. Open the project, then File > Save As into <PACKAGE>\\results\\outputs\\{card['id']}\\ before you change anything, so the original in 3_test_files is never altered.")
    if _BROWSER.search(body):
        out.append("BROWSERS: the Claude app lets you only LOOK at a web browser, not click or type in it. Skip any step that needs one, say so in the note, and give the row Partial at best.")
    if re.search(r"\bNotepad\b|\bExcel\b|\bLibreOffice\b", body):
        out.append("OTHER PROGRAMS: a step that needs a program other than QGIS and File Explorer: skip that step, say so in the note, and give the row Partial at best.")
    return out


def card_text(card):
    """The text the dock shows. Pure."""
    lines = [f"ROW {card['id']}  -  {card['title']}", ""]
    if not card["can_run"]:
        return "\n".join([*lines, f"NOT FOR THIS AGENT: {card['why_not']}. Click Skip and write 'human row' in the note."])
    for label, key in (("START FROM", "starts_from"), ("DO", "do"), ("EXPECT", "expect"), ("PASS ONLY IF", "pass_if"), ("EXTRA EVIDENCE (the dock already saved the window and layers; do this only if easy)", "also_capture")):
        if card.get(key):
            lines += [f"{label}: {card[key]}", ""]
    for line in helps(card):
        lines += [line, ""]
    if card.get("slow"):
        lines.append("SLOW ROW: a tool here can run for up to 6 minutes and QGIS then looks frozen ('Not Responding'). That is normal: wait, do NOT click, do NOT restart QGIS. "
                     "If nothing has changed after 8 minutes, click Fail with the note 'no reply'.")
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


def record_human_rows(out_dir, cards, clock=time.time):
    """Records every row that is not for the agent as SKIP (with the reason) unless it already has a result, so the dock only ever shows work to do. Returns the ids recorded. Pure apart from files."""
    have = load_results(out_dir)
    now = round(clock(), 1)
    recorded = []
    for card in cards:
        if not card["can_run"] and card["id"] not in have:
            append_result(out_dir, {"row": card["id"], "status": "SKIP", "note": f"human row: {card['why_not']}", "started": now, "finished": now, "seconds": 0, "evidence_error": ""})
            recorded.append(card["id"])
    return recorded


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
