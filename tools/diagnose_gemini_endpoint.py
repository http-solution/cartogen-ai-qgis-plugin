#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Checks, with a real key, what Google's OpenAI-compatible Gemini endpoint does with the options the API-call optimisation plan
(docs/API_CALL_OPTIMIZATION_PLAN_2026-10-10.md, phase 0) wants to use. It uses the plugin's own GeminiClient, so it tests what the
plugin would actually send.

    GEMINI_API_KEY=... python tools/diagnose_gemini_endpoint.py [--model gemini-flash-latest] [--json out.json]

What it sends: only short synthetic text and one dummy tool, plus (for the cache probe) the same ~20 KB of filler text twice. No
project data, no layer names. Cost: a handful of small requests and two of about 5,000 tokens. The key is read from the environment
only and is never printed.

What each probe answers (PASS/FAIL is about the endpoint's behaviour, not the plugin):
  baseline          a tool-calling request works at all
  tool_choice none  with a tool offered and a prompt that invites it, NO tool call comes back (a text-only turn can be forced)
  tool_choice req   a tool call comes back when required
  tool_choice named the named function is the one called
  extra_body flat   {"google": {...}} at the top level of the body is accepted
  extra_body nested {"extra_body": {"google": {...}}} is accepted (the shape Google's OpenAI-client examples use)
  implicit cache    the second of two identical ~5,000-token requests reports cached_tokens > 0 (not guaranteed; run it twice)
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from cartogen_ai.infrastructure.providers.gemini import GeminiClient  # noqa: E402

DUMMY_TOOL = [{"type": "function", "function": {
    "name": "get_layers", "description": "Lists the layers in the project.",
    "parameters": {"type": "object", "properties": {}}}}]
PROMPT = [{"role": "user", "content": "Use the get_layers tool to list the layers."}]


def _tool_calls(result):
    message = result.get("message") or {}
    return message.get("tool_calls") or []


def _probe(name, fn):
    started = time.monotonic()
    try:
        ok, detail = fn()
    except Exception as e:                       # a probe must never stop the others
        ok, detail = False, f"{type(e).__name__}: {e}"
    return {"probe": name, "pass": bool(ok), "detail": detail, "seconds": round(time.monotonic() - started, 1)}


def run(model):
    client = GeminiClient(os.environ["GEMINI_API_KEY"], model=model)
    results = []

    def baseline():
        r = client.complete(PROMPT, tools=DUMMY_TOOL, max_tokens=200)
        if "error" in r:
            return False, r["error"][:300]
        return True, f"tool_calls={len(_tool_calls(r))} usage={r.get('usage')}"

    def choice_none():
        r = client.complete(PROMPT, tools=DUMMY_TOOL, max_tokens=200, tool_choice="none")
        if "error" in r:
            return False, r["error"][:300]
        calls = _tool_calls(r)
        return (not calls), f"tool_calls={len(calls)} text={(r['message'].get('content') or '')[:80]!r}"

    def choice_required():
        r = client.complete([{"role": "user", "content": "Say hello."}], tools=DUMMY_TOOL, max_tokens=200, tool_choice="required")
        if "error" in r:
            return False, r["error"][:300]
        return bool(_tool_calls(r)), f"tool_calls={len(_tool_calls(r))}"

    def choice_named():
        choice = {"type": "function", "function": {"name": "get_layers"}}
        r = client.complete([{"role": "user", "content": "Say hello."}], tools=DUMMY_TOOL, max_tokens=200, tool_choice=choice)
        if "error" in r:
            return False, r["error"][:300]
        names = [c.get("function", {}).get("name") for c in _tool_calls(r)]
        return names == ["get_layers"], f"called={names}"

    def extra(body):
        def inner():
            r = client.complete([{"role": "user", "content": "Reply with the word ok."}], max_tokens=50, extra_body=body)
            if "error" in r:
                return False, r["error"][:300]
            return True, f"accepted; usage={r.get('usage')}"
        return inner

    thinking = {"thinking_config": {"thinking_budget": 0}}

    def cache():
        filler = ("The project contains layers of several kinds, each with fields and features. " * 330)
        messages = [{"role": "system", "content": filler}, {"role": "user", "content": "Reply with the word ok."}]
        first = client.complete(messages, max_tokens=20)
        if "error" in first:
            return False, first["error"][:300]
        time.sleep(3)
        second = client.complete(messages, max_tokens=20)
        if "error" in second:
            return False, second["error"][:300]
        u1, u2 = first.get("usage") or {}, second.get("usage") or {}
        cached = u2.get("cached_tokens") or 0
        return cached > 0, f"first={u1} second={u2} (cached_tokens on the 2nd call: {cached})"

    for name, fn in (("baseline", baseline), ("tool_choice none", choice_none), ("tool_choice required", choice_required),
                     ("tool_choice named", choice_named), ("extra_body flat", extra({"google": thinking})),
                     ("extra_body nested", extra({"extra_body": {"google": thinking}})), ("implicit cache", cache)):
        results.append(_probe(name, fn))
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--model", default="gemini-flash-latest")
    parser.add_argument("--json", help="also write the results to this file")
    args = parser.parse_args()
    if not os.environ.get("GEMINI_API_KEY"):
        sys.exit("Set GEMINI_API_KEY in the environment (it is never printed).")
    results = run(args.model)
    print(f"Gemini OpenAI-compatible endpoint, model {args.model}\n")
    for r in results:
        print(f"{'PASS' if r['pass'] else 'FAIL':4s}  {r['probe']:22s} {r['seconds']:5.1f}s  {r['detail']}")
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump({"model": args.model, "results": results}, fh, indent=2)
    return 0 if all(r["pass"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
