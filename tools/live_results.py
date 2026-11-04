#!/usr/bin/env python3
"""What a live run showed per feature, and which of those features a later change has touched (PLAN-057).

    python tools/live_results.py            validate docs/LIVE_RESULTS.json and print the counts
    python tools/live_results.py --gate     also list features recorded working/partly whose source files changed since the live run (exit 1 if any)

docs/LIVE_RESULTS.json records only what a live run saw (an agent or a person driving QGIS); a feature not in it has not been seen live. The gate is the
regression guarantee for stable releases and big changes: a feature seen working live whose source files then change must be rechecked live (a rerun
of its row) and stamped with `rechecked_at` = the commit it was rechecked on, or the release check fails."""
import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "docs" / "LIVE_RESULTS.json"
STATUSES = ("working", "partly", "failing")


def load():
    return json.loads(RESULTS.read_text(encoding="utf-8"))


def ledger():
    return json.loads((ROOT / "docs" / "FEATURE_LEDGER.json").read_text(encoding="utf-8"))["features"]


def row_ids():
    sys.path.insert(0, str(ROOT / "tools"))
    import build_full_smoke
    return {row["id"] for row in build_full_smoke.all_rows()}


def not_testable():
    sys.path.insert(0, str(ROOT / "tools"))
    import build_full_smoke
    return set(build_full_smoke.load()["not_hand_testable"])


def problems(doc, features, rows, nht):
    """[sentence] for every way the record can be wrong. Pure."""
    by_id = {f["id"]: f for f in features}
    out = []
    if not doc.get("runs"):
        out.append("no run is recorded")
    for run_id, run in doc.get("runs", {}).items():
        if not run.get("baseline_commit"):
            out.append(f"run {run_id}: no baseline_commit (the gate needs it)")
    for fid, entry in doc.get("features", {}).items():
        if fid not in by_id:
            out.append(f"{fid}: not a ledger entry")
            continue
        if entry.get("status") not in STATUSES:
            out.append(f"{fid}: status {entry.get('status')!r} is not one of {STATUSES}")
        if not str(entry.get("note", "")).strip():
            out.append(f"{fid}: no note saying what was seen")
        out.extend(f"{fid}: row {token} is not a smoke row" for token in str(entry.get("rows", "")).split() if token not in rows)
        if fid in nht:
            out.append(f"{fid}: a person cannot test it, so a live run cannot have seen it")
        if entry.get("status") == "working" and not by_id[fid].get("guards"):
            out.append(f"{fid}: recorded working but has no automated guard to keep it working")
    return out


def summary(doc, features, nht):
    feats = doc.get("features", {})
    counts = {s: sum(1 for e in feats.values() if e.get("status") == s) for s in STATUSES}
    testable = len(features) - len(nht)
    return {"ledger": len(features), "not_testable": len(nht), "testable": testable, **counts,
            "not_tested": testable - sum(counts.values())}


def needs_recheck(doc, features, changed, head=None):
    """Ids recorded working/partly whose source files are in `changed` and that have not been rechecked on this head. Pure."""
    out = []
    for f in features:
        entry = doc.get("features", {}).get(f["id"])
        if not entry or entry.get("status") not in ("working", "partly"):
            continue
        if not changed & set(f.get("sources", [])):
            continue
        if head and entry.get("rechecked_at") == head:
            continue
        out.append(f["id"])
    return out


def changed_since(baseline):
    out = subprocess.run(["git", "diff", "--name-only", f"{baseline}...HEAD"], cwd=ROOT, capture_output=True, text=True, check=True)  # noqa: S603, S607 -- fixed argv
    return set(out.stdout.split())


def head_sha():
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()  # noqa: S607 -- fixed argv


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--gate", action="store_true")
    args = ap.parse_args()
    doc, feats = load(), ledger()
    bad = problems(doc, feats, row_ids(), not_testable())
    for line in bad:
        print("PROBLEM:", line)
    s = summary(doc, feats, not_testable())
    print(f"testable {s['testable']} of {s['ledger']}: working {s['working']}, partly {s['partly']}, failing {s['failing']}, not seen live {s['not_tested']}")
    code = 1 if bad else 0
    if args.gate:
        run = next(iter(doc["runs"].values()))
        hit = needs_recheck(doc, feats, changed_since(run["baseline_commit"]), head_sha())
        print(f"{len(hit)} feature(s) seen working/partly live have changed sources since {run['baseline_commit'][:9]} and need a live recheck:")
        for fid in hit:
            print("  -", fid, "(", doc["features"][fid]["rows"], ")")
        code = code or (1 if hit else 0)
    return code


if __name__ == "__main__":
    sys.exit(main())
