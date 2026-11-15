"""Pure half of the computer-use smoke package (no QGIS, no Qt): turns smoke rows into one short card each, keeps the result log, and runs the one-row-at-a-time session the in-QGIS dock drives.

Why: the 2026-11-13/14 run asked a small agent to follow a long hand sheet AND to remember the evidence (console commands, screenshots, file names). It forgot. Here the agent only
does the steps on one card and presses a result button; pressing it takes the evidence (tools/smoke_dock.py calls snap), so a result without evidence cannot be recorded."""
import csv
import json
import os
import re
import time

STATUSES = ("PASS", "PARTIAL", "FAIL", "SKIP")
CONSOLE = re.compile(r"snap\(|shot\(|begin\(|collect_evidence|Python console|exec\(open|EVIDENCE_HOWTO|\bsnap\b", re.I)
HUMAN_ONLY = re.compile(r"fluent|GeoDa|MCP client|Antigravity|Claude Code, Codex|second tool", re.I)
RESULT_FIELDS = ["row", "status", "note", "started", "finished", "seconds", "evidence_error"]


def clean(text):
    """Drops every sentence that tells the reader to type a console command or run snap(): the dock does that. Pure."""
    parts = re.split(r"(?<=[.;])\s+(?=[A-Z(0-9'\"])", str(text or ""))
    return " ".join(p for p in parts if not CONSOLE.search(p)).strip()


def make_cards(rows, machine_rows=None):
    """One card per row, in running order. machine_rows maps a hand row id to the ids of the agent-run rows that already check its numbers. Pure."""
    machine_rows = machine_rows or {}
    cards = []
    for row in rows:
        needs = str(row.get("needs", ""))
        human = bool(HUMAN_ONLY.search(needs))
        cards.append({
            "id": row["id"], "session": row.get("session", ""), "title": row.get("title", ""), "needs": needs,
            "model_needed": bool(re.search(r"model|key", needs, re.I)), "internet_needed": bool(re.search(r"internet|network", needs, re.I)),
            "can_run": not human, "why_not": "needs a second program or a fluent reader a computer-use agent does not have" if human else "",
            "starts_from": clean(row.get("starts_from", "")), "do": clean(row.get("do", "")), "expect": clean(row.get("expect", "")),
            "pass_if": clean(row.get("pass_if", "")), "also_capture": clean(row.get("evidence", "")), "files": list(row.get("files", [])),
            "machine_checked_by": machine_rows.get(row["id"], []),
        })
    return cards


def card_text(card):
    """The text the dock shows. Pure."""
    lines = [f"ROW {card['id']}  -  {card['title']}", ""]
    if not card["can_run"]:
        return "\n".join([*lines, f"NOT FOR THIS AGENT: {card['why_not']}. Click Skip and write 'human row' in the note."])
    for label, key in (("START FROM", "starts_from"), ("DO", "do"), ("EXPECT", "expect"), ("PASS ONLY IF", "pass_if"), ("EXTRA EVIDENCE (the dock already saved the window and layers; do this only if easy)", "also_capture")):
        if card.get(key):
            lines += [f"{label}: {card[key]}", ""]
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
        if status not in STATUSES:
            return False, f"status must be one of {', '.join(STATUSES)}"
        if not self.current:
            return False, "press Start on a row first"
        row_id, error = self.current, ""
        try:
            self.snapshot(row_id, note)
        except Exception as e:                         # the result is still recorded, but marked so the analysis does not trust it
            error = f"{type(e).__name__}: {e}"
        now = self.clock()
        append_result(self.out_dir, {"row": row_id, "status": status, "note": note, "started": round(self.started, 1), "finished": round(now, 1),
                                     "seconds": round(now - self.started, 1), "evidence_error": error})
        self.current = self.started = None
        return True, f"{row_id}: {status}" + (f" (evidence problem: {error})" if error else "")


def write_cards(path, cards):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(cards, fh, indent=1, ensure_ascii=False)
