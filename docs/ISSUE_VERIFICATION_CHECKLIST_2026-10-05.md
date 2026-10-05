# Issue verification checklist (open issues, 2026-10-05)

A dated checklist, not a result. Nothing here has been run by hand. It turns the open GitHub issues into hand-test rows so each can be closed on a
pass. **An issue is closed only on a hand-verified pass** (see `docs/RC12_LIVE_TEST_AND_AUDIT_PLAN_2026-10-04.md` section H for what to record).
This file indexes and extends that plan; where the plan already has a row, the row id is given (B*, C, I*) instead of repeating it.

**Build under test:** the `cartogen-ai-v1.16.0-rc14` pre-release (install the attached zip, not "Source code (zip)"; restart QGIS; Settings must show
`1.16.0-rc14`). **Data:** the Yemen/Sanaa project of the rc10/rc11 smoke tests (roads with `oneway` F/T/B and `speed_kmh`, health facilities,
`yem_ppp_2020`, an HDX admin layer), saved before you start.

**"State"** = what is true in the code today, taken from the commit history, the tracker and the rc12 plan (not re-run today). *CI* = covered by the
offline suite and/or the `qgis-live-tests` job (QGIS 4.2.2). *Hand* = needs you in a desktop QGIS session. Open count on 2026-10-05: **62 open issues**
(10 others are already closed).

## 0. Gate (do first)
Panel opens at start-up; the API key is still present; no traceback in the QGIS log on load; Settings shows `1.16.0-rc14`.

## 1. rc7 smoke-test findings (#72-#97)
The "State" cells in this section summarise the rc8-rc12 fix lists (`docs/RC7_SMOKE_TEST_FINDINGS_2026-09-30.md`, the tracker); read the finding there if a row's wording looks too short.

| Issue | State | Run | Expected |
|---|---|---|---|
| #75 F03 fabricated tool output | Fixed: guard + footnote for ungrounded claims (rc12). CI for the logic; needs a real model | Plan section C: after a service-area run ask "What population lives within one hour of this point, and what region is that in?" | Tool-derived figures carry no note; any place name, million-plus total, file size or terrain wording the tools did not return is listed in a "Not from a tool result" footnote. Record false positives and misses with the exact wording |
| #79 F07 duplicate/orphan layer-tree nodes | Fixed with live tests + healing (rc9). CI | Run an analysis that reorders layers; open Layer Order | Nodes == layers; basemap at the bottom; no orphan nodes after removing a layer |
| #80 F08 "beyond one hour" took 44 min | Fixed: single-tree matrix, `classify_facilities_by_access`, time estimate + Stop. CI; timing is live-only | "Which health facilities are beyond one hour's travel from <point>?" on the Yemen project (plan B3, #122) | Finishes well under a minute for the reference request, 110 reachable facilities; Stop works |
| #81 F09 convex-hull exposure | Fixed: three labelled figures (rc10). CI | "Population within the one-hour service area" (plan B9, #123) | Concave-hull headline + road-buffer + convex hull labelled an upper bound |
| #84 F12 HTML dashboard | Fixed: saved under the project, full path, sample notice, fitBounds, no-basemap markers. CI | Generate a dashboard (basemap "none" and default); open in a browser (plan B13) | File in `<project>/outputs`; "showing N of M"; map fits the data; markers and layer control draw |
| #86 F14 double confirmation / model-authored "Preview Ready" | Fixed: model prose suppressed when a real card shows (rc8/rc10). CI | Trigger a confirmable tool (e.g. add layer with write) | One card; no model-written "Preview Ready" text |
| #87 F15 UX polish | Fixed: Sensitivity dialog text, LaTeX degree, stray ")", log level. CI | Open Layer Data Sensitivity; ask for a slope in degrees; run an access analysis with unreachable facilities | Dialog explains itself; "45°" not raw LaTeX; unreachable-facility lines are INFO/WARNING with a count, not ~130 CRITICAL lines |
| #88 F16 generic "yes" resolves a stale destructive preview | Fixed: explicit words only (rc8). CI | Stage `load_project`, ignore it, send an unrelated message that raises a router card, reply "yes" (plan B5) | The project is NOT replaced; a hint is shown |
| #89 F17 live tests for the rc7 defects | Done: tests added in rc8. CI green | Check the `qgis-live-tests` job list in `tests.yml` against the F-series | Closable on CI evidence (your call) |
| #91 F19 whole-country WorldPop | Fixed: bbox/extent clip, size confirmation, honest refusal text. CI | Plan I14: `fetch_worldpop_population` for a city bbox | Only the bbox is added; real file size shown; one confirmation if worldpop refuses a partial read |
| #92 F20 request coordinates assumed in project CRS | Fixed: deterministic coordinate handling + asks the CRS when unstated and out of range (#119). CI | Plan B1: "Add a point at 4902068.0, 1799912.0" in a 3857 project | Asks which CRS; places nothing |
| #93 F21 schema of a SENSITIVE layer reaches the cloud | Disclosure text added (rc12); the "acceptable?" decision is yours. CI | Plan I13: open Settings and Layer Data Sensitivity | Both show the schema-disclosure text. Then record your decision (accept / gate in STRICT mode) |
| #94 F22 103 MB extract without asking | Fixed: size threshold + cached skip + whole-country refusal. CI | Ask for a road-network task needing a Geofabrik extract | A size confirmation appears before any download over the threshold |
| #95 F23 project memory wrote wrong coordinates | Fixed: consent + never raw coordinates. CI | Run a plain service-area request; open Memory dialog | Nothing written without consent; no coordinates stored; dialog is not empty-and-silent |
| #97 F25 exported chat history missing turns | Fixed: opt-in full project-lifetime transcript, Memory-dialog delete. Needs a long real session | Chat for ~20 turns, rename/save the project, export history | All turns present with clock times; the digest is included |
| #72 umbrella (rc7 findings) | Children above | — | Close when #75-#97 are closed |

## 2. rc11 smoke findings (#119-#132)
| Issue | State | Run | Expected |
|---|---|---|---|
| #119 | Fixed (rc12). CI | Plan B1 | Asks which CRS; places nothing |
| #120 generic labels / unsaved scratch layers / black raster | Fixed: `tidy_project_layers`, labelling, ramp name check. CI | Plan B10 on an old project | Report lists duplicates, black raster and scratch layers; apply hides extra copies, restyles the raster, saves scratch layers; deletes nothing |
| #121 repeated service area makes new origin/result sets | Fixed: origin reuse. CI | Plan B2: same request three times | One origin layer; no new origin/result sets |
| #122 model restyles the access layer | Fixed: restyle blocked; task hints corrected. CI | Plan B3 | Green/red layer kept; no model re-style |
| #123 one bare headline number | Fixed (#133). CI | Plan B9 | Three labelled figures |
| #124 egress card rough (label, raw dict, duplicates) | Fixed (rc12). CI | Plan B4 (and trigger an egress override) | Clean card text; one live card; no raw dict; no stale previews |
| #125 casual "yes" retries via `execute_pyqgis_script`; "confirm" approves an egress override | Fixed (rc12). CI | Plan B5; then, with a `remove_layer` preview pending, reply "yes"; type "confirm" while an egress card is pending | No model call from a vague reply; no alternate destructive route; an egress override is approved only by the card click |
| #127 HDX admin layer opaque/unlabelled/duplicated | Fixed (#133). **Not re-run in real QGIS** | Plan B8 | One layer, labelled, pale fill, polygons below lines/points |
| #128 `yem_ppp_2020` black | Fixed: name check. **Not verified in real QGIS** | Plan B10 / load `yem_ppp_2020` and run a stretch | Warm ramp, empty land transparent, `people/cell` legend |
| #129 print-layout graticule/legend/body box | Fixed (#126, #177). Re-check by hand | Plan B12 (PNG and PDF) | Thin pale graticule; legend lists the reach polygon; body panel sized to its text; no stacked duplicate result sets |
| #130 non-request fragment starts an analysis | **Checked 2026-10-05:** the classifier answers "too short to be a request" for `template: access_map` and `yes` (test `tests/test_task_register.py`). The proposal's point 3 (say so when a replace-by-name would overwrite a result with different parameters) is NOT built | Plan B6: paste `template: access_map` | No analysis starts. Close on a pass, or keep open for point 3 (your call) |
| #131 fastest route | Fixed: two-stop skip, draw order, route honours direction/speed, `strategy='fastest'` estimate, deprecation arguments. CI; timing not measured live | Plan B11: "Fastest route from A to B" | Estimated time labelled an estimate with the speed basis; the route sits above the roads; a shortest route is not called "fastest"; duration well under the earlier 14 min (record it) |
| #132 one-way streets on Geofabrik extracts | Fixed (`F/T/B` recognised when the layer's own values are a subset). CI; **not run on the real Yemen layer** | Plan B7: service area from a point beside a one-way street | Differs from the two-way result |

## 3. External audit, P1 (#137-#151) and umbrella #169
All fixed in PR #171 and follow-ups (README: "fixed in code and CI-verified where a live test exists"), except #151, which needs a database.
For each, run the issue's **Acceptance** line; the "Hand" column is what only a desktop session shows.

| Issue | Acceptance (from the issue) | Hand check |
|---|---|---|
| #137 allowlisted `gdal:rastercalculator` | Permitted arithmetic works; imports, attribute traversal, arbitrary calls and extra backend arguments are rejected before execution | Ask the agent for a raster calculation with `__import__('os')` in the formula: refused with a message |
| #138 snapshots off the main thread | Thread-affinity assertions in every snapshot helper under a real `AgentQgsTask`; remove/style/field/undo exercised | Run remove / style / add-field / undo from chat; no crash, no "wrong thread" log lines |
| #139 hub siting `hasGeometry()` | Algorithm executed with normal points, null geometries, multipoints, empty candidates | Run Cartogen hub siting from the Processing toolbox on valid points: it runs (plan I8) |
| #140 service-area `materialize()` | Run from the Processing dialog and a model, with layer ids, layer objects, selected features, filtered sources | Run it from the toolbox on a road layer + facility layer (plan I8) |
| #141 SI-named fields | SI outputs constant across project unit changes (geographic, metric, US-survey-foot) | `calculate_area` with the project area unit set to km² then ha: `area_sqm` identical |
| #142 mixed CRS | Equivalent datasets in different CRSs give equal ranks and distances | Hub siting on candidates in 4326 vs the same in a projected CRS: same ranking |
| #143 edit-session takeover | Unrelated edits survive success and failure; undo stack stays coherent | Edit a layer (leave it in edit mode), run a field calculation, then check your edit is still uncommitted and undo still works |
| #144 failures reported as success | Malformed expressions, incompatible types, read-only sources, commit failure leave no partial change and return failure | Field-calculate a bad expression and a text into an integer field: error shown, layer unchanged |
| #145 isolated-script outputs in deleted temp dir | Results readable after scratch cleanup, provider reopen, save/reopen, unload | Create a layer by `execute_pyqgis_script`, save, close, reopen: data still there |
| #146 reconciliation drops same-count edits | Same-count attribute/geometry edits reconcile or give an explicit unsupported error | Script that edits one attribute and one vertex without changing counts: edit reaches the live layer |
| #147 turn not bound to its project | No old tool modifies the new project; no old response or history appended there | Start a long request, switch project mid-way: nothing lands in the new project or its history |
| #148 bbox nearest neighbour for lines | Concave/U-shaped roads, overlapping envelopes, off-road facilities return the true nearest reached geometry | `classify_facilities_by_access` with a U-shaped road and a facility inside the U: classified by true distance |
| #149 compound tools bypass the egress gate | Sensitive-layer statistics inside stored presets and SQL cannot return to a cloud provider without the explicit override | Mark a layer SENSITIVE; run a stored workflow and an SQL query touching it with a cloud provider: blocked until the card override |
| #150 lineage ignores list/nested inputs | Merge, overlay, weighted-raster, generic Processing preserve ancestry; renames and duplicate names cannot open a protected output | Merge a SENSITIVE layer with another, rename the output: still protected |
| #151 PostGIS read-only SQL | Integration tests with geometry and non-spatial SELECTs, missing connections, auth configs, rejected mutations, provider failure | **Blocked on a database** (not touched). Needs a PostGIS connection |
| #169 umbrella | — | Close when #137-#168 are closed |

## 4. External audit, P2/P3 (#152-#168)
Merged as WP1-WP6 (PRs #175-#181). **None is hand-verified.** The plan's section I has the full rows (I1-I16); this maps issue to row.

| Issue | State | Row | Still open inside it |
|---|---|---|---|
| #152 travel_time_matrix partial-edge cost | Fixed (WP5) | I7 | — |
| #153 raster arithmetic common grid | Partial (WP2): mismatched grids refused | I4 | Automatic alignment |
| #154 elevation/slope/min-area units | Partial (WP2) | I5 | DEM vertical unit assumed metres |
| #155 impassable roads still traversable | Fixed (WP3); a closed road is a negative speed, not 0 | I6 | — |
| #156 service-area output schema/CRS/time | Fixed (WP4) | I8 | — |
| #157 sinks/cancellation | Fixed (WP4) | I8 | — |
| #158 result table names collide | Fixed (WP1); automatic only | — | — |
| #159 display names collapse features | Partial (WP2) | I1, I2 | Score writes in `analysis_tools` |
| #160 zonal tools mutate input | Partial (WP2) | I1 | Raster-unit validation |
| #161 boundary points / overlaps | Partial (WP2) | I3 | Reprojecting points into the admin CRS |
| #162 allowlist references missing algorithms | Fixed (WP4) | I9, I10 | — |
| #163 generic Processing output names/params | Fixed (WP4) | I8, I9 | — |
| #164 layout replacement / atlas collisions | Fixed (WP6) | I11 | — |
| #165 access-map guide text | Fixed (WP1) | I15, B12 | — |
| #166 wheel omits JSON resources | Fixed (WP1); wheel not built in the sandbox | I16 | A clean-environment `pip wheel .` |
| #167 plugin lifecycle | Partial (WP6) | I12 | Running-task invalidation at unload |
| #168 Python 3.9 vs 3.10 floor | Fixed (WP1); automatic only | — | Closable on CI evidence |

## 5. Items with no open issue but still unverified
Smoke 16-18 (carry-over C2, C3, C4, C12; C13 clean-profile install; C14 upgrade from the previous zip; C7 sandbox refusals), the JIAF project-store
and layer writes (`record_jiaf_decisions`, `finalize_jiaf_results` with `write_fields`) and the hydrology tools H1-H5 (plan section E).

## 6. Suggested order
1. Gate (section 0). 2. Plan section B (13 quick rows covering #88, #92, #119-#132). 3. Section 3 rows #139, #140, #141, #143, #144 (the cheapest to reproduce).
4. Plan section I (I1-I16). 5. Section 1 rows needing a long session (#97, #75). Record each result in a new dated doc and on the issue.
