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
    too_many = [f"{t} x{tools.count(t)} (limit {n})" for t, n in (row.get("max_calls") or {}).items() if tools.count(t) > n]
    wanted = row.get("expected_tools", [])
    missing = bool(wanted) and not any(t in tools for t in wanted)
    if forbidden or missing or too_many:
        problems = []
        if forbidden:
            problems.append("called " + ", ".join(forbidden))
        if missing:
            problems.append("never called " + " or ".join(wanted))
        if too_many:
            problems.append("called too often: " + ", ".join(too_many))
        return "FAIL", f"{name}: " + "; ".join(problems) + f" (tools: {', '.join(tools) or 'none'})"
    return "PASS", f"{name}: tools {', '.join(tools) or 'none'}"


def expected_tool_checks(row):
    """[(label, check dict)] for a row: the row itself when it names a prompt's expected/forbidden tools, and one entry per item of its `checks` list
    (the full smoke package puts several prompts in one row). A check dict has prompt, expected_tools, forbidden_tools, max_calls. Pure."""
    def names_tools(item):
        return bool(item.get("expected_tools") or item.get("forbidden_tools") or item.get("max_calls"))
    found = [(row["id"], row)] if names_tools(row) else []
    found.extend((f"{row['id']} [{(check.get('prompt') or '')[:48]}]", check) for check in row.get("checks") or [] if names_tools(check))
    return found


def record_lines(folder):
    """One line per saved layer_properties.json (from collect_evidence.snap) and per mcp_probe.json: which plugin records each layer holds, and the probe's
    failed checks (PLAN-050). Reports what the files show; whether it is the RIGHT record is the row's pass_if, read by a person. Pure."""
    lines = []
    for path in sorted(Path(folder).rglob("layer_properties.json")):
        try:
            found = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            lines.append(f"  {path.parent.name}: layer_properties.json is not valid JSON")
            continue
        for layer, props in found.items():
            lines.append(f"  {path.parent.name}: {layer}: " + (", ".join(sorted(k.split("/", 1)[1] for k in props)) or "no cartogen records"))
        if not found:
            lines.append(f"  {path.parent.name}: no layer holds a cartogen record")
    for path in sorted(Path(folder).rglob("mcp_probe.json")):
        checks = json.loads(path.read_text(encoding="utf-8")).get("checks", [])
        bad = [c["id"] for c in checks if not c["ok"]]
        lines.append(f"  {path.parent.name}: mcp probe {len(checks) - len(bad)} of {len(checks)} passed" + (f"; FAILED {', '.join(bad)}" if bad else ""))
    return lines


def main(argv):
    if len(argv) < 2:
        raise SystemExit(__doc__)
    folder = Path(argv[1])
    rows_file = Path(argv[argv.index("--rows") + 1]) if "--rows" in argv else next((c for c in (Path(__file__).resolve().parent / "3_ROWS.json", Path(__file__).resolve().parent.parent / "docs" / "HAND_TEST_V2_ROWS.json") if c.is_file()), Path("3_ROWS.json"))
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
            for label, check in expected_tool_checks(row):
                verdict, note = verdict_for_row(check, requests)
                lines.append(f"  {verdict:11} {label}: {note}")
    print("\n".join(lines))
    records = record_lines(folder)
    if records:
        lines.append("plugin records and probes:")
        lines.extend(records)
    failed = check is not None and check["failed"]
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
