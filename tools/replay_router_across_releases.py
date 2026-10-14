#!/usr/bin/env python3
"""Replays plain requests against every release commit and reports tools that an earlier release offered and a later one does not.

    python tools/replay_router_across_releases.py [--prompts FILE.json] [--limit N]

Uses git worktrees in a temp folder (the working tree is untouched). Needs only git and Python. This is how the rc23 router regression
(generic words discounted for every request) was found on 2026-10-14; see docs/ROUTER_REGRESSION_AUDIT_2026-10-14.md. Run it before a
release that touches core/services/tool_router.py or tool descriptions."""
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PROBE = r'''
import sys, json
sys.path.insert(0, '.'); sys.path.insert(0, 'src')
prompts = json.load(open(sys.argv[1]))
try:
    from cartogen_ai.core.agent.tools import TOOLS_SCHEMA
    from cartogen_ai.core.services.tool_router import ToolRouter
    r = ToolRouter(TOOLS_SCHEMA)
    print(json.dumps({q: sorted(t["function"]["name"] for t in r.filter_relevant_tools(q)) for q in prompts}))
except Exception as e:
    print(json.dumps({"__error__": str(e)[:200]}))
'''
DEFAULT_PROMPTS = ["create layer for Jordan ADM1", "zoom to the layer smoke_zones", "remove the layer smoke_zones", "export smoke_points to CSV",
                   "buffer smoke_points by 500 m", "add a point at 15.3694, 44.1910", "what layers are in this project"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompts")
    ap.add_argument("--limit", type=int, default=45)
    args = ap.parse_args()
    prompts = json.loads(Path(args.prompts).read_text(encoding="utf-8")) if args.prompts else DEFAULT_PROMPTS
    log = subprocess.run(["git", "log", "--format=%h", "-n", str(args.limit), "--", "metadata.txt"], cwd=REPO, capture_output=True, text=True).stdout.split()
    results = []
    with tempfile.TemporaryDirectory() as tmp:
        probe, plist = Path(tmp) / "probe.py", Path(tmp) / "prompts.json"
        probe.write_text(PROBE, encoding="utf-8")
        plist.write_text(json.dumps(prompts), encoding="utf-8")
        for h in log:
            wt = Path(tmp) / f"wt_{h}"
            subprocess.run(["git", "worktree", "add", "-q", "-f", str(wt), h], cwd=REPO, check=False)
            try:
                version = next((ln.split("=", 1)[1] for ln in (wt / "metadata.txt").read_text(encoding="utf-8").splitlines() if ln.startswith("version=")), h)
                out = subprocess.run([sys.executable, str(probe), str(plist)], cwd=wt, capture_output=True, text=True, timeout=300).stdout.strip().splitlines()
                results.append((version, json.loads(out[-1]) if out else {"__error__": "no output"}))
            finally:
                subprocess.run(["git", "worktree", "remove", "-f", str(wt)], cwd=REPO, check=False)
    results.reverse()                                   # oldest first
    good = [(v, r) for v, r in results if "__error__" not in r]
    latest_v, latest = good[-1]
    print(f"compared {len(good)} releases, newest {latest_v}")
    for q in prompts:
        ever = {t for _v, r in good[:-1] for t in r.get(q, [])}
        for t in sorted(ever - set(latest.get(q, []))):
            last = [v for v, r in good if t in r.get(q, [])][-1]
            print(f"  {q!r}: {t} was offered up to {last}, not in {latest_v}")


if __name__ == "__main__":
    main()
