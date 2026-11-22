#!/usr/bin/env python3
"""Tool calls, first tool and tokens for every request in a saved run: the measurement master-list row LR-24 still needs.

    python tools/request_costs.py RESULTS_FOLDER [--out request_costs.md]

Why: the 2026-11-20 live run asked for 12 routing requests (card C26) and a chart (C16), but the project was never saved, so the plugin wrote no
evidence and nothing could be counted. With a SAVED project and "Save an evidence folder for each request" on, every request leaves a folder
cartogen_evidence/<stamp>/ with steps.jsonl (each tool call, in order) and summary.md (the request text and, when the model reported it, a usage line
with the tokens). This reads every such folder under RESULTS_FOLDER at any depth and prints one row per request: its calls, the FIRST tool called,
the tokens, and a verdict against two kinds of target.

The targets are TARGETS, not measurements (LR-24 chose them; no live run has produced a number yet):
  - a request that matches a row of tests/fixtures/routing_requests.json should call one of that row's tools FIRST (the C26 routing requests);
  - a chart request should take at most CHART_CALL_BUDGET calls (the C16 chart took 22 before chart_field_by_category existed).
Everything else is only listed, never judged. Standard library only; reads files, writes one markdown file."""
import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
# In the test package the routing rows sit next to this script (build_computer_use.py copies them); in the repository they are a test fixture.
ROUTING_ROWS = next((p for p in (Path(__file__).resolve().parent / "routing_requests.json", REPO / "tests" / "fixtures" / "routing_requests.json")
                     if p.is_file()), REPO / "tests" / "fixtures" / "routing_requests.json")
CHART_CALL_BUDGET = 3
CHART_WORDS = re.compile(r"\b(bar chart|pie chart|line chart|histogram|chart|plot|graph)\b", re.I)
_USAGE = re.compile(r"(?P<calls>[\d,]+) calls?, (?P<inp>[\d,]+) input \((?P<cached>[\d,]+) cached\) \+ (?P<out>[\d,]+) output tokens")


def _number(text):
    return int(str(text).replace(",", ""))


def parse_usage(text):
    """{calls, input_tokens, cached_tokens, output_tokens} from a 'This turn: ...' usage line, or {} when there is none. Pure."""
    match = _USAGE.search(text or "")
    if not match:
        return {}
    return {"model_calls": _number(match["calls"]), "input_tokens": _number(match["inp"]), "cached_tokens": _number(match["cached"]),
            "output_tokens": _number(match["out"])}


def parse_summary(text):
    """(request text, usage dict) from a summary.md the plugin wrote. Pure."""
    request = ""
    match = re.search(r"## Request\s*\n+(.*?)\n+## ", text or "", re.S)
    if match:
        request = match.group(1).strip()
    usage = ""
    match = re.search(r"## Usage\s*\n+(.*?)\n+## ", text or "", re.S)
    if match:
        usage = match.group(1).strip()
    return request, parse_usage(usage)


def tool_names(steps_text):
    """The tool names in a steps.jsonl, in call order; lines that are not JSON are skipped. Pure."""
    names = []
    for line in (steps_text or "").splitlines():
        try:
            tool = json.loads(line).get("tool")
        except (ValueError, AttributeError):
            continue
        if tool:
            names.append(tool)
    return names


def _norm(text):
    return re.sub(r"\s+", " ", re.sub(r"^[A-Za-z ]{2,30}:\s+", "", str(text or ""))).strip().lower().rstrip(".?!")


def expected_first_tools(request, routing_rows):
    """The tools a routing row says this request should be offered (any one of them is fine as the first call), or None when no row matches. A row
    matches when its prompt, without a leading 'Public health:' style label, is the request or is contained in it. Pure."""
    wanted = _norm(request)
    for row in routing_rows:
        prompt = _norm(row["prompt"])
        if prompt and (prompt == wanted or prompt in wanted):
            options = []
            for need in row["tools"]:
                options += list(need) if isinstance(need, list) else [need]
            return options
    return None


def judge(request, tools, routing_rows):
    """(verdict, reason). 'ok', 'over target' or 'not judged'. Pure."""
    expected = expected_first_tools(request, routing_rows)
    if expected is not None:
        if not tools:
            return "over target", f"no tool was called; expected one of {', '.join(expected)} first"
        if tools[0] not in expected:
            return "over target", f"first tool was {tools[0]}; expected one of {', '.join(expected)}"
        return "ok", f"first tool {tools[0]} is one the routing row accepts"
    if CHART_WORDS.search(request or ""):
        if len(tools) > CHART_CALL_BUDGET:
            return "over target", f"{len(tools)} tool calls for a chart request; the target is {CHART_CALL_BUDGET} or fewer"
        return "ok", f"{len(tools)} tool call(s) for a chart request (target {CHART_CALL_BUDGET} or fewer)"
    return "not judged", "no routing row and not a chart request"


def read_requests(root):
    """One dict per request folder (a folder holding steps.jsonl) anywhere under `root`, oldest first by folder name. Pure apart from reads."""
    rows = []
    for steps in sorted(Path(root).rglob("steps.jsonl")):
        folder = steps.parent
        summary = folder / "summary.md"
        request, usage = parse_summary(summary.read_text(encoding="utf-8", errors="replace")) if summary.is_file() else ("", {})
        tools = tool_names(steps.read_text(encoding="utf-8", errors="replace"))
        rows.append({"folder": str(folder), "stamp": folder.name, "request": request, "tools": tools, "usage": usage})
    return rows


def build_report(rows, routing_rows):
    """The markdown report. Pure."""
    lines = ["# Tool calls and tokens per request", "",
             "Targets are TARGETS chosen for master-list row LR-24, not measurements. 'not judged' means no target applies.", "",
             "| # | request | tool calls | first tool | model calls | input tokens | output tokens | verdict |", "|---|---|---|---|---|---|---|---|"]
    over = 0
    for i, row in enumerate(rows, 1):
        verdict, reason = judge(row["request"], row["tools"], routing_rows)
        over += verdict == "over target"
        usage = row["usage"]
        text = row["request"].replace("|", "/")[:70]
        lines.append(f"| {i} | {text} | {len(row['tools'])} | {row['tools'][0] if row['tools'] else '-'} | {usage.get('model_calls', '')} | "
                     f"{usage.get('input_tokens', '')} | {usage.get('output_tokens', '')} | {verdict}: {reason} |")
    if not rows:
        lines.append("| - | no evidence folder found: save the project first, tick 'Save an evidence folder for each request', run again | | | | | | |")
    counts = sorted(len(r["tools"]) for r in rows)
    lines += ["", f"{len(rows)} request(s); {over} over target." + (f" Tool calls per request: min {counts[0]}, median {counts[len(counts) // 2]}, max {counts[-1]}." if counts else "")]
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("results")
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)
    routing = json.loads(ROUTING_ROWS.read_text(encoding="utf-8")) if ROUTING_ROWS.is_file() else []
    report = build_report(read_requests(args.results), routing)
    if args.out:
        Path(args.out).write_text(report, encoding="utf-8")
    sys.stdout.write(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
