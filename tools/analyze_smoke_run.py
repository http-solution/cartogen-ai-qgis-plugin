"""Reads a finished computer-use smoke run and writes REPORT.md. Pure Python, no QGIS. A claimed PASS is only VERIFIED when evidence made by the program (not by the agent) backs it.

    python analyze_smoke_run.py RESULTS_FOLDER CARDS.json [--agent-rows AGENT_RUN_ROWS.json]

Per row it reports: the agent's claim (RESULTS_GUI.csv), the program's own verdict (RESULTS.csv of the headless runner), which evidence files exist, the tools the plugin really called
(plugin_evidence), the seconds spent, and a trust level:
  SUPPORTED     (only when the evidence watcher never reported) claimed PASS with the agent's notes and, for a model row, tool calls the plugin itself recorded
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

sys.path.insert(0, str(Path(__file__).resolve().parent))
from smoke_cards import canonical_row_id


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
    short = row_id.split("-", 1)[0]
    folders = [p for p in base.glob(f"{row_id}*") if p.is_dir()] if base.is_dir() else []
    if short != row_id and (base / short).is_dir():             # evidence the watcher saved before it knew the full id (an older package)
        folders.append(base / short)
    for folder in folders:
        for path in folder.rglob("*"):
            if path.name == "window.png" and path.stat().st_size > 0:
                found["window"] = True
            elif path.name == "layers.json":
                found["layers"] = True
            elif path.name == "steps.jsonl":
                found["plugin_evidence"] = True
            elif path.name == "tools_called.txt":
                found["tools"] += [t.strip() for t in path.read_text(encoding="utf-8", errors="replace").splitlines() if t.strip()]
    # Without the watcher (or when it failed) the agent's notes sit in evidence/<row>/observations.txt or outputs/<row>/result.txt, and the PLUGIN's own record of the tools it called
    # (cartogen_evidence/<stamp>/steps.jsonl) sits next to the saved project, in outputs/<row>*/ or work/<row>*/. Both are read here; the tool names come from the program-written steps.jsonl.
    found["notes"] = False
    for sub in ("evidence", "outputs", "work"):
        base_dir = Path(results) / sub
        patterns = [f"{row_id}*"] + ([f"{row_id.split('-')[0]}_*"] if sub == "work" else [])       # work copies are named E5_copy, W11_copy, ...
        for folder in (p for pat in patterns for p in base_dir.glob(pat) if p.is_dir()) if base_dir.is_dir() else ():
            for path in folder.rglob("*"):
                if path.name in ("observations.txt", "result.txt") and path.stat().st_size > 0:
                    found["notes"] = True
                elif path.name == "steps.jsonl" and sub == "work":
                    found["unattributed"] = True       # a work copy of 3_test_files also holds the evidence of earlier rows (E5_copy held a dissolve_layer call E5 never makes): cannot be counted for THIS row
                elif path.name == "steps.jsonl":
                    found["plugin_evidence"] = True
                    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                        try:
                            tool = json.loads(line).get("tool")
                        except ValueError:
                            continue
                        if tool:
                            found["tools"].append(tool)
    shots = Path(results) / "screens"
    if shots.is_dir() and any(f.stat().st_size > 0 for f in shots.glob(f"{row_id}*.png")):
        found["window"] = True                    # the watcher's screen capture is made from outside QGIS and lands here
    return found


def judge(card, claim, ev, dock_shown=True):
    """(trust, reason). Pure."""
    if not card["can_run"]:
        return "HUMAN ROW", card["why_not"]
    if not claim:
        return "NO RESULT", "no line in RESULTS_GUI.csv"
    status = claim["status"]
    if status != "PASS":
        return "CLAIMED", f"{status}: {claim.get('note', '')}"
    if not dock_shown:
        # No watcher: the agent's notes plus the plugin's own tool record are the support. A row that needs a model must show at least one tool call.
        missing = []
        if not ev.get("notes"):
            missing.append("no observations.txt / result.txt")
        if card["model_needed"] and not ev["plugin_evidence"]:
            missing.append("the row needs a model but the plugin recorded no tool call for it" + (" (the only steps.jsonl is in a work copy that also holds older rows, so it cannot be attributed)" if ev.get("unattributed") else " (no steps.jsonl beside a saved project)"))
        return ("UNSUPPORTED", "; ".join(missing)) if missing else ("SUPPORTED", f"agent notes + {len(ev['tools'])} plugin tool call(s) recorded by the plugin, no window picture (watcher did not report)")
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


def written_by(claim):
    """'dock' when the line carries the timings only the card dock writes (started, finished, seconds), else 'typed'. Pure.

    Why: in the 2026-11-20 run 50 result lines were typed in by the agent afterwards (the dock recorded nothing), and the
    report gave them the same weight as lines the program wrote. The prompt tells the agent to leave those columns empty,
    so a filled-in set is the dock's signature."""
    if claim and claim.get("started") and claim.get("finished") and claim.get("seconds"):
        return "dock"
    return "typed" if claim else ""


def build_report(results, cards, agent_rows=()):
    gui, machine = load_results_pair(results)
    ids = [c["id"] for c in cards]
    renamed = {}
    for written, claim in gui.items():
        real = canonical_row_id(written, ids)
        if real != written and real not in gui:
            renamed[real] = {**claim, "note": f"(written as '{written}') " + str(claim.get("note", ""))}
        else:
            renamed[written] = claim
    gui = renamed
    lines = ["# Computer-use smoke run: report\n"]
    start_log = Path(results) / "watcher.log"
    shown = start_log.is_file() and "watcher running" in start_log.read_text(encoding="utf-8", errors="replace")
    lines += ["## Evidence watcher start-up\n", ("The evidence watcher reported that it was running (results/watcher.log)." if shown else
              "WARNING: the evidence watcher never reported that it was running (no results/watcher.log line 'watcher running'). Every result below was then written without its evidence: read watcher.log and watcher_errors.txt first."), ""]
    table, counts, writers = [], {}, {}
    for card in cards:
        ev = evidence_for(results, card["id"])
        trust, why = judge(card, gui.get(card["id"]), ev, dock_shown=shown)
        counts[trust] = counts.get(trust, 0) + 1
        claim = gui.get(card["id"], {})
        writer = written_by(claim)
        writers[writer] = writers.get(writer, 0) + 1
        table.append(f"| {card['id']} | {claim.get('status', '')} | {writer} | {trust} | {claim.get('seconds', '')} | {', '.join(sorted(set(ev['tools']))[:6])} | {why} |")
    machine_lines = [f"| {rid} | {r['status']} | {r['covers_row']} |" for rid, r in machine.items()]
    mc = {}
    for r in machine.values():
        mc[r["status"]] = mc.get(r["status"], 0) + 1
    lines += ["## Totals\n", "Computer-use rows: " + (", ".join(f"{k}: {v}" for k, v in sorted(counts.items())) or "none"),
              "Result lines written by the agent: " + str(writers.get("typed", 0) + writers.get("dock", 0)) + " (each is only as trustworthy as the evidence the watcher and the plugin recorded for it: see the trust column)",
              "Program-checked rows: " + (", ".join(f"{k}: {v}" for k, v in sorted(mc.items())) or "none run"), "",
              "A claimed PASS counts only when its trust is VERIFIED. UNSUPPORTED means the agent said PASS but the program's own evidence is missing: treat as not run.\n",
              "## Computer-use rows\n", "| row | claim | written by | trust | seconds | tools called | reason |", "|---|---|---|---|---|---|---|", *table, "",
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
