# PLAN-003: measure the 28-tool default against live answers

Status: in progress

## Goal
Show that offering 28 tool definitions instead of 40 (rc47, about 35 percent fewer tokens per call) loses no capability in a real session, or raise the default.

## Scope
In: the rc47 test run, with `tools/summarize_usage_log.py` for tokens and a count of "tool not available" style replies. Out: other cost work (history compaction, cheaper models).

## Acceptance
1. Part 2 of the bundle ends with no row failing because a needed tool was not offered (the row notes say which tool the assistant chose).
2. The usage table shows input tokens per prompt lower than the rc46 run for the same kind of prompt. A number goes in the status log; "should be lower" does not.

## Guard tests
`router-top-k` in `docs/FEATURE_LEDGER.json` (the golden routing tables still pass at 28).

## Rollback
Set `cartogen_ai/tool_router_top_k` to 40 in QGIS advanced settings, or change `DEFAULT_TOP_K` in `tool_router.py`.

## Status log
- 2026-10-18: default changed 40 to 28 (PR #363); offline measurement 14.3k to 9.4k mean tool-definition tokens. Not measured live.
