"""Pick the smallest hand-test list that still covers what changed since the last tested release.

Why: the rc46 hand test re-ran ~245 algorithm rows whose code had not changed since rc45 passed them, and every live row costs model
calls (about 24k tokens of system prompt and tool schemas each, plus chat history). A row is worth running live only when code it
depends on changed; everything else keeps its previous verdict. The free offline gates (full unit suite, router/task replay of every
prompt) run on every change regardless.

Usage:
  python tools/plan_hand_test.py --base cartogen-ai-v1.17.0-rc46 [--previous 3_RESULTS_tools.csv] [--out delta.csv]

Rules (conservative, so a skipped row is never one that could have regressed):
  * a tools/*.py file changed          -> every tool registered in it is re-run;
  * a shared file changed (router, task matcher, orchestrator, prompts, providers, registry, transactions, UI) -> the CANARY rows run,
    because shared code can break any tool; the offline replay already covers routing for all rows;
  * nothing under src/ changed         -> nothing runs live.
Rows with a Pass in --previous and no dependency change are listed as "carried forward", not run.
"""
import argparse
import csv
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = "src/cartogen_ai/core/agent/tools/"
SHARED = ("src/cartogen_ai/core/services/", "src/cartogen_ai/core/agent/agent_orchestrator.py", "src/cartogen_ai/core/agent/task_matcher.py",
          "src/cartogen_ai/core/agent/tools/registry.py", "src/cartogen_ai/core/agent/prompts", "src/cartogen_ai/infrastructure/",
          "src/cartogen_ai/core/models/", "src/cartogen_ai/core/ui/", "src/cartogen_ai/core/agent/tool_dispatcher.py")
# One cheap, representative row per layer of the stack: if shared code broke something these are the rows that notice.
CANARY = ("add_vector_layer", "get_layers", "set_project_crs", "apply_categorized_style", "undo_last_operation", "create_print_layout",
          "run_allowlisted_processing_algorithm", "calculate_service_area")
_REGISTER = re.compile(r"@register_tool\(\s*[\"']([a-z0-9_]+)[\"']")


def changed_files(base):
    out = subprocess.run(["git", "diff", "--name-only", f"{base}..HEAD", "--", "src"], cwd=ROOT, capture_output=True, text=True, check=True)  # noqa: S603, S607 -- fixed argv, base ref is the developer's own
    return [line for line in out.stdout.splitlines() if line.endswith(".py")]


def tools_in(path):
    try:
        return set(_REGISTER.findall((ROOT / path).read_text(encoding="utf-8")))
    except FileNotFoundError:  # deleted file: its tools are gone, nothing to run
        return set()


def plan(files):
    rerun, shared = set(), False
    for f in files:
        if f.startswith(SHARED):
            shared = True
        if f.startswith(TOOLS_DIR):
            rerun |= tools_in(f)
    return rerun, shared


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", required=True, help="git ref of the last release that was hand-tested")
    ap.add_argument("--sheet", default=str(ROOT / "docs" / "HAND_TEST_rc44_tools.csv"))
    ap.add_argument("--previous", help="the tester's filled-in results CSV from the last run (verdicts are carried forward)")
    ap.add_argument("--target", default="", help="comma list of tools a fix this release was aimed at (routing/task fixes live outside the tool files)")
    ap.add_argument("--out", help="write the rows to run live to this CSV")
    args = ap.parse_args()

    files = changed_files(args.base)
    rerun, shared = plan(files)
    rerun |= {t for t in args.target.split(",") if t}
    if shared:
        rerun |= set(CANARY)
    previous = {}
    if args.previous:
        with open(args.previous, encoding="utf-8-sig") as fh:
            for row in csv.DictReader(fh):
                previous[row["tool"].split(" ")[0]] = row["result (Pass/Partial/Fail/Skip)"].strip()
    with open(args.sheet, encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        header = reader.fieldnames
        rows = list(reader)

    run, carried, retry = [], [], []
    for row in rows:
        tool = row["tool"].split(" ")[0]
        verdict = previous.get(tool, "")
        if tool in rerun:
            run.append(row)
        elif verdict in ("Fail", "Partial"):
            retry.append(row)  # not passing last time and not changed: only worth re-running if a fix targeted it, so list it, don't run
        else:
            carried.append(row)
    print(f"{len(files)} source files changed since {args.base}; shared code touched: {shared}")
    print(f"RUN LIVE ({len(run)}): " + ", ".join(r["tool"].split(" ")[0] for r in run))
    print(f"UNCHANGED BUT NOT PASSING LAST TIME ({len(retry)}), run only if a fix targeted them: " + ", ".join(r["tool"].split(" ")[0] for r in retry))
    print(f"CARRIED FORWARD ({len(carried)}): no dependency changed")
    if args.out:
        with open(args.out, "w", newline="", encoding="utf-8-sig") as fh:
            writer = csv.DictWriter(fh, fieldnames=header)
            writer.writeheader()
            writer.writerows(run)
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
