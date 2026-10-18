"""Turn a Cartogen AI plugin log (QGIS Log Messages > CartogenAI, saved as text) into a cost table: one line per prompt.

A prompt starts at every `model_call call_index=0` line; its calls are the following lines up to the next index 0. Prints model calls,
input/cached/output tokens and the tool schemas offered for each prompt, then a total, so the cost of a test version is a number and
the most expensive rows are visible.

  python tools/summarize_usage_log.py cartogen.log [--csv usage.csv]
"""
import argparse
import csv
import re
import sys

_FIELD = re.compile(r"(\w+)=([^\s]*)")
_NUMERIC = ("call_index", "input_tokens", "cached_tokens", "output_tokens", "tool_count", "tool_calls", "latency_ms")


def parse(lines):
    """[{calls, input_tokens, cached_tokens, output_tokens, tool_count, model}] one dict per prompt, in log order."""
    turns, current = [], None
    for line in lines:
        at = line.find("model_call ")
        if at < 0:
            continue
        fields = dict(_FIELD.findall(line[at:]))
        index = int(fields.get("call_index", "0") or 0)
        if index == 0 or current is None:
            current = {"calls": 0, "input_tokens": 0, "cached_tokens": 0, "output_tokens": 0, "tool_count": 0, "model": fields.get("model", "")}
            turns.append(current)
        current["calls"] += 1
        for key in ("input_tokens", "cached_tokens", "output_tokens"):
            current[key] += int(fields.get(key, "0") or 0) if fields.get(key, "0").isdigit() else 0
        if index == 0 and fields.get("tool_count", "").isdigit():
            current["tool_count"] = int(fields["tool_count"])
    return turns


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("log")
    ap.add_argument("--csv")
    args = ap.parse_args()
    with open(args.log, encoding="utf-8", errors="replace") as fh:
        turns = parse(fh)
    print(f"{'#':>3} {'calls':>5} {'input':>9} {'cached':>9} {'output':>7} {'tools':>5}  model")
    for i, t in enumerate(turns, 1):
        print(f"{i:>3} {t['calls']:>5} {t['input_tokens']:>9} {t['cached_tokens']:>9} {t['output_tokens']:>7} {t['tool_count']:>5}  {t['model']}")
    total_in = sum(t["input_tokens"] for t in turns)
    print(f"{len(turns)} prompts, {sum(t['calls'] for t in turns)} model calls, {total_in} input tokens "
          f"({sum(t['cached_tokens'] for t in turns)} cached), {sum(t['output_tokens'] for t in turns)} output tokens")
    if turns:
        worst = sorted(range(len(turns)), key=lambda i: -turns[i]["input_tokens"])[:5]
        print("most expensive prompts (#): " + ", ".join(f"{i + 1} ({turns[i]['input_tokens']})" for i in worst))
    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=["prompt", "calls", "input_tokens", "cached_tokens", "output_tokens", "tool_count", "model"])
            writer.writeheader()
            for i, t in enumerate(turns, 1):
                writer.writerow({"prompt": i, **t})
    return 0


if __name__ == "__main__":
    sys.exit(main())
