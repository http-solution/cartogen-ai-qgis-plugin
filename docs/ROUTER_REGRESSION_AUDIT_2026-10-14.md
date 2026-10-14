# Router regression audit, 2026-10-14

**Trigger.** Owner report: "create layer for Jordan ADM1" worked in an earlier version and not now; "every release breaks previous work".

**Method.** Forty plain requests (layers, boundaries, export, buffer, service area, layout, dashboard, hazards ...) were replayed through the tool router of all 43 release commits from rc12 to 1.16.2 (git worktrees; `tools/replay_router_across_releases.py`), and the tools offered were diffed release to release. This is deterministic; it does not need a model.

**Finding.** Up to rc21 a short request such as "create layer for Jordan ADM1", "zoom to the layer X", "remove the layer X" or "export X to CSV" was offered `add_layer_from_path`, `zoom_to_layer`, `get_layer_extent`, `remove_layer`, `export_layer`, `reproject_layer`, `clip_layer` and the other layer tools. From rc23 (the cost work, commit a127885, "quieter tool ranking") they were not: the generic words "layer", "add", "create", "export", "get", "set" ... were removed from tool-name matching for **every** request, although the measurement that justified it was made on long requests. With nothing left to score, ties were broken alphabetically, so the model was offered `apply_*` and `calculate_*` tools instead. Nothing crashed and no test failed: the model simply never saw the tool, so it answered "no fetcher is active" or improvised.

**Not the cause.** System-prompt rules (39 rules before and after), the number of tools offered (about 31 on average before and after), the model, the downloads.

**Fix.** The generic-word discount and the cap on description matches now apply only to long requests (more than 25 words), as the original comment said. A permanent guard, `tests/test_tool_router_basics.py`, lists 28 plain requests with the tools they must be offered; it fails on the old router (checked) and passes now. Routing phrases for ADM0 to ADM5, "governorate" and "admin boundaries" were added at the same time.

**Not covered by this audit.** Behaviour that depends on the model's choices (what it does with the tools it is offered), prompts longer than 25 words, and anything in the QGIS UI. Those still need the hand-test rows. The replay tool and the golden table are the first line of defence for routing only.

## Second pass: the three gaps the first pass left open (same day)

The first pass checked only short requests and only which tools are offered. Each gap now has a deterministic check, committed, and run in CI.

### 1. Requests of more than 25 words

Long requests use different rules (generic words discounted, a minimum score), so they were not covered by the 28 short golden requests. Sixteen realistic long requests (35 to 51 words: boundaries plus styling plus layout, OSM plus buffer plus dissolve plus area, route planning, fact-check, hazard maps ...) were written with the tools each needs and run against the router. Two real gaps were found and fixed:

- "classify the slope into five classes, style the result with a **green to red colour ramp**" was offered the vector style tools and not `apply_raster_stretch`: aliases added to that tool.
- "Create a map of Yemen ADM1 ... **style them with a pale fill and a grey outline**" was offered no tool that can change a fill or an outline at all: a `fill_outline_style` capability (`change_layer_color`, `apply_categorized_style`) was added.

Two other failures were wrong expectations in my own table (the OSM tool the router offers for "schools" is `ingest_osm_features`; "within two kilometres" does not name a buffer) and were corrected, not "fixed". The 16 requests are in `tests/test_tool_router_basics.py` (`GOLDEN_LONG`).

### 2. System prompt rules and tool count across all 43 releases

For 18 requests (12 short, 6 long) the system prompt was built for every release from rc12 to 1.16.2 and compared.

| | rc12 | rc21 | rc23 | rc34 | 1.16.2 |
|---|---|---|---|---|---|
| prompt characters (mean) | 28,110 | 28,230 | 28,357 | 28,357 | 28,518 |
| rules included (mean) | 40.1 | 40.1 | 40.1 | 40.1 | 40.1 |
| tools offered (mean) | 34.5 | 35.3 | 35.2 | 35.2 | 35.7 |

So prompt size, rule count and tool count are flat; the earlier statement "39 before and after" was for two requests only and the table above replaces it. The differences that do exist are per request: a rule is included only when a tool it mentions is offered (rules 21, 22, 54, 55 ... follow the tools), so the router regression also dropped the rules that belong to the missing tools. With the router fixed, the rules a request lost relative to history are the ones that belong to tools it should not be offered (for example the severity-index rule for a "zoom" request).

### 3. What happens to the model's choices

No test can replace a real model's choices. What can be tested without a model is everything the plugin does **with** a choice. `tests/test_recorded_sessions_replay.py` replays 26 real sessions from the rc40 hand test (`tests/fixtures/recorded_sessions_rc40.json`: the request, each tool call the model made with its arguments, the recorded result, the recorded reply) through the current agent loop with a scripted model. It fails if the loop skips a call, changes its arguments, returns an error instead of the reply, or replaces the reply. Checked by mutation: replacing the reply guard's output makes it fail.

### Still not covered

- A real model choosing different tools or arguments (the live-test rows, the 38-row open-issues pack).
- The QGIS tools themselves (live tests in CI cover many; the replay uses recorded results).
- The UI (chat widget wiring) beyond the live-widget tests.
- Requests in languages other than English and Arabic.

## Third pass: QGIS everyday vocabulary and the Processing tools (same day, owner question)

**Question.** Are basic QGIS actions and vocabulary covered, including the Processing tools?

**Method.** 91 plain, menu-style phrases (Vector > Geoprocessing, Geometry, Analysis, Research tools, Data management, attribute table, Raster, symbology, labels, layout, project) were written with the tool that does each, or marked GAP where no dedicated tool and no allow-listed Processing algorithm exists. All 42 allow-listed Processing algorithms were also given a plain request. The router was run on each phrase. The 91 phrases were also replayed against rc14, rc21, rc23, rc30, rc40 and 1.16.2 to see whether this is a regression.

**Result before the fixes.**

| | rc14 | rc21 | rc23 | rc30 | rc40 | 1.16.2 |
|---|---|---|---|---|---|---|
| phrases with a tool that reached it (of 78) | 70 | 70 | 69 | 69 | 69 | 69 |
| phrases without a tool that got a fallback (of 13) | 0 | 0 | 3 | 3 | 3 | 3 |

So about 90 percent of the phrases that have a tool reached it in every release, and this part is **not** a regression (the 28 short golden requests were the regression). Two real holes were found:

1. **Seven phrases with a tool were not offered it**: symmetrical difference, k-means, DBSCAN, reclassify a raster, sample raster values (all Processing), "how many features are in the layer" (`get_feature_count`), "categorize the layer by type" (`apply_categorized_style`). Aliases added.
2. **Thirteen everyday actions have no tool at all** (extract vertices, densify, polygons to lines, minimum bounding geometry, random points, split layer, delete duplicate geometries, raster calculator, polygonize, rasterize, viewshed, add a basemap, measure a distance) and, in 10 of the 13 cases, the model was offered neither a Processing tool nor the script fallback, so it could only say it could not. They now earn `execute_pyqgis_script` and `find_tools` (new `_NO_TOOL_ACTIONS` table in `capabilities.py`, kept apart from the main table so it does not turn plain requests into "workflows").

**Processing allow-list.** 41 of 42 algorithms were reachable from a plain request; `native:creategrid` ("create a grid") was not (alias added). `tests/test_processing_allowlist_routing.py` now maps every allow-listed algorithm to a request and fails when a new algorithm is added without one.

**Not done, on purpose: widening the allow-list.** The 13 GAP actions could be given safe Processing algorithms (`native:extractvertices`, `densifygeometriesgivenaninterval`, `polygonstolines`, `minimumboundinggeometry`, `randompointsinpolygons`, `deleteduplicategeometries`, `gdal:polygonize`, `gdal:rasterize`). Each needs per-algorithm parameter checks and a live test, and `gdal:rastercalculator` is the one the 2026-10 audit (issue 137) found executes Python expressions, so the raster calculator stays out. This is a security decision for the owner (CONTRIBUTING: flag, do not apply); recommendation: add the eight listed above, one PR with their parameter rules and live tests, and leave the raster calculator on the script path.

**Guards added.** `tests/test_qgis_vocabulary_coverage.py` (91 phrases) and `tests/test_processing_allowlist_routing.py` (42 algorithms).

**Still not covered.** What the model does with the tools it is offered, and whether each Processing algorithm actually runs in QGIS (the live tests in CI run a subset; `tests/test_processing_allowlist_tools_live.py` is the place to extend).


### Correction (same day, after reading the code)
Three statements in the third pass were wrong and are replaced by docs/PLAN_FULL_QGIS_BY_PROMPT_2026-10-14.md: the raster calculator does **not** stay available on the script path (the script worker has no Processing framework at all); the safe-algorithm count is **six**, not eight (the two GDAL ones need code changes); and the script fallback added for the 13 no-tool actions only helps geometry-only jobs. 34 of the 42 allow-listed algorithms are not run by id in any live test.
