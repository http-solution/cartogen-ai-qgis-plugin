# PLAN-042: Routing wordings as data, not code

Status: in progress

## Goal
A wording the tool router misses ("list medical service in Al Maharah", 2026-10-30) is fixed and guarded by adding one row of data, not by editing a Python table: `python tools/routing_golden.py add "<request>" tool1,tool2`. Later steps move each tool's keywords next to the tool and share concept groups, so a synonym is one line of data.

## Scope
In (step 1, this plan's first PR): `tests/fixtures/routing_requests.json` (rows: prompt, tools that must be offered, source), `tests/test_routing_requests_data.py` (replays the rows against the router), `tools/routing_golden.py` (`add`, `check`).
Step 2 (second PR): `keywords=` on `@register_tool`, migrating tool by tool. Out, for later steps and their own plan lines: shared concept groups, the weak-match `find_tools` fallback, any scoring change. The code tables `GOLDEN` and `GOLDEN_LONG` in `tests/test_tool_router_basics.py` stay; the 385-prompt replay stays.

## Acceptance
1. Offline: every row's tools are offered; every named tool is registered; `tools/routing_golden.py check` says all rows pass.
2. Adding a row needs no Python edit.
3. Not claimed: that a model now completes the requests; only that the router offers the tools.

## Guard tests
- tests/test_routing_requests_data.py::TestRoutingRequestsData::test_every_request_is_offered_its_tools
- tests/test_routing_requests_data.py::TestRoutingRequestsData::test_every_named_tool_is_registered

## Rollback
Delete the three files; nothing else reads them.

## Status log
- 2026-10-30: owner asked for a smarter way to manage the router dictionary; two outside reviews read, most of them already covered by task_matcher, capabilities and the 385-prompt replay. Step 1 built (this PR): data file, replay test, add/check command, three seed rows from the medical-services report.
- 2026-10-30: step 1 merged (#512, `2ec03b6`). Step 2 started (this PR): `register_tool(..., keywords=[...])` stores routing-only phrases in `registry.TOOL_KEYWORDS` (never in the schema); the router scores them like `_TOOL_ALIASES`. Migrated the three medical tools (geocode_and_enrich, geocode_batch, ingest_osm_features) as the proof; the other ~180 alias blocks move in later PRs by domain. The medical wording is still repeated across the three tools: step 3 (shared concept groups) removes that.
