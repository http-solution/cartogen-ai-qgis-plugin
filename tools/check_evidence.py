"""Reads what a hand-test run sends back and prints a verdict per row (PLAN-021 WP-G), so nobody has to read every evidence folder by hand.

    python tools/check_evidence.py FOLDER [--rows docs/HAND_TEST_V2_ROWS.json]

FOLDER is the returned bundle folder. It may hold: layout_check.json (from tools/layout_check_script.py), 4_RESULTS.csv, and cartogen_evidence
folders (one per request, with summary.md and steps.jsonl). Reports:
  - the layout checks that failed, with what was measured;
  - every row left blank in 4_RESULTS.csv;
  - for a row that lists expected_tools / forbidden_tools, which tools the matching request really called.
It judges only what the files show. Whether a page looks right to a person is not in any file; that stays a person's call. Pure Python, no QGIS."""
import csv
import json
import sys
from pathlib import Path


def load_layout_check(folder):
    found = sorted(Path(folder).rglob("layout_check.json"))
    if not found:
        return None
    return json.loads(found[0].read_text(encoding="utf-8"))


def load_results(folder):
    found = sorted(Path(folder).rglob("4_RESULTS.csv"))
    if not found:
        return []
    with open(found[0], encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def evidence_requests(folder):
    """[(request text, [tool names in order], folder)] for every cartogen_evidence folder under `folder`."""
    out = []
    for summary in sorted(Path(folder).rglob("summary.md")):
        text = summary.read_text(encoding="utf-8", errors="replace")
        request = text.split("## Request", 1)[-1].split("## Steps", 1)[0].strip() if "## Request" in text else ""
        tools = []
        steps = summary.parent / "steps.jsonl"
        if steps.is_file():
            for line in steps.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.strip():
                    with_tool = json.loads(line)
                    tools.append(with_tool.get("tool", ""))
        out.append((request, tools, summary.parent.name))
    return out


def verdict_for_row(row, requests):
    """(verdict, note) for one expected-tools row. `row` has optional prompt, expected_tools, forbidden_tools. Pure."""
    prompt = (row.get("prompt") or "").strip().lower()
    if not prompt:
        return "n/a", "no prompt to match"
    matches = [r for r in requests if prompt in r[0].lower()]
    if not matches:
        return "NO EVIDENCE", "no evidence folder holds this request (was 'Save an evidence folder for each request' ticked?)"
    _request, tools, name = matches[-1]
    forbidden = [t for t in row.get("forbidden_tools", []) if t in tools]
    wanted = row.get("expected_tools", [])
    missing = bool(wanted) and not any(t in tools for t in wanted)
    if forbidden or missing:
        problems = []
        if forbidden:
            problems.append("called " + ", ".join(forbidden))
        if missing:
            problems.append("never called " + " or ".join(wanted))
        return "FAIL", f"{name}: " + "; ".join(problems) + f" (tools: {', '.join(tools) or 'none'})"
    return "PASS", f"{name}: tools {', '.join(tools) or 'none'}"


def main(argv):
    if len(argv) < 2:
        raise SystemExit(__doc__)
    folder = Path(argv[1])
    rows_file = Path(argv[argv.index("--rows") + 1]) if "--rows" in argv else Path(__file__).resolve().parent.parent / "docs" / "HAND_TEST_V2_ROWS.json"
    lines = []
    check = load_layout_check(folder)
    if check is None:
        lines.append("layout check: layout_check.json not found (was tools/layout_check_script.py run?)")
    else:
        lines.append(f"layout check: {check['passed']} of {len(check['checks'])} passed (QGIS {check.get('qgis')}, plugin {check.get('plugin_version')}, fonts {check.get('fonts_found')})")
        lines.extend(f"  FAIL {e['id']} {e['title']}\n       measured: {json.dumps(e['got'], default=str)[:500]}" for e in check["checks"] if not e["ok"])
    results = load_results(folder)
    blank = [r["id"] for r in results if not (r.get("result (Pass/Partial/Fail/Skip)") or "").strip()]
    lines.append(f"results file: {len(results)} rows, {len(blank)} left blank" + (f": {', '.join(blank)}" if blank else ""))
    requests = evidence_requests(folder)
    lines.append(f"evidence folders: {len(requests)}")
    if rows_file.is_file():
        for row in json.loads(rows_file.read_text(encoding="utf-8")).get("rows", []):
            if row.get("expected_tools") or row.get("forbidden_tools"):
                verdict, note = verdict_for_row(row, requests)
                lines.append(f"  {verdict:11} {row['id']}: {note}")
    print("\n".join(lines))
    failed = check is not None and check["failed"]
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
