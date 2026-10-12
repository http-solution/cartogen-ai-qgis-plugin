#!/usr/bin/env python3
"""Sets up and checks a full live-test run of the plugin. Standard library only; run it with any Python 3.10+ (not inside QGIS).

    python tools/live_test_pack.py prepare  C:/Cartogen-AI-Smoke/rc34
    python tools/live_test_pack.py check    C:/Cartogen-AI-Smoke/rc34 [--strict]

`prepare` makes the TEST_ROOT folder tree (inputs, outputs, screenshots, logs, results), copies the synthetic fixtures from
docs/release_smoke_assets/inputs after checking each file against docs/FULL_LIVE_TEST_rc34_INPUTS.sha256, copies the row list to
results/results.csv (the file you fill in) and writes results/prompts_filled.csv, the same prompts with {TEST_ROOT} replaced by the
absolute path, ready to paste. It refuses a folder that already has files unless you pass --force.

`check` reads results/results.csv after (or during) a run and reports: how many rows have each result, which rows have a result but no
screenshot, which output files a PASS row promised and whether they exist, files that must be absent (the sandbox row), rows that took
more than 4 model calls, and which input files the run changed. It writes results/summary.md. With --strict it exits 1 if any row has a
result without evidence. It never edits results.csv.

See docs/FULL_LIVE_TEST_rc34.md for the full procedure."""
import argparse
import csv
import hashlib
import shutil
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
INPUTS = REPO / "docs" / "release_smoke_assets" / "inputs"
ROWS = REPO / "docs" / "FULL_LIVE_TEST_rc34_ROWS.csv"
ROWS_EXTRA = REPO / "docs" / "FULL_LIVE_TEST_rc37_ROWS.csv"     # rows for what changed after rc34; added to the run when present
MANIFEST = REPO / "docs" / "FULL_LIVE_TEST_rc34_INPUTS.sha256"
SUBFOLDERS = ("inputs", "outputs", "screenshots", "logs", "results")
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp")
DECIDED = ("PASS", "PASS (DEGRADED)", "FAIL", "INCONCLUSIVE")        # rows that claim to have been run and need evidence
KNOWN = (*DECIDED, "NOT RUN", "SKIP", "")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_manifest():
    out = {}
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        if line.strip():
            digest, name = line.split(None, 1)
            out[name.strip().lstrip("*")] = digest
    return out


def read_rows(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_rows(path, rows, fields):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def prepare(root, force=False):
    root = Path(root).expanduser().resolve()
    if root.exists() and any(root.iterdir()) and not force:
        print(f"{root} already has files. Use an empty folder, or --force to add to it.", file=sys.stderr)
        return 2
    manifest = read_manifest()
    bad = []
    for name, digest in manifest.items():
        src = INPUTS / name
        if not src.is_file() or sha256(src) != digest:
            bad.append(name)
    if bad:
        print("These fixture files in the repository do not match docs/FULL_LIVE_TEST_rc34_INPUTS.sha256, so the run would not be on "
              "the documented data: " + ", ".join(bad), file=sys.stderr)
        return 2
    for sub in SUBFOLDERS:
        (root / sub).mkdir(parents=True, exist_ok=True)
    for name in manifest:
        shutil.copy2(INPUTS / name, root / "inputs" / name)
    rows = read_rows(ROWS) + (read_rows(ROWS_EXTRA) if ROWS_EXTRA.is_file() else [])
    fields = list(rows[0].keys())
    write_rows(root / "results" / "results.csv", rows, fields)
    filled = [dict(r, prompt_or_action=r["prompt_or_action"].replace("{TEST_ROOT}", root.as_posix())) for r in rows]
    write_rows(root / "results" / "prompts_filled.csv", filled, fields)
    (root / "README_FIRST.txt").write_text(
        "TEST_ROOT = " + root.as_posix() + "\n\n"
        "inputs/       the synthetic fixtures. Open inputs/smoke_start.qgz in QGIS. Never use the copy in the repository.\n"
        "outputs/      files the rows write (the row list says which). Never write inside the installed plugin folder.\n"
        "screenshots/  one or more images per row, named <row id>.png or <row id>_<what>.png (for example N3_card.png).\n"
        "logs/         the exported QGIS Log Messages, and api_trace_summary.txt if you recorded the API trace.\n"
        "results/      results.csv is the file you fill in (the result column: PASS, FAIL, NOT RUN, SKIP, INCONCLUSIVE or "
        "PASS (degraded)); prompts_filled.csv has every prompt with the real paths.\n\n"
        "Procedure: docs/LIVE_TEST_rc37_START_HERE.md (rc37 rows, RC37-*) and docs/FULL_LIVE_TEST_rc34.md (everything else) in the repository. When you are done, or at any time: "
        "python tools/live_test_pack.py check " + root.as_posix() + "\n", encoding="utf-8")
    print(f"Prepared {root}\n  inputs copied and verified: {len(manifest)} files\n  rows: {len(rows)} (results/results.csv)")
    return 0


def find_output(root, name):
    """Where a promised output file ended up: first TEST_ROOT/outputs, then anywhere under TEST_ROOT (a relative path in a prompt lands
    next to the project, which is the inputs folder here)."""
    direct = root / name
    if direct.is_file():
        return direct
    base = Path(name).name
    hits = [p for p in root.rglob(base) if p.is_file()]
    return hits[0] if hits else None


def check(root, strict=False):
    root = Path(root).expanduser().resolve()
    results = root / "results" / "results.csv"
    if not results.is_file():
        print(f"No {results}. Run prepare first.", file=sys.stderr)
        return 2
    rows = read_rows(results)
    shots_dir = root / "screenshots"
    shots = [p.name for p in shots_dir.iterdir()] if shots_dir.is_dir() else []

    def screenshots_for(rid):
        stem = rid.lower()
        return [n for n in shots if n.lower().endswith(IMAGE_SUFFIXES) and (n.lower().rsplit(".", 1)[0] == stem or n.lower().startswith(stem + "_"))]

    counts = Counter()
    unknown, no_shot, missing_out, present_but_forbidden, many_calls, failed = [], [], [], [], [], []
    by_group = {}
    for r in rows:
        res = (r.get("result") or "").strip().upper()
        counts[res or "(blank)"] += 1
        g = by_group.setdefault(r["group"].split(":")[0], Counter())
        g[res or "(blank)"] += 1
        if res not in KNOWN:
            unknown.append((r["id"], r.get("result")))
        if res == "FAIL":
            failed.append(r["id"])
        if res in DECIDED and not screenshots_for(r["id"]):
            no_shot.append(r["id"])
        out = (r.get("expected_output_file") or "").strip()
        if out.startswith("ABSENT:"):
            name = out.split(":", 1)[1].split("(")[0].strip()
            if res in DECIDED and find_output(root, name):
                present_but_forbidden.append((r["id"], name))
        elif out and res in ("PASS", "PASS (DEGRADED)"):
            missing_out.extend((r["id"], name) for name in (o.strip() for o in out.split(";") if o.strip()) if not find_output(root, name))
        calls = (r.get("model_calls") or "").strip()
        if calls.isdigit() and int(calls) > 4 and res in ("PASS", "PASS (DEGRADED)"):
            many_calls.append((r["id"], int(calls)))
    manifest = read_manifest()
    changed = []
    for name, digest in manifest.items():
        p = root / "inputs" / name
        if not p.is_file():
            changed.append(f"{name} (missing)")
        elif sha256(p) != digest:
            changed.append(name)

    lines = ["# Live test summary", "", f"TEST_ROOT: {root.as_posix()}", f"Rows: {len(rows)}", ""]
    lines += ["## Results", "", "| Result | Rows |", "|---|---:|"] + [f"| {k} | {v} |" for k, v in sorted(counts.items())]
    lines += ["", "## By group", "", "| Group | PASS | FAIL | NOT RUN / SKIP | other / blank |", "|---|---:|---:|---:|---:|"]
    for g, c in by_group.items():
        passed = c["PASS"] + c["PASS (DEGRADED)"]
        notrun = c["NOT RUN"] + c["SKIP"]
        other = sum(c.values()) - passed - c["FAIL"] - notrun
        lines.append(f"| {g} | {passed} | {c['FAIL']} | {notrun} | {other} |")

    def section(title, items, fmt):
        lines.extend(["", f"## {title}", ""] + ([f"- {fmt(i)}" for i in items] if items else ["- none"]))

    section("FAIL rows", failed, str)
    section("Rows with a result but no screenshot (need <row id>.png or <row id>_<what>.png in screenshots/)", no_shot, str)
    section("PASS rows whose promised output file was not found", missing_out, lambda t: f"{t[0]}: {t[1]}")
    section("Files that must NOT exist but do", present_but_forbidden, lambda t: f"{t[0]}: {t[1]}")
    section("PASS rows that took more than 4 model calls (a finding, not a pass with a footnote)", many_calls, lambda t: f"{t[0]}: {t[1]} calls")
    section("Unrecognised result values", unknown, lambda t: f"{t[0]}: {t[1]!r}")
    section("Input files changed by the run (expected for the project and the GeoPackage once rows write to them)", changed, str)
    (root / "results" / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    problems = bool(no_shot or missing_out or present_but_forbidden or unknown)
    return 1 if (strict and problems) else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare", help="create TEST_ROOT and copy the fixtures and the row list")
    p.add_argument("root")
    p.add_argument("--force", action="store_true", help="use a folder that already has files")
    c = sub.add_parser("check", help="summarise results and verify evidence")
    c.add_argument("root")
    c.add_argument("--strict", action="store_true", help="exit 1 when a decided row has no screenshot or a promised file is missing")
    args = ap.parse_args(argv)
    return prepare(args.root, args.force) if args.cmd == "prepare" else check(args.root, args.strict)


if __name__ == "__main__":
    sys.exit(main())
