"""PLAN-038 spike: run the Claude CLI bridge against your own logged-in `claude` and write down what happened.

Run on the machine where you use Claude Code (it must already be signed in):
    python tools/cli_bridge_spike.py [--model sonnet] [--exe claude] [--out spike_report.md]

It sends three tiny requests through the same code the plugin will use, with two fake tools, and records latency, whether a tool call
came back in the right shape, and whether the CLI tried to act on its own. It touches no QGIS project and no files besides the report.
Nothing here is verified until you have run it; attach the report to the PR or the master-list row SPIKE-1.
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
from cartogen_ai.infrastructure.providers import cli_bridge as cb

TOOLS = [
    {"type": "function", "function": {"name": "count_features", "description": "Count the features in a layer by name.",
     "parameters": {"type": "object", "properties": {"layer": {"type": "string"}}, "required": ["layer"]}}},
    {"type": "function", "function": {"name": "delete_layer", "description": "Delete a layer by name (destructive).",
     "parameters": {"type": "object", "properties": {"layer": {"type": "string"}}, "required": ["layer"]}}},
]
CASES = [
    ("plain answer", [{"role": "user", "content": "In one sentence, what is a coordinate reference system?"}], "final"),
    ("tool call", [{"role": "user", "content": "How many features are in the layer called roads?"}], "tool_calls"),
    ("uses a tool result", [{"role": "user", "content": "How many features are in roads?"},
                            {"role": "assistant", "content": None, "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "count_features", "arguments": '{"layer":"roads"}'}}]},
                            {"role": "tool", "tool_call_id": "c1", "content": '{"count": 412}'}], "final"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default="claude")
    ap.add_argument("--model", default=None)
    ap.add_argument("--out", default="spike_report.md")
    args = ap.parse_args()
    exe = cb.find_executable(args.exe)
    lines = ["# CLI bridge spike report (Claude Code)", "", f"- executable: {exe or 'NOT FOUND'}", f"- model flag: {args.model or '(CLI default)'}", ""]
    if not exe:
        lines.append("The claude executable was not found; nothing was run.")
    else:
        client = cb.ClaudeCliClient(executable=exe, model=args.model)
        lines += ["| case | seconds | expected | got | tokens (in/out) | note |", "|---|---|---|---|---|---|"]
        for name, messages, expect in CASES:
            t0 = time.monotonic()
            res = client.complete(messages, TOOLS)
            secs = time.monotonic() - t0
            if "error" in res:
                lines.append(f"| {name} | {secs:.1f} | {expect} | ERROR | - | {res['error']} |")
                continue
            msg = res["message"]
            got = "tool_calls" if msg.get("tool_calls") else "final"
            use = res.get("usage", {})
            note = ("estimated tokens" if use.get("estimated") else "tokens reported by the CLI")
            if name == "uses a tool result" and "412" not in (msg.get("content") or ""):
                note += "; answer did not use the tool result"
            lines.append(f"| {name} | {secs:.1f} | {expect} | {got}{' OK' if got == expect else ' MISMATCH'} | {use.get('input_tokens')}/{use.get('output_tokens')} | {note} |")
    lines += ["", "Also note by hand: did any file appear in the current folder, did the CLI ask for a permission, did it open a browser?"]
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
