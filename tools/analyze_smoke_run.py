"""Reads a finished computer-use smoke run and writes REPORT.md. Pure Python, no QGIS. A claimed PASS is only VERIFIED when evidence made by the program (not by the agent) backs it.

    python analyze_smoke_run.py RESULTS_FOLDER CARDS.json [--agent-rows AGENT_RUN_ROWS.json]

Per row it reports: the agent's claim (RESULTS_GUI.csv), the program's own verdict (RESULTS.csv of the headless runner), which evidence files exist, the tools the plugin really called
(plugin_evidence), the seconds spent, and a trust level:
  VERIFIED      claimed PASS and window.png + layers.json exist (and, for a row that needs a model, at least one plugin tool call was recorded)
  UNSUPPORTED   claimed PASS but that evidence is missing, or the evidence step reported an error: do not believe it
  CLAIMED       PARTIAL / FAIL / SKIP with a note (nothing to verify, but read the note)
  NO RESULT     no line for the row: it was not run
  HUMAN ROW     the card says a computer-use agent cannot do it
  MACHINE       a row of the headless runner: PASS / FAIL / ERROR from its own checks"""
import csv
import json
import sys
from pathlib import Path


def load_cards(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_csv(path, key):
    p = Path(path)
    if not p.is_file():
        return {}
    with open(p, encoding="utf-8", newline="") as fh:
        return {r[key]: r for r in csv.DictReader(fh)}


def evidence_for(results, row_id):
    """Which program-made files exist for a row, searching evidence/<row>/ at any depth. Pure apart from reads."""
    base = Path(results) / "evidence"
    found = {"window": False, "layers": False, "plugin_evidence": False, "tools": []}
    for folder in (p for p in base.glob(f"{row_id}*") if p.is_dir()) if base.is_dir() else ():
        for path in folder.rglob("*"):
            if path.name == "window.png" and path.stat().st_size > 0:
                found["window"] = True
            elif path.name == "layers.json":
                found["layers"] = True
            elif path.name == "steps.jsonl":
                found["plugin_evidence"] = True
            elif path.name == "tools_called.txt":
                found["tools"] += [t.strip() for t in path.read_text(encoding="utf-8", errors="replace").splitlines() if t.strip()]
    shots = Path(results) / "screens"
    if shots.is_dir() and any(f.stat().st_size > 0 for f in shots.glob(f"{row_id}*.png")):
        found["window"] = True                    # the dock's screen capture is made from outside QGIS and lands here
    return found


def judge(card, claim, ev):
    """(trust, reason). Pure."""
    if not card["can_run"]:
        return "HUMAN ROW", card["why_not"]
    if not claim:
        return "NO RESULT", "no line in RESULTS_GUI.csv"
    status = claim["status"]
    if status != "PASS":
        return "CLAIMED", f"{status}: {claim.get('note', '')}"
    problems = []
    if claim.get("evidence_error"):
        problems.append(f"evidence step failed: {claim['evidence_error']}")
    if not ev["window"]:
        problems.append("no window.png")
    if not ev["layers"]:
        problems.append("no layers.json")
    if card["model_needed"] and not ev["plugin_evidence"]:
        problems.append("the row needs a model but no plugin tool call was recorded")
    return ("UNSUPPORTED", "; ".join(problems)) if problems else ("VERIFIED", "evidence present")


def build_report(results, cards, agent_rows=()):
    gui, machine = load_results_pair(results)
    lines = ["# Computer-use smoke run: report\n"]
    start_log = Path(results) / "dock_start.log"
    shown = start_log.is_file() and "dock shown" in start_log.read_text(encoding="utf-8", errors="replace")
    lines += ["## Card dock start-up\n", ("The dock reported that it was shown (results/dock_start.log)." if shown else
              "WARNING: the dock never reported that it was shown (no results/dock_start.log line 'dock shown'). Every result below was then written without it: read dock_start.log and dock_errors.txt first."), ""]
    table, counts = [], {}
    for card in cards:
        ev = evidence_for(results, card["id"])
        trust, why = judge(card, gui.get(card["id"]), ev)
        counts[trust] = counts.get(trust, 0) + 1
        claim = gui.get(card["id"], {})
        table.append(f"| {card['id']} | {claim.get('status', '')} | {trust} | {claim.get('seconds', '')} | {', '.join(sorted(set(ev['tools']))[:6])} | {why} |")
    machine_lines = [f"| {rid} | {r['status']} | {r['covers_row']} |" for rid, r in machine.items()]
    mc = {}
    for r in machine.values():
        mc[r["status"]] = mc.get(r["status"], 0) + 1
    lines += ["## Totals\n", "Computer-use rows: " + (", ".join(f"{k}: {v}" for k, v in sorted(counts.items())) or "none"),
              "Program-checked rows: " + (", ".join(f"{k}: {v}" for k, v in sorted(mc.items())) or "none run"), "",
              "A claimed PASS counts only when its trust is VERIFIED. UNSUPPORTED means the agent said PASS but the program's own evidence is missing: treat as not run.\n",
              "## Computer-use rows\n", "| row | claim | trust | seconds | tools called | reason |", "|---|---|---|---|---|---|", *table, "",
              "## Program-checked rows\n", "| row | status | covers hand row |", "|---|---|---|", *machine_lines, ""]
    slow = sorted((float(c.get("seconds") or 0), r) for r, c in gui.items())[-5:]
    lines += ["## Slowest rows\n", *[f"- {r}: {s:.0f} s" for s, r in reversed(slow)], ""]
    return "\n".join(lines) + "\n", counts, mc


def load_results_pair(results):
    return load_csv(Path(results) / "RESULTS_GUI.csv", "row"), load_csv(Path(results) / "RESULTS.csv", "row")


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 2
    results, cards = argv[1], load_cards(argv[2])
    text, counts, mc = build_report(results, cards)
    (Path(results) / "REPORT.md").write_text(text, encoding="utf-8")
    print(text)
    bad = counts.get("UNSUPPORTED", 0) + counts.get("NO RESULT", 0) + mc.get("FAIL", 0) + mc.get("ERROR", 0)
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
