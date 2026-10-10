#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Reads the model-call trace the plugin writes when "Record every model request and reply" is on (Settings) and prints one row per
request plus plain-language flags (a request with many calls, an identical tool call repeated, a system instruction that changed inside
one request, a failed call).

    python tools/summarize_api_trace.py <folder-or-file> [--loop-threshold 6] [--show-turn TURN_ID]

<folder> is the 'cartogen_api_trace' folder next to the project (or in the QGIS profile folder for an unsaved project). The trace holds raw
prompts and replies; this summary does not print message text except with --show-turn, which prints the calls of one request in order
(message roles, tool calls and a short preview). Check the output before you paste it anywhere."""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from cartogen_ai.core.agent.api_trace import read_records, summarize  # noqa: E402


def _short(text, n=100):
    text = " ".join(str(text or "").split())
    return text if len(text) <= n else text[:n] + "..."


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("path")
    parser.add_argument("--loop-threshold", type=int, default=6)
    parser.add_argument("--show-turn", help="print the calls of this turn_id in order")
    args = parser.parse_args()
    records = read_records(args.path)
    if not records:
        sys.exit("No model calls found. Is the setting on, and is this the cartogen_api_trace folder?")
    rows, flags = summarize(records, args.loop_threshold)
    print(f"{len(records)} model calls in {len(rows)} request(s)\n")
    print(f"{'turn':>10} {'calls':>5} {'in_tok':>8} {'cached':>7} {'out_tok':>7} {'sys_chars':>9} {'tools':>5}  tools called")
    for r in rows:
        print(f"{str(r['turn_id']):>10} {r['calls']:>5} {r['input_tokens']:>8} {r['cached_tokens']:>7} {r['output_tokens']:>7} "
              f"{r['system_chars']:>9} {r['tools_offered']:>5}  {', '.join(str(n) for n in r['tools_called'][:10]) or '-'}")
    print("\nFlags:" if flags else "\nNo flags.")
    for f in flags:
        print(" -", f)
    if args.show_turn:
        print(f"\nCalls of turn {args.show_turn}:")
        for c in sorted((c for c in records if str(c.get('turn_id')) == args.show_turn), key=lambda c: c.get("call_index") or 0):
            resp = c.get("response") or {}
            print(f"\n[call {c.get('call_index')}] {c.get('model')} {c.get('outcome')} {c.get('latency_ms')} ms usage={c.get('usage')}")
            print("  sent:", [f"{m.get('role')}:{_short(m.get('content') or [t.get('name') for t in m.get('tool_calls') or []], 70)}"
                              for m in (c.get("messages") or [])][-4:])
            print("  tools offered:", (c.get("tools") or {}).get("count"))
            print("  reply:", _short(resp.get("content")), "| tool calls:", [t.get("name") for t in resp.get("tool_calls") or []])
            if c.get("error"):
                print("  error:", _short(c["error"], 200))


if __name__ == "__main__":
    main()
