#!/usr/bin/env python3
"""Before you push: which finished features does this change touch, and which guard tests protect them?

    python tools/ledger_guard.py [--base origin/main]

Reads docs/FEATURE_LEDGER.json, lists the features whose source files differ from the base, and runs exactly their guard tests. Exit 1 if a guard
fails. A change that touches a ledger feature and does not keep its guard green is the way finished work gets broken again; this makes that visible
before CI does. Features with a live-QGIS guard are run in CI only (listed, not run here)."""
import argparse
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def changed_files(base):
    out = subprocess.run(["git", "diff", "--name-only", f"{base}...HEAD"], cwd=ROOT, capture_output=True, text=True, check=True)  # noqa: S603, S607 -- fixed argv
    working = subprocess.run(["git", "diff", "--name-only"], cwd=ROOT, capture_output=True, text=True, check=True)  # noqa: S607 -- fixed argv
    return set(out.stdout.split()) | set(working.stdout.split())


def touched(features, files):
    return [f for f in features if files & set(f["sources"])]


def dotted(reference):
    path, *names = reference.split("::")
    return ".".join([path[:-3].replace("/", "."), *names])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default="origin/main")
    args = ap.parse_args()
    features = json.loads((ROOT / "docs" / "FEATURE_LEDGER.json").read_text(encoding="utf-8"))["features"]
    hit = touched(features, changed_files(args.base))
    if not hit:
        print("no ledger feature touched by this change")
        return 0
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "src"))
    names, live = [], []
    for feature in hit:
        print(f"- {feature['id']}: {feature['feature']}")
        for guard in feature["guards"]:
            (live if guard.endswith("_live.py") or "_live.py::" in guard else names).append(dotted(guard))
    suite = unittest.TestSuite()
    for name in sorted(set(names)):
        suite.addTests(unittest.defaultTestLoader.loadTestsFromName(name))
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    if live:
        print("run in CI only (live QGIS): " + ", ".join(sorted(set(live))))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
