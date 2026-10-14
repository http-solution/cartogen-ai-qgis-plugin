# Plan: everything in QGIS through the chat, without breaking what works (2026-10-14)

Written from the code as it is today (main at 1.16.3), not from assumptions. Every claim below was checked in the source or by running the router; where something could not be checked here (no QGIS install in the development sandbox) it says so.

## 1. Reality check

| # | Claim I made earlier | What the code says |
|---|---|---|
| R1 | "The raster calculator stays on the script path." | **Wrong.** The script worker (`_script_isolation_worker.py`) hands a script 9 names (QgsProject, QgsVectorLayer, QgsRasterLayer, QgsFeature, QgsGeometry, QgsPointXY, QgsField, QgsApplication, QVariant) and never initialises the Processing framework (no `QgsNativeAlgorithms`, no `Processing.initialize`). A script cannot run any Processing algorithm, so the raster calculator is not reachable at all through chat today, except inside the dedicated NDVI, change-detection and weighted-overlay tools, which build their own formulas. |
| R2 | "Eight safe algorithms can be added." | **Six, not eight.** `gdal:polygonize` and `gdal:rasterize` write FILES; `_resolve_params` forces `memory:` on every non-raster destination and `harvest_outputs` only picks up raster paths, so they need code changes, not a list entry. The six native ones (extract vertices, densify, polygons to lines, minimum bounding geometry, random points in polygons, delete duplicate geometries) are plausible but their parameter lists were **not verified** (no QGIS here). |
| R3 | "The 13 no-tool actions now get a script fallback." | True, but the fallback is weak: a script runs on a **snapshot** (layer removal, reordering and styling made by a script are not applied back, edits to file layers are reported as not applied) and has no Processing. It can do geometry-only jobs (vertices, densify, polygons to lines, bounding boxes, random points, duplicates). It cannot do polygonize, rasterize, raster calculator, viewshed, a basemap or anything that changes the live project. |
| R4 | "The allow-list is safe." | The generic checker (`parameter_violation`) refuses only `FORMULA`, `EXTRA` and object values. A string that is not a loaded layer is passed to Processing as written, so `"INPUT": "C:\\some\\file.shp"` is read from disk. It is read-only and the output is forced to memory, but it is an unchecked path. No per-algorithm rules exist. |
| R5 | "The allow-listed algorithms are tested." | 34 of 42 are **never run by id in any live test** (8 are mentioned). `test_output_style_live.py` only checks that ids exist in the registry. A regression in `_resolve_params` or `harvest_outputs` would not be caught for most algorithms. |
| R6 | "A user can do everything in QGIS through the chat." | **No.** Searching the tool code: there is no tool for layer groups, project CRS, map scale or zoom to scale, scale-dependent visibility, editing a feature (add, delete, move, change one attribute value; only `field_calculator` writes), clearing a selection, adding an XYZ/WMS/WMTS basemap, virtual joins, a layer filter (definition query), bookmarks, or measuring. Those are the actions behind the 13 "no tool" phrases plus the GUI actions below. |

Verified good (so we keep it): 212 tools, the router fix in 1.16.3, 44 golden requests, 91 vocabulary phrases, all 42 algorithms reachable from a plain request, 26 recorded sessions replayed through the agent loop.

## 2. Rule for every change from now on ("stop breaking things")

1. **No optimisation without a before and after.** A change to the router, the prompt, the guards, the token budget or the tool schemas must paste in the PR the result of `tools/replay_router_across_releases.py` on the golden prompts and the golden-suite counts. A tool that was offered before and is not now needs a written reason.
2. **Golden suites only grow.** Add a test that fails if `GOLDEN`, `GOLDEN_LONG`, `VOCAB` or `ROWS` shrink below their current size (44, 91, 42), so a failing row cannot be fixed by deleting it.
3. **Schema snapshot.** `tests/fixtures/tool_schema_snapshot.json`: every tool name and its required parameters. A removed or renamed tool or parameter fails the build until the snapshot is edited on purpose in the same PR.
4. **Release gate.** The `release.yml` workflow runs the golden suites and the replay and refuses to publish if any fails. A stable release also needs the "START HERE" rows of the live-test pack run by a human on the release candidate (about 30 minutes) with the results file attached to the release.
5. **Every new capability ships with:** its tool test, a live test in the QGIS 4.2.2 image, a golden phrase, an entry in the vocabulary file, and a line in the hand-test pack.

## 3. Phases (order matters: safety net first, capabilities second)

### Phase 0 - Safety net (before any new capability). Size: M
- 0.1 The five rules above (schema snapshot, shrink guard, release gate, PR template with the before/after table, `CONTRIBUTING.md` section).
- 0.2 **Live matrix for all 42 allow-listed algorithms** (closes R5): one small fixture per algorithm run through `run_allowlisted_processing_algorithm` by id in the CI image; assert success, a result layer (or a changed selection) and the expected feature count. This is also the first real check of `_resolve_params` and `harvest_outputs`.
- 0.3 Per-algorithm parameter rules (closes R4): a table giving, for each id, the allowed parameter names and types. Any source-type parameter must name a loaded layer; a path or URL string is refused.

### Phase 1 - Widen Processing, mechanically gated. Size: M
- 1.1 A live "inspect" test dumps the real parameter definitions of every candidate algorithm from the 4.2.2 registry and fails if any parameter is an expression, a file or folder input, a script or an "extra arguments" parameter. **The list is decided by that test, not by me.** Candidates: `native:extractvertices`, `native:densifygeometriesgivenaninterval`, `native:polygonstolines`, `native:minimumboundinggeometry`, `native:randompointsinpolygons`, `native:deleteduplicategeometries`, plus `native:extractbyattribute` (plain field/operator/value) and `native:pointsalonglines`.
- 1.2 Each accepted algorithm gets: a live test (0.2), a router phrase, a golden row (the existing guard forces this), and a line in the tool description.
- 1.3 `gdal:polygonize` and `gdal:rasterize`: separate PR that teaches `_resolve_params` and `harvest_outputs` about vector file outputs (a `TEMPORARY_OUTPUT` file loaded back as a layer), with live tests. GDAL algorithms are Python-implemented and the code already notes they crashed CI on a worker thread, so they run on the GUI thread.
- 1.4 **The raster calculator**: stays off as a free formula. Replace the need with a small dedicated tool, `raster_expression`, that accepts a **parsed** arithmetic expression over named rasters (digits, `+ - * /`, parentheses, raster names; nothing else), rejects everything else, and builds the `gdal_calc` call itself. Same pattern as the NDVI tool. Decision for you: yes or no.
- 1.5 Viewshed has no core algorithm; say so plainly in the reply and offer terrain tools (slope, aspect, hillshade, contours). No script workaround.

### Phase 2 - Missing QGIS actions as confirmed, undoable tools. Size: L (one PR per row)
Each uses the existing checked edit session (`_edit_session.edit_command`) and transaction log (so `undo_last_operation` works) and the confirmation gate for anything destructive. Priority by how often a QGIS user does it:
1. Layer groups: create a group, move layers into it, rename, collapse.
2. Web basemaps: `add_web_basemap` with a fixed vetted set of XYZ/WMTS sources (OpenStreetMap standard, Esri World Imagery, OpenTopoMap) and their attribution; never an arbitrary URL.
3. Project and layer CRS, zoom to scale, bookmarks.
4. Layer filter (definition query) and clearing it, with the expression validated.
5. Attribute editing: change values of selected or filtered features, delete features (confirmation gate), add a feature from WKT, move a feature by geometry, all through the edit session.
6. Selection: clear selection, export selected features.
7. Measure distance, length, area (ellipsoidal, via `QgsDistanceArea`).
8. Virtual joins, scale-dependent visibility.

### Phase 3 - What the script tool is for
Keep Processing out of the script worker (turning it on reopens the #137 class of problem). Instead make the fallback honest: when a task needs a live-project change or Processing and no tool covers it, the reply says so in one sentence and names the nearest tool, instead of improvising a script that cannot apply.

### Phase 4 - Proof before each release
Per phase: offline suite, CI live tests, golden suites, replay, schema snapshot, then one human run of the START HERE rows on a release candidate. Only then a stable number.

## 4. What this plan does not promise
- It does not make the model choose well. It makes sure the model is offered the right tools, that each tool is tested in real QGIS, and that a change which loses a capability fails before release.
- "Everything in QGIS" is a direction, not a state: Phase 2 is a list, and each row ships separately.
- Parameter lists in Phase 1.1 and the 4.2.2 behaviour of every candidate are unverified until the inspect test has run in CI.

## 5. Decisions needed
1. Approve Phase 0 first (recommended, nothing user-visible changes).
2. Approve the mechanical gate for Phase 1 (the inspect test decides the list).
3. Yes or no on the parsed `raster_expression` tool.
4. Order of the Phase 2 rows (the list above is my guess at frequency; yours is better).
