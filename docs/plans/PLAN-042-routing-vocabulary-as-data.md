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
- 2026-10-30: step 2 merged (#513, `84bbb1c`). Step 3 (this PR): shared concept groups in `core/services/routing_concepts.json`, named by `concept:<name>` in a tool's `keywords=` (or in `_TOOL_ALIASES`); not `@`, because existing aliases such as `@2` start with it. First group `health_facility` replaces the 12 medical phrases repeated in three tools; the phrases and scores are unchanged. Checked by hand that the JSON ships in the release zip (it is under src/, like algorithm_topics.json); no test builds the zip.
- 2026-10-30: step 3 merged (#514, `76f4a76`). Step 2 completed (this PR): all 180 remaining entries of `tool_router._TOOL_ALIASES` moved into their tools' `keywords=[...]` by a script that kept each why-comment above its list; `_TOOL_ALIASES` is now an empty legacy dict. Proof of no change: the set of phrases per tool, taken before and after for all 183 tools, is identical, and the total is 2105 both times. Two tests read the dict and would have passed on an empty dict, so they now read `routing_phrases()` (the 1565-phrase 'each phrase still offers its own tool' replay, with a floor of 1500 phrases checked, and the 5-character minimum for engineering aliases); the duplicate-key guard became 'no tool is registered twice' plus a floor on the phrase count. Not verified: model behaviour.
- 2026-10-31: steps 2 and 3 merged (#514 `76f4a76`, #515 `39777f0`). Step 4 (this PR), changed from the first idea after measuring: a 'weak match' trigger cannot fire (the best score was 10 or more for all 493 test requests; the medical miss was a confident wrong answer). Instead: (1) `find_tools` also scores a tool when one of its curated routing phrases occurs in the request (before, 'list medical service in Al Maharah' found calculate_service_area and list_bookmarks; now the OSM and geocoding tools); (2) `find_tools` is always offered, appended after the top_k cut so it takes no slot (a reserved slot dropped get_layer_extent for 'zoom to the layer', caught by the golden table), so the router can return top_k + 1; (3) prompt rule 56 (core): if no offered tool fits, call `find_tools` before saying a capability is missing or writing a script. Parts 1 and 2 are checked offline; part 3 changes model behaviour and is NOT verified: it needs a real model run (hand row: 'list medical service in Al Maharah' with a CLI or API connection).

- 2026-10-31: HT-7 audit, first round (this PR). 30 everyday wordings, each checked against the real router and find_tools with real tool names (a first pass with guessed tool names was discarded). Before: 11 did not offer the right tool (hide/show a layer, where to put a warehouse, heat map, average of each column, shrink the polygons, cut/crop with a boundary, switch the coordinate system, who lives near the flooded area). Now: phrases added beside toggle_visibility, optimal_hub_siting, apply_heatmap_style, field_statistics, buffer_analysis, clip_layer, reproject_layer and estimate_population_exposure; the 12 wordings are rows in tests/fixtures/routing_requests.json (pin raised to 15). Not covered: other tool families, and whether a model then picks the tool.
