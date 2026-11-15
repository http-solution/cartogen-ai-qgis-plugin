#!/usr/bin/env python3
"""What a live run showed per feature, and which of those features a later change has touched (PLAN-057).

    python tools/live_results.py            validate docs/LIVE_RESULTS.json and print the counts
    python tools/live_results.py --gate     also list features recorded working/partly whose source files changed since the live run (exit 1 if any)

docs/LIVE_RESULTS.json records only what a live run saw (an agent or a person driving QGIS); a feature not in it has not been seen live. The gate is the
regression guarantee for stable releases and big changes: a feature seen working live whose source files then change must be rechecked live (a rerun
of its row) and stamped with `rechecked_at` = the commit it was rechecked on, or the release check fails."""
import argparse
import ast
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


def needs_recheck(doc, features, changed, head=None, deps=None):
    """Ids recorded working/partly whose source files (or, when `deps` is given, the files they import directly) are in `changed` and that have not
    been rechecked on this head. Pure."""
    out = []
    for f in features:
        entry = doc.get("features", {}).get(f["id"])
        if not entry or entry.get("status") not in ("working", "partly"):
            continue
        if not changed & ((deps or {}).get(f["id"]) or set(f.get("sources", []))):
            continue
        if head and entry.get("rechecked_at") == head:
            continue
        out.append(f["id"])
    return out


class BaselineMissingError(Exception):
    """The commit the live run was made on is not in this clone (a shallow CI checkout), so 'what changed since' cannot be answered."""


def _module_file(root, dotted):
    base = Path(root) / "src" / Path(*dotted.split("."))
    for candidate in (base.with_suffix(".py"), base / "__init__.py"):
        if candidate.is_file():
            return candidate.relative_to(root).as_posix()
    return None


def imports_of(path, root):
    """Repository-relative paths of the cartogen_ai modules `path` imports directly (absolute or relative; not what those import in turn). Pure given the files."""
    file = Path(root) / path
    parts = list(file.relative_to(Path(root) / "src").with_suffix("").parts)
    package = parts[:-1]                      # for an __init__.py the file IS the package, so the same slice holds
    found = set()
    for node in ast.walk(ast.parse(file.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = package[:len(package) - (node.level - 1)] if node.level else []
            module = ".".join([*base, *([node.module] if node.module else [])])
            submodules = [m for m in (_module_file(root, f"{module}.{a.name}") for a in node.names) if m]
            names = [] if submodules else [module]               # `from pkg import name` is the name's module when it is one, else the package itself
            found.update(submodules)
        else:
            continue
        found.update(m for m in (_module_file(root, n) for n in names if n.startswith("cartogen_ai")) if m)
    return found


def dependencies(features, root=ROOT):
    """{feature id: its source files plus the modules those sources import directly}. One level only: transitive reach would flag most of the ledger for
    any change to a shared helper (115 of 152 features for net.py), which is noise; direct reach flags 21. Pure given the files."""
    out = {}
    for f in features:
        deps = set(f.get("sources", []))
        for source in f.get("sources", []):
            if source.startswith("src/") and source.endswith(".py") and (Path(root) / source).is_file():
                deps |= imports_of(source, root)
        out[f["id"]] = deps
    return out


def _run_git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=False)  # noqa: S603, S607 -- fixed argv


def changed_since(baseline, fetch=True):
    """Files changed between the baseline commit and HEAD. Raises BaselineMissingError (never returns a guess) if the baseline is not in this clone and cannot be fetched."""
    if _run_git("cat-file", "-e", f"{baseline}^{{commit}}").returncode != 0:
        if fetch:
            _run_git("fetch", "--quiet", "origin", baseline)
        if _run_git("cat-file", "-e", f"{baseline}^{{commit}}").returncode != 0:
            raise BaselineMissingError(f"baseline commit {baseline[:9]} is not in this clone; fetch full history (git fetch --unshallow) and rerun")
    out = _run_git("diff", "--name-only", f"{baseline}...HEAD")
    if out.returncode != 0:
        raise BaselineMissingError(f"git diff from baseline {baseline[:9]} failed (a shallow clone has no merge base; run git fetch --unshallow): {out.stderr.strip()[:160]}")
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
        try:
            changed = changed_since(run["baseline_commit"])
        except BaselineMissingError as exc:
            print("cannot check the gate:", exc)
            return 2
        hit = needs_recheck(doc, feats, changed, head_sha(), dependencies(feats))
        print(f"{len(hit)} feature(s) seen working/partly live have changed sources since {run['baseline_commit'][:9]} and need a live recheck:")
        for fid in hit:
            print("  -", fid, "(", doc["features"][fid]["rows"], ")")
        code = code or (1 if hit else 0)
    return code


if __name__ == "__main__":
    sys.exit(main())
