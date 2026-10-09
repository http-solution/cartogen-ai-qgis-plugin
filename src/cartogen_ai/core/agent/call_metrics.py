# -*- coding: utf-8 -*-
"""Per-model-call measurement: what each request to the model cost and what it carried.

Why (2026-10-09): a user's multi-scenario prompt consumed API credit and the first diagnosis rested on ESTIMATES (a ~26k-token
fixed overhead per call, from character counts). Credit is spent on provider-reported tokens, split into fresh input, cached input
and output, so any cost work must start from those, per call, with the estimates kept apart and labelled. This module is pure
(no Qt, no QGIS) so it is unit-testable and cannot raise into the agent loop.

Policy: metadata only, like core/logger.py -- counts, sizes, tool NAMES, timings; never prompt text, tool arguments or results.
Estimates are characters / 4 and are always reported under the `est_` prefix; `input_tokens`, `cached_tokens`, `output_tokens` are
provider-reported and are None when the provider did not report them (never filled in with a guess)."""
import json
import time
from collections import deque

CHARS_PER_TOKEN = 4          # the usual rough ratio; an ESTIMATE, only ever shown as est_*
MAX_RECORDS = 400


def estimate_tokens(obj):
    """Rough token estimate of a str or JSON-serialisable object (chars / 4). Never raises; 0 on failure."""
    try:
        text = obj if isinstance(obj, str) else json.dumps(obj, default=str, ensure_ascii=False)
        return int(len(text) / CHARS_PER_TOKEN)
    except Exception:
        return 0


def prompt_breakdown(messages, tools):
    """Estimated token split of one request: {est_system_tokens, est_tools_tokens, est_history_tokens, est_user_tokens, tool_count}.

    `messages` is the list sent to the model (system first, user message last); `tools` the schema list. History is everything
    between them, including earlier tool results of this turn."""
    messages = list(messages or [])
    system = next((m for m in messages[:1] if isinstance(m, dict) and m.get("role") == "system"), None)
    user = messages[-1] if messages and isinstance(messages[-1], dict) and messages[-1].get("role") == "user" else None
    middle = [m for m in messages if m is not system and m is not user]
    return {
        "est_system_tokens": estimate_tokens(system.get("content") if system else ""),
        "est_tools_tokens": estimate_tokens(tools or []),
        "est_history_tokens": sum(estimate_tokens(m) for m in middle),
        "est_user_tokens": estimate_tokens(user.get("content") if user else ""),
        "tool_count": len(tools or []),
    }


def tool_names(tools):
    return [t.get("function", {}).get("name", "") for t in (tools or []) if isinstance(t, dict)]


def new_record(turn_id, call_index, model, provider, tools, messages, started_monotonic):
    """The record for one request, created just before it is sent. `finish_record` completes it."""
    record = {"turn_id": turn_id, "call_index": call_index, "model": model, "provider": provider,
              "tool_names": tool_names(tools), "started": started_monotonic,
              "input_tokens": None, "cached_tokens": None, "output_tokens": None,
              "latency_ms": None, "tool_calls": 0, "outcome": "pending"}
    record.update(prompt_breakdown(messages, tools))
    return record


def finish_record(record, usage, latency_s, tool_calls=0, outcome="ok"):
    """Fills in the measured part. `usage` is the provider-normalised dict or None (then the three token fields stay None)."""
    if isinstance(usage, dict):
        for key in ("input_tokens", "cached_tokens", "output_tokens"):
            value = usage.get(key)
            record[key] = int(value) if isinstance(value, (int, float)) else None
    record["latency_ms"] = int(latency_s * 1000)
    record["tool_calls"] = int(tool_calls)
    record["outcome"] = outcome
    return record


class CallLog:
    """A bounded in-memory log of call records for this session (not persisted, like UsageTracker)."""

    def __init__(self, maxlen=MAX_RECORDS):
        self.records = deque(maxlen=maxlen)
        self._turn = 0

    def next_turn_id(self):
        self._turn += 1
        return self._turn

    def add(self, record):
        self.records.append(record)
        return record

    def turn_records(self, turn_id):
        return [r for r in self.records if r.get("turn_id") == turn_id]


def turn_summary(records):
    """Measured vs estimated totals for the records of one turn. Measured fields sum only the calls that reported them and say
    how many did not; the estimate is kept in separate keys. Pure."""
    records = list(records or [])
    reported = [r for r in records if r.get("input_tokens") is not None]
    total_in = sum(r["input_tokens"] for r in reported)
    total_cached = sum(r.get("cached_tokens") or 0 for r in reported)
    total_out = sum(r.get("output_tokens") or 0 for r in reported)
    last = reported[-1] if reported else None
    return {
        "calls": len(records),
        "calls_with_usage": len(reported),
        "calls_without_usage": len(records) - len(reported),
        "input_tokens": total_in, "cached_tokens": total_cached, "fresh_input_tokens": total_in - total_cached,
        "output_tokens": total_out,
        "avg_input_per_call": int(total_in / len(reported)) if reported else None,
        "last_call_input_tokens": last["input_tokens"] if last else None,
        "latency_ms": sum(r.get("latency_ms") or 0 for r in records),
        "est_fixed_tokens_per_call": (int(sum(r.get("est_system_tokens", 0) + r.get("est_tools_tokens", 0) for r in records) / len(records))
                                      if records else None),
    }


def next_call_estimate(records):
    """Observed estimate of the NEXT call's input tokens: the last measured input of this turn plus what its own reply added
    is not knowable, so it is the last measured input. None until a call has reported usage (no guess is made)."""
    for record in reversed(list(records or [])):
        if record.get("input_tokens") is not None:
            return record["input_tokens"]
    return None


def turn_usage_line(records):
    """'This turn: 5 calls, 131,878 input (51,200 cached) + 2,100 output tokens; last call 27,400 input' or None. Says plainly when
    some calls reported no usage. Observed numbers only."""
    summary = turn_summary(records)
    if summary["calls"] == 0 or summary["calls_with_usage"] == 0:
        return None
    text = (f"This turn: {summary['calls']} call{'s' if summary['calls'] != 1 else ''}, {summary['input_tokens']:,} input "
            f"({summary['cached_tokens']:,} cached) + {summary['output_tokens']:,} output tokens")
    if summary["last_call_input_tokens"] is not None:
        text += f"; last call {summary['last_call_input_tokens']:,} input"
    if summary["calls_without_usage"]:
        text += f"; {summary['calls_without_usage']} call(s) reported no usage"
    return text


def monotonic():
    return time.monotonic()
