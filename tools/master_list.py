"""Keep docs/MASTER_TASK_LIST_*.md and its CSV copy in step.

The CSV is the data; the Markdown tables are what a person reads. Two commands:

    python tools/master_list.py check
        fails (exit 1) when a row's id, priority, owner or status differs between the two files, a status word is not one of the allowed
        words, an id repeats, a `depends_on` names an id that does not exist, or the 'Counts by status' table is wrong.

    python tools/master_list.py set ROW-ID "New status" ["one-line note"]
        changes the status in both files, rewrites the counts table, and appends a dated line to the change log at the end of the Markdown
        (the note, or the status change if there is none). Statuses are never deleted: a finished row is set to Closed with its note.

The file pair is the newest docs/MASTER_TASK_LIST_*.md; pass --md PATH to choose another. Pure standard library, no QGIS.
"""
import argparse
import csv
import datetime
import glob
import io
import os
import re
import sys
from pathlib import Path

STATUSES = ("Not started", "Waiting on you", "Decision needed", "Blocked", "In progress", "Closed", "Closed (record)")
STATUS_COL = 7        # zero-based cell index in a Markdown row (0 ID,1 Task,2 Why,3 Who,4 Depends,5 Size,6 Pri,7 Status,8 Source)
PRIORITY_COL, WHO_COL = 6, 3
LOG_HEADING = "## Change log"
COUNTS_HEADING = "## Counts by status"


def newest_md():
    found = sorted(glob.glob(os.path.join(os.path.dirname(__file__), "..", "docs", "MASTER_TASK_LIST_*.md")))
    if not found:
        raise SystemExit("no docs/MASTER_TASK_LIST_*.md found")
    return os.path.normpath(found[-1])


def read_csv(path):
    with open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def write_csv(path, rows):
    fields = ["id", "stream", "task", "why", "who", "depends_on", "size", "priority", "status", "source", "notes"]
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(out.getvalue())


def split_row(line):
    """Cells of a Markdown table row; a pipe inside a cell is not used in this file."""
    return [c.strip() for c in line.strip().strip("|").split("|")]


def md_rows(text):
    rows = {}
    for line in text.split("\n"):
        if re.match(r"^\| [A-Z]+-[A-Z0-9]+ \|", line):
            cells = split_row(line)
            rows[cells[0]] = cells
    return rows


def counts_block(rows):
    counts = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    lines = [COUNTS_HEADING, "", "| Status | Rows |", "|---|---|"]
    for status, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
        lines.append(f"| {status} | {n} |")
    lines.append(f"| **Total** | **{len(rows)}** |")
    return "\n".join(lines)


def replace_counts(text, rows):
    start = text.index(COUNTS_HEADING)
    nxt = text.find("\n## ", start + 1)
    block = counts_block(rows)
    return text[:start] + block + "\n" + (text[nxt:] if nxt != -1 else "")


def problems(md_path, csv_path):
    rows = read_csv(csv_path)
    text = Path(md_path).read_text(encoding="utf-8")
    ids = [r["id"] for r in rows]
    found = [f"id {dup} appears more than once in the CSV" for dup in sorted({i for i in ids if ids.count(i) > 1})]
    known = set(ids)
    for r in rows:
        if r["status"] not in STATUSES:
            found.append(f"{r['id']}: status '{r['status']}' is not one of {STATUSES}")
        found.extend(
            f"{r['id']}: depends_on names '{dep}', which is not a row"
            for dep in re.split(r"[,\s]+", r["depends_on"].strip())
            if dep and dep != "-" and dep not in known
        )
    in_md = md_rows(text)
    for r in rows:
        cells = in_md.get(r["id"])
        if cells is None:
            found.append(f"{r['id']}: in the CSV but not in the Markdown")
            continue
        for label, col, key in (("status", STATUS_COL, "status"), ("priority", PRIORITY_COL, "priority"), ("who", WHO_COL, "who")):
            if cells[col] != r[key]:
                found.append(f"{r['id']}: {label} is '{r[key]}' in the CSV and '{cells[col]}' in the Markdown")
    found.extend(f"{extra}: in the Markdown but not in the CSV" for extra in sorted(set(in_md) - known))
    if COUNTS_HEADING in text:
        start = text.index(COUNTS_HEADING)
        nxt = text.find("\n## ", start + 1)
        current = text[start:nxt if nxt != -1 else len(text)].strip()
        if current != counts_block(rows).strip():
            found.append("the 'Counts by status' table does not match the CSV")
    else:
        found.append("the Markdown has no 'Counts by status' section")
    return found


def set_status(md_path, csv_path, row_id, status, note):
    if status not in STATUSES:
        raise SystemExit(f"status must be one of {STATUSES}")
    rows = read_csv(csv_path)
    match = [r for r in rows if r["id"] == row_id]
    if not match:
        raise SystemExit(f"no row {row_id}")
    old = match[0]["status"]
    match[0]["status"] = status
    if note:
        match[0]["notes"] = note
    write_csv(csv_path, rows)
    text = Path(md_path).read_text(encoding="utf-8")
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if line.startswith(f"| {row_id} |"):
            cells = split_row(line)
            cells[STATUS_COL] = status
            lines[i] = "| " + " | ".join(cells) + " |"
            break
    text = replace_counts("\n".join(lines), rows)
    today = datetime.date.today().isoformat()
    entry = f"- {today}: {row_id} {old} -> {status}" + (f". {note}" if note else "")
    if LOG_HEADING not in text:
        text = text.rstrip("\n") + f"\n\n{LOG_HEADING}\n\nNewest last. One line per status change; written by `tools/master_list.py set`.\n\n"
    text = text.rstrip("\n") + "\n" + entry + "\n"
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write(text)
    print(entry)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--md", default=None)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check")
    s = sub.add_parser("set")
    s.add_argument("row_id")
    s.add_argument("status")
    s.add_argument("note", nargs="?", default="")
    args = parser.parse_args(argv)
    md_path = args.md or newest_md()
    csv_path = md_path[:-3] + ".csv"
    if args.cmd == "check":
        found = problems(md_path, csv_path)
        for f in found:
            print("PROBLEM:", f)
        print("master list in step" if not found else f"{len(found)} problem(s)")
        return 1 if found else 0
    set_status(md_path, csv_path, args.row_id, args.status, args.note)
    return 0


if __name__ == "__main__":
    sys.exit(main())
