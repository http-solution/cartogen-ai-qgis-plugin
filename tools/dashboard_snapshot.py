#!/usr/bin/env python3
"""Builds the data files of the project-status dashboard (PLAN-052) from this repository. Standard library plus the repo's own code; no QGIS.

    python tools/dashboard_snapshot.py --out DIR [--run-tests] [--tests N] [--sandbox-errors N] [--open-prs N] [--open-pr-note TEXT] [--release TEXT]

Writes DIR/summary.json, work_items.json, activity.json, hand_tests.json and defects.json. What it reads itself: metadata.txt (version), the tool registry
(tool count), docs/FEATURE_LEDGER.json, docs/plans/PLAN-*.md, the master task list csv, `git log origin/main`, and the two hand-kept files in
docs/dashboard_data/ (hand_tests.json, defects.json: update them when a hand-test result or a defect changes). What it cannot read from a checkout and
takes as arguments: the number of open pull requests (GitHub), and the test counts (--run-tests runs the offline suite, about two minutes, and reads
the counts from its summary line; without it pass --tests/--sandbox-errors or the counts are 0 and the dashboard says they are unknown).
Never writes credentials or anything outside DIR. See docs/DASHBOARD.md for how the dashboard is refreshed from these files."""
import argparse
import csv
import datetime
import glob
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
VERIFIED_BY_HAND = re.compile(r"^hand-tested\b|\bowner (looked|confirmed|checked)\b")


def ledger_class(hand_verified):
    """'Verified by hand', 'Partly verified' or 'Not hand-verified' from a ledger entry's hand_verified text. Pure. Conservative on purpose: only text that
    says it was hand-tested, or that the owner looked, counts as verified; anything else, including text this does not recognise, is NOT counted. (The
    first version counted everything that did not start with 'not', and so counted 'plain-language hand test ... not run' as verified.)"""
    text = (hand_verified or "").strip().lower()
    if text.startswith("partly"):
        return "Partly verified"
    if VERIFIED_BY_HAND.search(text):
        return "Verified by hand"
    return "Not hand-verified"


def read_plans(repo):
    plans = []
    for path in sorted(glob.glob(str(repo / "docs" / "plans" / "PLAN-*.md"))):
        text = Path(path).read_text(encoding="utf-8")
        status = re.search(r"^Status: (.+)$", text, re.M)
        plans.append({"id": Path(path).name[:8], "status": status.group(1).strip() if status else "unknown"})
    return plans


def read_tasks(repo):
    found = sorted(glob.glob(str(repo / "docs" / "MASTER_TASK_LIST_*.csv")))
    if not found:
        return []
    with open(found[-1], encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def read_activity(repo, limit=25):
    for ref in ("origin/main", "HEAD"):
        done = subprocess.run(["git", "log", ref, "--pretty=%ad|%s", "--date=short", "-n", str(limit)], capture_output=True, text=True, cwd=repo, check=False)  # noqa: S603, S607 -- fixed argv
        if done.returncode == 0 and done.stdout.strip():
            break
    rows = []
    for line in done.stdout.splitlines():
        date, subject = line.split("|", 1)
        pr = re.search(r"\(#(\d+)\)\s*$", subject)
        rows.append({"date": date, "change": re.sub(r"\s*\(#\d+\)\s*$", "", subject), "pr": int(pr.group(1)) if pr else None})
    return rows


def tool_count(repo):
    sys.path.insert(0, str(repo / "src"))
    import cartogen_ai.core.agent.agent_orchestrator  # noqa: F401  (registers every tool)
    from cartogen_ai.core.agent.tools.registry import TOOL_REGISTRY
    return len(TOOL_REGISTRY)


def run_tests(repo):
    """(tests run, failures + errors) from the offline suite's summary lines. Slow (about two minutes). Raises when the summary cannot be read."""
    done = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", ".", "-p", "test_*.py"], capture_output=True, text=True, cwd=repo, check=False)
    text = done.stderr + done.stdout
    ran = re.search(r"^Ran (\d+) tests?", text, re.M)
    if not ran:
        raise RuntimeError("could not read the test run's summary line")
    bad = re.search(r"^FAILED \((.*)\)", text, re.M)
    problems = sum(int(n) for n in re.findall(r"(?:failures|errors)=(\d+)", bad.group(1))) if bad else 0
    return int(ran.group(1)), problems


def _live_counts(repo, ledger):
    """The measure the owner asked for (PLAN-057): of the features a live run can test, how many were SEEN working, partly, failing, or not seen. Read from
    docs/LIVE_RESULTS.json, which records only what a live run showed. `live_needs_recheck` is the regression gate: seen working, source changed since."""
    sys.path.insert(0, str(repo / "tools"))
    import live_results
    doc = json.loads((repo / "docs" / "LIVE_RESULTS.json").read_text(encoding="utf-8"))
    s = live_results.summary(doc, ledger, live_results.not_testable())
    run = next(iter(doc["runs"].values()))
    try:
        recheck = len(live_results.needs_recheck(doc, ledger, live_results.changed_since(run["baseline_commit"]), live_results.head_sha()))
    except Exception:                                                  # a shallow clone has no baseline; say unknown, not zero
        recheck = -1
    return {"live_testable": s["testable"], "live_working": s["working"], "live_partly": s["partly"], "live_failing": s["failing"],
            "live_not_seen": s["not_tested"], "live_not_testable": s["not_testable"], "live_run_date": run["date"], "live_needs_recheck": recheck}


def build(out, repo=REPO, facts=None):
    """Writes the five dashboard files into `out` and returns the summary row. `facts` carries what a checkout cannot know. Pure apart from the files."""
    facts = dict(facts or {})
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)

    def write(name, rows):
        (out / name).write_text(json.dumps(rows, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")

    ledger = json.loads((repo / "docs" / "FEATURE_LEDGER.json").read_text(encoding="utf-8"))["features"]
    classes = [ledger_class(f.get("hand_verified")) for f in ledger]
    plans = read_plans(repo)
    tasks = read_tasks(repo)
    open_tasks = [t for t in tasks if not t["status"].startswith("Closed")]
    meta = (repo / "metadata.txt").read_text(encoding="utf-8")
    count = lambda rows, key, value: sum(1 for r in rows if r[key] == value)   # noqa: E731
    live = _live_counts(repo, ledger)
    summary = {
        "as_of": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "version": re.search(r"^version=(.+)$", meta, re.M).group(1).strip(),
        "release_state": facts.get("release", "1.18.6 is held"),
        "tools": facts.get("tools") if facts.get("tools") is not None else tool_count(repo),
        "tests_run": facts.get("tests", 0), "tests_sandbox_errors": facts.get("sandbox_errors", 0),
        "open_prs": facts.get("open_prs", 0), "open_pr_note": facts.get("open_pr_note", ""),
        "ledger_total": len(ledger), "ledger_by_hand": classes.count("Verified by hand"), "ledger_partly": classes.count("Partly verified"),
        "ledger_not": classes.count("Not hand-verified"),
        "plans_total": len(plans), "plans_planned": count(plans, "status", "planned"), "plans_abandoned": count(plans, "status", "abandoned"),
        "plans_in_progress": count(plans, "status", "in progress"), "plans_done": count(plans, "status", "done"),
        **live,
        "tasks_open": len(open_tasks), "tasks_waiting_on_owner": sum(1 for t in open_tasks if t["status"] in ("Waiting on you", "Decision needed")),
    }
    write("summary.json", [summary])
    write("work_items.json", [{"id": t["id"], "stream": t["stream"], "who": t["who"], "priority": t["priority"], "size": t["size"], "status": t["status"],
                               "task": t["task"][:150]} for t in open_tasks])
    write("activity.json", read_activity(repo))
    for name in ("hand_tests.json", "defects.json"):
        write(name, json.loads((repo / "docs" / "dashboard_data" / name).read_text(encoding="utf-8")))
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", required=True)
    parser.add_argument("--run-tests", action="store_true")
    parser.add_argument("--tests", type=int)
    parser.add_argument("--sandbox-errors", type=int)
    parser.add_argument("--open-prs", type=int, default=0)
    parser.add_argument("--open-pr-note", default="")
    parser.add_argument("--release")
    args = parser.parse_args(argv)
    facts = {"open_prs": args.open_prs, "open_pr_note": args.open_pr_note}
    if args.release:
        facts["release"] = args.release
    if args.run_tests:
        facts["tests"], facts["sandbox_errors"] = run_tests(REPO)
    else:
        facts["tests"], facts["sandbox_errors"] = args.tests or 0, args.sandbox_errors or 0
    summary = build(args.out, REPO, facts)
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
