# Cartogen AI

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="branding/cartogen-lockup-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="branding/cartogen-lockup-light.svg">
  <img src="branding/cartogen-lockup-light.svg" alt="Cartogen AI" width="440">
</picture>

<p align="center">
  <strong>Spatial AI for QGIS — plan it, run it, inspect the work.</strong><br>
  Describe a mapping or analysis task in plain language and Cartogen AI turns it into
  visible, real operations against your open QGIS project.
</p>

<p align="center">
  <a href="https://github.com/http-solution/cartogen-ai-qgis-plugin/actions/workflows/tests.yml"><img src="https://github.com/http-solution/cartogen-ai-qgis-plugin/actions/workflows/tests.yml/badge.svg" alt="Tests"></a>
  <a href="https://github.com/http-solution/cartogen-ai-qgis-plugin/releases"><img src="https://img.shields.io/github/v/release/http-solution/cartogen-ai-qgis-plugin?display_name=tag&include_prereleases" alt="Release"></a>
  <a href="https://github.com/http-solution/cartogen-ai-qgis-plugin/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-GPL--2.0-blue.svg" alt="GPL-2.0 license"></a>
  <a href="https://github.com/http-solution/cartogen-ai-qgis-plugin/issues"><img src="https://img.shields.io/github/issues/http-solution/cartogen-ai-qgis-plugin" alt="Issues"></a>
  <a href="https://cartogenai.com"><img src="https://img.shields.io/badge/website-cartogenai.com-0b6efd" alt="Website"></a>
</p>

**Community edition · Version 1.17.0-rc45 (pre-release) · GNU GPL v2 · QGIS 4.2–4.99 · [cartogenai.com](https://cartogenai.com)**

Cartogen AI is built for GIS analysts, humanitarian teams, researchers, and anyone who
needs to move from a question to a reproducible spatial result without leaving QGIS.
The agent exposes its plan, tool calls, progress, and errors instead of returning a
black-box answer.

> **Project status (2026-10-06):** active Community edition, currently at the **1.17.0-rc45 pre-release** build (the last stable build is 1.16.3; rc20 to 1.17.0-rc45 add the audit fixes, hand-test fixes and the cost and routing work made after rc19).
> - **Tests:** 3,570 automated tests, 0 failures in the offline run; the live-QGIS tests (and any needing optional libraries) are skipped there and
>   the QGIS ones run in CI (the `qgis-live-tests` job, QGIS 4.2.2).
> - **Architectural audit:** an external audit of rc12 raised 32 findings, filed as issues #137-#168 (tracking issue #169). The 15
>   highest-severity findings (#137-#151) are fixed in code and CI-verified where a live test exists, except #151 (PostGIS), which needs a
>   database and is untouched. The other 17 (#152-#168) were addressed in work packages 1-6 (merged, CI-verified); some have parts still
>   open (raster auto-alignment, DEM vertical unit, raster-unit validation, running-task invalidation at unload). All 32 issues remain open
>   because none of the fixes has been hand-verified yet; the per-issue hand checks are in
>   [docs/ISSUE_VERIFICATION_CHECKLIST_2026-10-05.md](docs/ISSUE_VERIFICATION_CHECKLIST_2026-10-05.md).
> - **Not yet verified:** a complete hands-on smoke test of rc12 to rc23 in a desktop QGIS session (rc18 was partly hand-tested: rows R1-R7 and N1-N9 ran, rows V, T, J and P did not). A clean-profile install and an in-place upgrade
>   were verified on an earlier release candidate (rc6); the rc23 build has passed local packaging checks, the release workflow's zip checks and GitHub Actions on the merged head.
> - Details: [the release smoke test](docs/RELEASE_SMOKE_TEST.md), [the implementation tracker](docs/IMPLEMENTATION_TRACKER.md),
>   [the rc12 live-test and audit plan (still applies to rc23)](docs/RC12_LIVE_TEST_AND_AUDIT_PLAN_2026-10-04.md).

## What it does

- **Multi-provider**: OpenRouter, Google Gemini, or a local
  Ollama server — switch anytime, bring your own API key (OpenRouter has a free tier;
  Ollama is free and fully local).
- **Native QGIS Processing Provider**: Registered under `QgsApplication.processingRegistry()`
  (`cartogen_ai.processing`), exposing native algorithms (e.g. `OptimalHubSitingAlgorithm`,
  `CalculateServiceAreaAlgorithm`) directly to the QGIS Processing Toolbox, Graphical Model Designer,
  batch processing, and headless `qgis_process` CLI execution.
- **294 tools** covering vector and raster geoprocessing, OGC SLD 1.1.0/1.0.0 export, point cluster
  and displacement renderers, styling and labeling (with text halos and obstacle avoidance), print
  layouts with coordinate graticules and inset locator maps, exports, humanitarian data (HDX /
  OpenStreetMap / geoBoundaries / building footprints), satellite imagery search, database queries,
  trend forecasting, humanitarian severity/needs indexing (JIAF/INFORM-style composite scoring for
  fund-allocation prioritization), 3W/4W operational-presence analysis and coverage-gap detection, live
  hazard monitoring (NASA FIRMS active fires, NASA EONET natural events, GDACS disaster alerts) with
  recurring-workflow tracking, an interactive HTML situation dashboard export with per-layer freshness
  badges, ellipsoidal geodetic distance measurement (`QgsDistanceArea`), geoprivacy obfuscation for
  sensitive point data (Do No Harm), and workflow presets — see
  [docs/TOOLS_REFERENCE.md](docs/TOOLS_REFERENCE.md) for the full, auto-generated list.
- **Guided by a 792-task Humanitarian Mapping Task Register**: a request that
  matches a task shows the exact prompt about to be sent, with the reasoning behind it, before
  it's sent; stops to ask only when a detail genuinely can't be safely guessed (e.g. hazard or
  facility type); and checks the response against what the task promised, with one automatic,
  disclosed follow-up if a promised dashboard, export, or chart didn't actually get produced.
  See [docs/USER_GUIDE.md](docs/USER_GUIDE.md).
- **API Token Economy & Caching**: Deterministic tool tie-breaking designed for Gemini 2.5+
  implicit prefix caching (up to 90% prompt discount), Claude/OpenRouter prompt cache control breakpoints,
  and dynamic token budgeting per turn.
- **Enterprise & Network Integration**: Native `QgsMessageLog` structured logging under the "Cartogen AI"
  panel, custom exception hierarchy (`CartogenError`), and automatic `QgsNetworkAccessManager` proxy
  detection for restricted corporate or field environments.
- **Task Manager**: multi-step requests get a visible plan with progress tracking,
  retry, and edit-and-resend for failed steps.
- **File attachments**: PDF, Word, CSV, Excel, and images. CSV/Excel attachments can be
  loaded as full real layers (not just a preview) with automatic point-geometry
  detection for coordinate columns.
- **Native web search grounding** on Gemini, with automatic model fallback
  if a configured model is retired.
- **Stop button**: cancel an in-progress request instead of waiting it out.
- **Security-conscious by design** — see [SECURITY.md](SECURITY.md) for the full
  threat model and what was actually adversarially tested (not just intentions):
  a restricted execution sandbox for model-generated PyQGIS scripts, fail-closed
  read-only SQL enforcement, an SSRF guard on fetched URLs, and a destructive-action
  confirmation gate the model cannot self-approve.

## What's new in 1.17.0-rc45

Built on 1.17.0-rc44. Offline tests and the QGIS 4.2.2 live checks in CI pass; **not hand-tested** in desktop QGIS unless an item says so. Full list: the `v1.17.0-rc45` block in [metadata.txt](metadata.txt) and [CHANGELOG.md](CHANGELOG.md).

- Fixes found against the QGIS 4.2.3 reference: The map-history tool (zoom_history) now says so when there is no earlier or later extent instead of reporting success; diagnose_topology counts invalid geometries again; the proxy check no longer fails on the QGIS network settings; and the point-displacement map style applies. A new test compares every QGIS call in the code with the 4.2.3 reference list and fails on a name that does not exist.
- Not hand-tested: Everything above is checked by the offline suite and, for the QGIS parts, by CI on QGIS 4.2.2. None of it has been hand-tested in desktop QGIS. The check compares method names only, not argument lists or return types.

## What's new in 1.17.0-rc44

Built on 1.17.0-rc43. Offline tests and the QGIS 4.2.2 live checks in CI pass; **not hand-tested** in desktop QGIS unless an item says so. Full list: the `v1.17.0-rc44` block in [metadata.txt](metadata.txt) and [CHANGELOG.md](CHANGELOG.md).

- Symbology and labels: New tools: rule-based labels, label callouts and masks, pie and bar diagrams, SVG and font point markers, hillshade and contour styles for rasters, and a personal symbol library (save a layer's symbol, list and re-apply it). Undo covers the label, callout, diagram, marker, relief and saved-symbol changes.
- Print layouts: New tools: an overview (locator) map, layout guides and a snapping grid, an atlas with one page per feature, bar, line and pie charts, and an elevation profile along a line. A layout can be exported with a world file or as a GeoPDF. How charts and profiles look when drawn has not been checked.
- New layer types: New tools: open a point cloud (.copc.laz or EPT; a plain .las or .laz needs a QGIS build with the PDAL provider and says so otherwise), a vector tile source (https XYZ, .mbtiles or .vtpk) and a 3D Tiles tileset. New settings tools: turn elevation on for a raster or set a vector layer's clamping and extrusion, and set the project's terrain (flat or a DEM).
- GRASS and mesh algorithms: The approved Processing list grew from 267 to 427 algorithms: 154 GRASS algorithms (only where QGIS has GRASS installed; the ones that read or write files, take SQL or expressions, or install extensions are left out) and 6 mesh algorithms (export edges, faces, vertices and grid points, rasterize a dataset, surface to polygon). 12 GRASS algorithms and mesh contours failed their live run and are not offered.
- Fixes found by an integration audit: More changes can now be undone with undo_last_operation (layer filter, labels, callouts, diagrams, markers, relief, saved symbols, elevation, time settings). A virtual layer built over a protected layer is now seen by the privacy gate and inherits that protection. Packaging layers offline, adding a chart and setting an atlas now warn when a RESTRICTED or SENSITIVE layer is involved. A plain 'animate the layer over time' is offered the animation tool again.
- Results look better: Continuous raster, GRASS and mesh results (distance, cost, slope-like surfaces, interpolations) open with a colour ramp instead of plain grey; classified and shaded results stay as they are. GRASS buffers, hulls, overlays and network results get the same look as their native counterparts. This was checked by which algorithm gets which look, not by viewing the maps.
- Not hand-tested: Everything above is checked by the offline suite and, for the QGIS parts, by CI on QGIS 4.2.2 (each new tool is read back from real QGIS objects, each Processing algorithm was run once on small test data). None of it has been hand-tested in desktop QGIS, no real model was used to choose these tools, and no real point cloud, vector-tile or 3D-tiles data was opened. Not built: GPS tools, PDAL point-cloud algorithms (this QGIS build has no PDAL) and a 3D map layout item (not available in the CI QGIS).

## What's new in 1.17.0-rc43

Built on 1.17.0-rc42. Offline tests and the QGIS 4.2.2 live checks in CI pass; **not hand-tested** in desktop QGIS unless an item says so. Full list: the `v1.17.0-rc43` block in [metadata.txt](metadata.txt) and [CHANGELOG.md](CHANGELOG.md).

- More QGIS actions by plain request: The approved Processing list grew from 166 to 267 algorithms: 66 raster algorithms (terrain indices, proximity, sieve, fill no-data, warp, translate, grid interpolation, cell-stack and fuzzify tools, zonal tables, constant and random rasters) and 35 more table, analysis and geometry algorithms (X/Y fields, extract by attribute, kernel density heatmap, raster pixels to points or polygons, multi-layer union, intersection and difference, drape lines on a DEM, rasterize, service area from a layer and others). Each was run once in real QGIS 4.2.2 in CI; any that failed there was left off (find projection hangs, line density could not create its raster, shortest path from a layer needs a purpose-built network). A layer list given to a raster-stack algorithm must hold rasters: vector layers there crashed QGIS in a test, so they are now refused before the algorithm runs.
- Edit features, not just values: New tools: set a layer filter, move, rotate and scale features, merge features, split features by a line, undo and redo manual edits on a layer in edit mode, change a field's type, and start, save or discard editing. Anything that changes or removes data shows a preview with exact counts first.
- Open more kinds of data: New tools: add a PostGIS table through a connection saved in QGIS, create a virtual layer (SQL over the project's layers; a single SELECT only), load and save .qlr layer files, and package layers into one GeoPackage for offline use. NetCDF, GRIB, HDF, ECW, MrSID and mesh files (.nc .grb .2dm .slf) are opened when your QGIS build supports them.
- Styling and print layouts: New tools: set a layer's fill, outline, marker and opacity, label style (halo, buffer, placement) and raster style (resampling, brightness and contrast). Layouts: add label, picture, shape, arrow and attribute-table items, edit, move, rotate or remove them, set the map's scale, extent and rotation, change the page size, save and load layout templates, and export to PDF, image or SVG. HTML frames and pictures given as a URL are refused on purpose.
- Project settings: New tools: rename a layer group, zoom to the previous or next extent, read and set layer metadata, snapping options, 1-N relations between layers, time-aware layers and the project time range, and text annotations on the map.
- Showcase services measured: A CI job now records which outside services answer from the build machine. The Copernicus DEM tile and Google News were reached; GDELT answered with a rate limit (HTTP 429) and DuckDuckGo returned no result list. The plugin falls back from GDELT to Google News and says when a service cannot be used.
- Not hand-tested: Everything above is checked by the offline suite and, for the QGIS parts, by CI on QGIS 4.2.2 (each new tool is read back from real QGIS objects and each Processing algorithm was run once). None of it has been hand-tested in desktop QGIS. set_map_view, go_to_bookmark and zoom_history need the real map canvas, which CI does not have. PostGIS was tested against a throwaway server only. ECW and MrSID depend on your QGIS build's drivers and were not tested.

## What's new in 1.17.0-rc42

Built on 1.16.3. Offline tests and the QGIS 4.2.2 live checks in CI pass; **not hand-tested** in desktop QGIS unless an item says so. Full list: the `v1.17.0-rc42` block in [metadata.txt](metadata.txt) and [CHANGELOG.md](CHANGELOG.md).

- Run QGIS tools by name: The approved Processing list grew from 42 to 166 algorithms: 73 geometry tools (densify, smooth, extract vertices, polygons to lines, hulls, boundaries and more), 11 table and selection tools (delete duplicates, drop fields, random extract, join by location summary and others), 35 analysis and creation tools (distance matrix, hub lines, random points, mean coordinates, topological colouring, the 16 geometry checks) and 5 expression tools (extract, geometry and order by expression, autoincrement field, random points inside polygons). New tool find_processing_algorithm searches the list by a few words and returns each algorithm's exact parameters. Each algorithm was run once in real QGIS 4.2.2 in CI; any that failed there was left off. Expression tools refuse env(), file functions and eval() in what the model writes. Algorithms that need file output, a path, or a selection change on your own layer are not on the list.
- Raster calculator: New tool raster_calculator: map algebra with QGIS's own calculator, for example "dem@1" > 100 or ("nir@1" - "red@1") / ("nir@1" + "red@1"). Only numbers, + - * / ^, comparisons, AND, OR, brackets and sqrt sin cos tan asin acos atan ln log10 abs min max are accepted; layers must exist, share a coordinate system and have unique names. The result is a new raster; no input is changed.
- Layers, groups, map view and project: New tools: create an empty layer, add a basemap or a web service layer (WMS, WFS, XYZ), find and repair broken layer paths, assign a layer CRS, save a layer as another format, create layer groups and move layers into them, set the project CRS and properties, set the map view (centre, scale), create and go to bookmarks, and measure a distance.
- Selections and attribute editing: New tools: select all, select by expression, clear selection, set an attribute value, add, rename and delete a field, add a feature from WKT, delete features. Edits go through the edit session so they can be undone. Expressions the model writes are screened: env(), file functions and eval() are refused.
- Hydrology and research: New tool delineate_watershed: from a DEM and an outlet point it derives the basin, longest flow path and outlet, and returns area, stream length, relief, slope and time of concentration, then hands over to the existing peak-flow tool, which still refuses guessed rainfall intensity or runoff coefficient. New tool web_research returns sourced findings; search_web now falls back instead of failing when the search package is missing; find_incident_reports can include news as an opt-in source mapped from place names in headlines.
- Safety net: Every release is now built behind a gate of the offline test suite, a tool-schema snapshot, golden routing requests with size pins, a coverage ratchet over 163 QGIS actions and all 772 registry algorithms, and the replay of 26 recorded sessions. Plain requests that worked before must keep being offered their tools.
- Not hand-tested: Everything above is checked by the offline suite and, for the QGIS parts, by CI on QGIS 4.2.2. None of it has been hand-tested in desktop QGIS. Not verified from the build environment: the Copernicus DEM download behind delineate_watershed, and the live GDELT, Google News and DuckDuckGo responses behind the news source and web_research. set_map_view and go_to_bookmark need the real map canvas, which CI does not have.

## What's new in 1.16.3

Built on 1.16.2. Offline tests and the QGIS 4.2.2 live checks in CI pass; **not hand-tested** in desktop QGIS unless an item says so. Full list: the `v1.16.3` block in [metadata.txt](metadata.txt) and [CHANGELOG.md](CHANGELOG.md).

- Plain requests are offered their tools again: Since 1.16.0-rc23 a short request such as 'create layer for Jordan ADM1', 'zoom to the layer X', 'remove the layer X' or 'export X to CSV' was no longer offered add_layer_from_path, zoom_to_layer, get_layer_extent, remove_layer, export_layer, reproject_layer, clip_layer and the other layer tools: the cost work had removed generic words such as layer, add, create and export from tool matching for every request, and ties were then broken alphabetically. The model never saw the tool and answered that none was available. The discount now applies only to requests of more than 25 words, as designed. Found by replaying 40 plain requests through the router of all 43 releases from rc12 to 1.16.2.
- Boundary tools for ADM codes: 'Jordan ADM1', 'ADM2 districts', 'governorates of Syria', 'admin boundaries' and 'P-code' now offer fetch_geoboundaries and fetch_hdx_admin_boundaries.
- Long requests and raster styling: 'Style the result with a green to red colour ramp' now offers apply_raster_stretch, and 'style them with a pale fill and a grey outline' offers a tool that can change a fill or an outline (neither was offered before). 16 long requests are checked by the new guard.
- QGIS vocabulary and Processing tools: Eight plain phrases that missed their tool now reach it (symmetrical difference, k-means, DBSCAN, reclassify a raster, sample raster values, how many features, categorize the layer, create a grid). Thirteen everyday actions that have no tool (extract vertices, densify, polygons to lines, random points, split layer, raster calculator, polygonize, rasterize, viewshed, basemap, measure and others) now at least get the script fallback and find_tools instead of nothing. All 42 allow-listed Processing algorithms are reachable from a plain request.
- Permanent guards: tests/test_tool_router_basics.py (44 plain and long requests), tests/test_qgis_vocabulary_coverage.py (91 phrases), tests/test_processing_allowlist_routing.py (every allow-listed algorithm) and tests/test_recorded_sessions_replay.py (26 real sessions replayed through the agent loop) fail the build when a change drops a tool a plain request needs. tools/replay_router_across_releases.py repeats the comparison across releases; the audit is in docs/ROUTER_REGRESSION_AUDIT_2026-10-14.md.
- Not hand-tested: All of the above is checked by the offline suite and CI. It checks which tools the model is offered, not what the model then does with them; the 1.16.2 and rc41 fixes (Stop during a model call, honest script edits, raster style kept, template defaults, boundary-failure wording) are also still not hand-tested. The 13 actions without a tool still need a script or a future Processing allow-list entry (owner decision, see the audit note).

## What's new in 1.16.2

Built on 1.16.1. Offline tests and the QGIS 4.2.2 live checks in CI pass; **not hand-tested** in desktop QGIS unless an item says so. Full list: the `v1.16.2` block in [metadata.txt](metadata.txt) and [CHANGELOG.md](CHANGELOG.md).

- No substitute for a failed boundary download: In a Jordan ADM1 request both boundary downloads failed, and the assistant then drew 12 governorate capitals from coordinates it remembered and titled the reply 'Jordan ADM1 Layer Created'. Points are not boundaries and remembered positions are unverified. Every failure message of fetch_geoboundaries and fetch_hdx_admin_boundaries now tells the model not to substitute points, capitals or polygons, to say the download failed and why, and to offer the other source or a boundary file you already have. It is an instruction to the model, not a block: the 'Unverified point positions' flag from rc40 stays as the backstop. Checked by an offline test; not tried against a real model.
- Still failing on some machines: The geoBoundaries file download still fails with 'HTTP Error 500: Domain Not Found' on the machine where it was reported. That points to DNS or a proxy on that machine (issue 305); this release does not change it. If it happens to you, check that github.com opens in a browser and what QGIS has under Settings, Options, Network.
- Same code otherwise: Everything else is 1.16.1 unchanged. The fixes of 1.16.0-rc41 and 1.16.1 (Stop during a model call, honest script edits, raster style kept, template defaults, routing words) are still checked by the offline suite and CI only, not by hand.

## What's new in 1.16.1

Built on 1.16.0-rc41. Offline tests and the QGIS 4.2.2 live checks in CI pass; **not hand-tested** in desktop QGIS unless an item says so. Full list: the `v1.16.1` block in [metadata.txt](metadata.txt) and [CHANGELOG.md](CHANGELOG.md).

- First stable release of 1.16: 1.16.1 is the stable build of the 1.16 line. It contains exactly the code of 1.16.0-rc41 and nothing else: the version number no longer carries 'pre-release'. The 1.16 line adds the audit fixes, the cost and routing work, the incident, earthquake, conflict-event and fact-check tools, point-position flags, and the fixes from the rc37 and rc40 hand tests (rc20 to rc41; full list in CHANGELOG.md).
- What was hand-tested: The rc40 build was hand-tested on Windows with QGIS 4.2.2 and Gemini (67 rows: 42 pass, 14 fail, 11 not run); 19 issues were closed from it and the failures were fixed in rc41 or traced to wrong test rows. Upgrading from rc39 to rc40 was checked by the owner. The rc41 fixes are checked by the offline suite and CI only, including live checks in QGIS 4.2.2.
- Not yet hand-tested in 1.16.1: Stop during a model call, the raster-style follow-up, honest script edits to file layers, task-template defaults, the routing words for access by road, the Memory dialog line and the cloud-card text. The corrected live-test rows for them are in docs/FULL_LIVE_TEST_open_issues_ROWS.csv. Report anything that fails at https://github.com/http-solution/cartogen-ai-qgis-plugin/issues.
- Changes from rc41: None in code. Version number and release text only.

## What's new in 1.16.0-rc41

Built on 1.16.0-rc40. Offline tests and the QGIS 4.2.2 live checks in CI pass; **not hand-tested** in desktop QGIS unless an item says so. Full list: the `v1.16.0-rc41` block in [metadata.txt](metadata.txt) and [CHANGELOG.md](CHANGELOG.md).

- Stop takes effect during a model call: Pressing Stop while the assistant was waiting for the model took 25 to 30 seconds to show, because the wait only ended when the reply did. The wait now checks Stop every quarter of a second, ends the turn as 'Stopped by user' rather than an API error, and does not resend the request. Checked by offline tests only; not tried against a real provider.
- Script edits to file layers are reported honestly: A script works on a copy of a file or database layer, so an edit it made to such a layer never reached the real one, yet the reply said it had. The reply now says the edit was NOT applied and points to an editing tool. Layers a script creates are flagged as temporary (lost when the project closes unless saved or exported). Memory layers still receive same-count edits. Two new live checks run in QGIS 4.2.2 in CI.
- A styled raster stays styled: After the assistant applied a colour ramp to a raster, a follow-up that checks the promised result told it to call a categorized-style tool, and it re-stretched the raster to grey. Styling tools now count as delivering a layer, so no follow-up is sent.
- Task templates state a default only where it is used: A matched task template used to add 'Given: threshold = 5 km', 'imagery = most recent low-cloud scene' or 'population_src = WorldPop' to requests that never mentioned them. A default is now stated only when a tool in the task's chain can use that slot (issue 304, owner decision).
- Routing words for access by road: 'Which facilities are beyond N minutes or km by road' now points the assistant to classify_facilities_by_access, the tool that adds the green reached and red beyond layer, for any number of facilities (the prompt said more than about 200).
- Incident wording, Memory dialog, cloud card, busy chat: find_incident_reports tells the model to say 'reported by', never 'verified'. The Memory dialog says whether notes are saved with the project. The cloud-override card says that layer names, field names, types, CRS and counts always reach the cloud model. A message sent while a reply is running now says it was kept in the box instead of being ignored silently.
- Security scan notes: Bandit's two XML findings (B405, B314) are marked with the reason: both feed parsers refuse any DOCTYPE or ENTITY and cap the size before parsing.
- Not hand-tested: Everything above is checked by the offline suite and CI (including live checks in QGIS 4.2.2) only. Stop latency, the card and dialog text, the raster fix and the routing words need a hand run; the corrected live-test rows are in the bundle.

## What's new in 1.16.0-rc40

Built on rc39. Offline tests, mypy and the QGIS 4.2.2 live checks in CI pass; **not hand-tested** in desktop QGIS. Full list: the `v1.16.0-rc40` block in [metadata.txt](metadata.txt) and [CHANGELOG.md](CHANGELOG.md).

- New tool: search_fact_checks: Answers 'has this claim, video or photo been fact-checked?' from the published feeds of Snopes, PolitiFact, FactCheck.org, Full Fact, Lead Stories and the Arabic-language Fatabyyano (searchable in Arabic). Every reply names the outlets that answered or failed and says that only each outlet's newest 10 to 25 entries are searched, so no match is never evidence that a claim is true, false or unchecked. Reuters, AFP, Africa Check and AP refuse automated requests and cannot be asked. The six feeds were queried live from a development session; not hand-tested in QGIS.
- Point positions the model typed are flagged: Coordinates passed to add_point_layer, add_incident_point or execute_pyqgis_script that appear in neither your message nor an earlier tool result are flagged in the tool result and in the final reply ('Unverified point positions'). This closes the gap noted in rc39. It never blocks, and it cannot see coordinates computed or read from a file inside a script.
- Routes from a depot in another layer: optimize_delivery_route takes additional_stops_layers, so a depot or hub in one layer and the stops in another no longer need scripts to merge them first (rc37 row F3 took 9 calls for 5 stops). Whether the assistant now does it in one call is not yet checked.
- Analysis fields are written through the edit session: Severity score, presence-gap status, population-in-need and damage-severity fields were added straight to the data provider, bypassing the edit buffer, so a failure half-way could not be undone and a layer you were already editing was ignored (issue 293). They now go through the same checked, undoable edit as the other field-writing tools.
- Downloads behind a proxy: A download that follows a redirect (geoBoundaries boundary files do) used urllib for the redirected hop, which does not know a PAC or authenticated proxy that QGIS does. A hop urllib cannot connect to is now retried through QGIS's own network stack. geoBoundaries failures now say whether the lookup or the file download failed, and from which host. The tester's failure on 2026-10-13 is still unconfirmed; this fixes the best-supported explanation.
- Security alerts and documentation site: Fixes for the CodeQL alerts on the website prototype (content security policy, a reflected error message, a log format string), a test server that copied the Host header into a redirect, workflow permissions, and the documentation site's search. The documentation site is live at https://http-solution.github.io/cartogen-ai-qgis-plugin/.
- Not hand-tested: Everything above is checked by the offline suite and CI (including the live checks in QGIS 4.2.2) only. The proxy fix was not tried behind a real proxy, the point-flagging and the depot merge were not tried with a real model, and the rc39 hand-test rows (no invented layer, follow-up, Stop on a long job) are still to run.

## What's new in 1.16.0-rc39

Built on rc38. Offline tests, mypy and the QGIS 4.2.2 live checks in CI pass; **not hand-tested** in desktop QGIS. Full list: the `v1.16.0-rc39` block in [metadata.txt](metadata.txt) and [CHANGELOG.md](CHANGELOG.md).

- No invented records to fill an empty layer: When a request promised a map layer and no layer had been made, the follow-up the plugin sends the model told it to 'generate an operational/representative sample dataset'. In the rc37 hand test (a request to check the internet for incidents near Amman, after every source returned nothing) the model added four invented incidents to the map as a 'planning baseline'. The follow-up now says the opposite: do not invent, sample, simulate or illustrate records; say which sources were tried, what each returned, and that no layer was made because there was nothing real to show. A test fails if the old wording returns.
- Hand-test result for rc37, corrected: Row RC37-A1 of the live test, recorded as a pass by the tester, is a fail for the reason above. Everything else in the rc37 report stands (docs/RC37_LIVE_TEST_REPORT_2026-10-13.md).
- Live-test bundle: The live-test bundle (tools/build_live_test_bundle.py) takes its version from metadata.txt, and its rows no longer name a version.
- Not hand-tested: The fix is checked by the offline suite and CI only. Nothing stops the model from adding made-up points by another route (for example add_point_layer with coordinates it invented); this release only removes the wording that asked for it.

## What's new in 1.16.0-rc38

Built on rc37. Offline tests, mypy and the QGIS 4.2.2 live checks in CI pass for these fixes; they have **not been re-run by hand** in desktop QGIS. rc37 itself was hand-tested on 2026-10-13 (17 of 23 rows passed; see [docs/RC37_LIVE_TEST_REPORT_2026-10-13.md](docs/RC37_LIVE_TEST_REPORT_2026-10-13.md)). Full list: the `v1.16.0-rc38` block in [metadata.txt](metadata.txt) and [CHANGELOG.md](CHANGELOG.md).

- Processing-algorithm tool works again: run_allowlisted_processing_algorithm failed on every call from the assistant since rc24 with "unexpected keyword argument 'params'": a code change had left the tool registered against an internal helper. Found in the rc37 hand test (a follow-up statistics step after a classification). The registration is fixed and a new test checks that every registered tool accepts the arguments it advertises.
- No false 'step did not run' note after incident searches: After find_incident_reports added its layer the chat could still end with 'Expected styled layers ... but the step that writes it did not run', because the tool's name was not recognised as one that creates a layer. It is now.
- rc37 hand test: rc37 was hand-tested on 2026-10-13 against Gemini in desktop QGIS 4.2: 17 of 23 rows passed, 2 were inconclusive (Stop was never exercised against a running job), 2 were not recorded and 2 optional rows were skipped. Report: docs/RC37_LIVE_TEST_REPORT_2026-10-13.md.
- Not hand-tested: The two fixes above are checked by the offline suite and CI only; neither has been re-run in desktop QGIS. Stop during a long-running job is still unproven on real data.

## What's new in 1.16.0-rc37

Built on rc36. Offline tests, mypy and the QGIS 4.2.2 live checks in CI pass; the five sources were queried live from a development session; **not hand-tested** in desktop QGIS and not run with a real model. Full list: the `v1.16.0-rc37` block in [metadata.txt](metadata.txt) and [CHANGELOG.md](CHANGELOG.md).

- New tool: find_incident_reports: Answers 'what incidents, disasters or conflict events happened in <place>' from a fixed list of named sources instead of the open web: GDACS (UN alerts), USGS earthquakes, NASA EONET, UCDP armed-conflict events and the ReliefWeb disasters feed. Every record carries its source, rating, date and link; records with a position become a map layer (ReliefWeb items have no coordinates and are listed). Every reply names the sources that answered, the ones that could not be reached and the ones not searched, so an empty result is not read as 'nothing happened'. UCDP data is preliminary and weeks old. No keys needed. The tool count is now 211.
- What it does not search: News outlets, fact-checkers and social media are not searched: the Reuters, AFP and Full Fact pages cannot be read by a program, Liveuamap is a paid API, ACLED needs a registered key, and social media is out of scope. The reply lists each with its reason.
- search_web points to it: The general web search description now tells the assistant to use find_incident_reports for incident, disaster and conflict questions.
- Not hand-tested: The five sources were queried live from a development session and CI is green, including the live checks in QGIS 4.2.2, but none of this has been hand-tested in desktop QGIS. Whether the assistant chooses the new tool for a plain request such as 'check the internet for incidents' is not yet known.

## What's new in 1.16.0-rc36

Built on rc35. Offline tests, mypy and the QGIS 4.2.2 live checks in CI pass; **not hand-tested** in desktop QGIS, not tried on a large real project and not run with a real model. Full list: the `v1.16.0-rc36` block in [metadata.txt](metadata.txt) and [CHANGELOG.md](CHANGELOG.md).

- QGIS stays responsive during long analyses: Loops over features, pairs and pixels used to run in one unbroken stretch on QGIS's main thread, so QGIS showed Not Responding and ignored Stop. About 90 such loops in the analysis, validation, styling, export and import tools now work in slices of about 50 ms: the window repaints, Stop is heard, and progress is reported every few seconds. A Stop inside an edit rolls the edit back.
- Hub siting, allocation and delivery routes: The distance matrix is built in slices and the ranking, facility selection and route ordering run off the main thread. Route ordering now finds tours about 14 percent shorter on a 200-stop test and runs faster (it used to stop after 2000 trial moves). The route-risk tool merges geometry in one pass and tests incidents against a prepared buffer.
- Large raster classification: unsupervised_classification reads and classifies the raster in blocks, so memory no longer limits its size; a raster over 400 million cells is refused with a clip-it-first message (it used to refuse over 25 million cells).
- Fewer freezes elsewhere: geocode_batch (up to 25 lookups with pauses) no longer runs on the main thread and stops when you press Stop. Scheduled recurring workflows now skip a tick while another one or a chat request is running instead of starting a second analysis on top. The chat window removes the oldest messages once it holds more than 300 items, keeping the newest 200 (the saved conversation is untouched).
- Not hand-tested: CI is green, including the live checks in QGIS 4.2.2, but none of this has been tried on a large real project or hand-tested in desktop QGIS. The size of the speed-up on real data has not been measured, and 300 and 200 for the chat window are estimates.

## What's new in 1.16.0-rc35

Built on rc34. Offline tests and mypy pass locally; the data fetches of the two new tools were run against the live services; **not hand-tested** in desktop QGIS and not run with a real model. Full list: the `v1.16.0-rc35` block in [metadata.txt](metadata.txt) and [CHANGELOG.md](CHANGELOG.md).

- Research requests end with an answer: A request that only reads (a web search, an inspection) never creates or changes anything, so the stall guard used to stop it after six rounds as 'NOT complete' with nothing summarised. Now, when such a turn has gathered results, the model is asked once to answer from them without calling more tools, saying what it found, its sources and what it could not find. A second stall still stops the turn.
- Two new tools: earthquakes and conflict events: fetch_usgs_earthquakes loads recent USGS earthquakes (bounding box, days, minimum magnitude) as a layer coloured by magnitude band. fetch_ucdp_conflict_events loads UCDP Candidate Events (state-based, non-state and one-sided violence) from the open UCDP download, filtered by country, area, dates and deaths. UCDP candidate data is preliminary and weeks old, and every result says so and names the newest event date. Both need no key. The tool count is now 210.
- URL downloads use the QGIS network stack: Downloads of web addresses named by the model, including the humanitarian data downloads, now go through QGIS's network stack (your proxy, authentication and SSL settings apply). Every redirect is still checked against the private-address block before it is followed, one hop at a time, and the key is dropped when a redirect leaves the site.
- Licence notice says GPL version 2 only: The notice in the plugin's root file offered 'any later version'; it now says version 2 only, matching the package metadata and the manifest.
- Not hand-tested: The earthquake and UCDP data fetches were run against the live services from a development session, and CI runs the rest, including the QGIS 4.2.2 live job, but none of this has been hand-tested in desktop QGIS or with a real model. Whether the assistant picks the new tools for plain requests is not yet known.

## What's new in 1.16.0-rc34

Built on rc33. GitHub Actions ran green on the merged head (Ubuntu, Windows, the QGIS 4.2.2 live job and the secret scan); **not hand-tested** in desktop QGIS and not run with a real model or API key. Full list: the `v1.16.0-rc34` block in [metadata.txt](metadata.txt) and [CHANGELOG.md](CHANGELOG.md).

- A refused Gemini request now explains itself: When Google refuses a request, the chat message says what each model answered (the status and Google's own text, for example 'Your project has been denied access'), which API key was sent (its length, last four characters and where it was found: QGIS saved credentials, this session's memory or an old plaintext setting) and, when the reply is not a normal Google error, the server name and size of the reply. Long key-like strings in provider text are blanked and the whole key is never shown.
- Retired Gemini model replaced: Google answers 404 for gemini-2.5-flash ('no longer available to new users, use gemini-3.8-flash'). The fallback list is now gemini-flash-latest, gemini-3.8-flash and gemini-3.7-flash, and Settings offers gemini-3.8-flash.
- No more waiting on a model your plan cannot use: A quota of zero (the free tier has none for the Pro models) is returned at once instead of after a minute of retries, and the plugin moves to the next model. A model refused with 403 is also skipped. When Google denies the whole project, the plugin stops and shows Google's message instead of trying every model. A Google quota error is shown as one sentence (model, free tier, limit, retry time) instead of a screenful of JSON.
- Log lines keep their host names: The redirect and refusal log lines had lost their host fields to the logger's allow-list; host names (never paths, keys or bodies) are now logged.
- Not hand-tested: CI is green, including the live checks in QGIS 4.2.2, but none of this has been hand-tested in desktop QGIS or run against Google. Which key and project Google accepts remains the user's to check in Google AI Studio.

## What's new in 1.16.0-rc33

Built on rc32. GitHub Actions ran green on the merged head (Ubuntu, Windows, the QGIS 4.2.2 live job and the secret scan); **not hand-tested** in desktop QGIS and not run with a real model or API key. Full list: the `v1.16.0-rc33` block in [metadata.txt](metadata.txt) and [CHANGELOG.md](CHANGELOG.md).

- AI requests keep their API key when a server redirects them: If anything between QGIS and a provider (a proxy, firewall or gateway) answered an AI request with a redirect, QGIS's own sender repeated the request without the Authorization header, so the provider refused it with 403. This was reproduced in QGIS 4.2.2 with a local test server. Requests that carry a body or a key now follow redirects inside the plugin: the same method, headers and body on a 307 or 308, a plain GET on 301, 302 and 303, the key kept on the same site and dropped for another, relative targets resolved, at most 5 hops.
- Redirects are logged without secrets: Each redirect writes a log line with the two host names and the status, never the path, key or body, so a later refusal shows whether a redirect was involved.
- Not hand-tested: CI is green, including the live checks in QGIS 4.2.2 against a local test server, but none of this has been hand-tested in desktop QGIS or run against Google, and it has not been confirmed that a redirect is what caused the reported Gemini 403. The reason code and the sender switch added in rc32 remain for that case.

## What's new in 1.16.0-rc32

Built on rc31. GitHub Actions ran green on the merged head (Ubuntu, Windows, the QGIS 4.2.2 live job and the secret scan); **not hand-tested** in desktop QGIS and not run with a real model or API key. Full list: the `v1.16.0-rc32` block in [metadata.txt](metadata.txt) and [CHANGELOG.md](CHANGELOG.md).

- A refused AI request now says why: When Google, OpenAI or another provider answers 401 or 403, the chat message now includes the provider's own short reason code (for example PERMISSION_DENIED, API_KEY_INVALID or SERVICE_DISABLED). The rest of the response is still hidden, because some providers echo part of the key back, and only values that look like a plain code name are shown.
- Switch back to the previous request sender: A Gemini key that worked in a test outside QGIS was refused with 403 when the plugin sent the same kind of request through QGIS's network stack. The cause has not been found. Setting cartogen_ai/hosted_requests_via_qgis to false in QGIS's advanced settings sends hosted AI requests (Gemini, OpenAI, Claude, OpenRouter) the way versions before rc28 did. It is on by default.
- Refusals are logged without secrets: A 401 or 403 on the QGIS path now writes a log line with the host and whether a QGIS proxy is set, never the key, the headers or the response body.
- Not hand-tested: CI is green, including the live checks in QGIS 4.2.2, but none of this has been hand-tested in desktop QGIS, and it has not been confirmed that the switch fixes the Gemini 403.

## What's new in 1.16.0-rc31

Built on rc30. GitHub Actions ran green on the merged head (Ubuntu, Windows, the QGIS 4.2.2 live job and the secret scan); **not hand-tested** in desktop QGIS and not run with a real model or API key. Full list: the `v1.16.0-rc31` block in [metadata.txt](metadata.txt) and [CHANGELOG.md](CHANGELOG.md).

- Metadata matches the QGIS plugin rules: The metadata declared a menu category (Plugins) that the QGIS developer documentation does not allow; it is removed, and the plugin stays in the default Plugins menu.
- Clearer error when QGIS cannot create a temporary layer: 18 places that create a temporary layer now check that QGIS actually created it and report a readable error, instead of failing a line later with a confusing message about a missing data provider.
- Notices appear inside the dialog: Results such as 'exported', 'deleted' and 'failed' in the Memory, Layer Data Sensitivity and account dialogs now show in a message bar inside the dialog instead of a pop-up box. Questions that need an answer, and the warning when an API key is kept for this session only, still use a pop-up.
- Styled layers redraw after score fields are written: After the severity, presence-gap, population and index tools write a field into a layer, the layer is redrawn, so a layer styled on that field no longer shows the old colours until the next refresh.
- Not hand-tested: CI is green, including the live checks in QGIS 4.2.2, but none of this has been hand-tested in desktop QGIS, and the new message bar has been checked only by an automated test, not by eye.

## What's new in 1.16.0-rc30

Built on rc29. GitHub Actions ran green on the merged head (Ubuntu, Windows, the QGIS 4.2.2 live job and the secret scan); **not hand-tested** in desktop QGIS and not run with a real model or API key. Full list: the `v1.16.0-rc30` block in [metadata.txt](metadata.txt) and [CHANGELOG.md](CHANGELOG.md).

- Large downloads and the account client use QGIS's network stack: Geofabrik extracts, model checkpoints and other large downloads are now read through QGIS's network stack, in chunks, so QGIS proxy, authentication and SSL settings apply, progress and cancel still work, and a download cut short is reported as an error instead of leaving a smaller file. The Cartogen account client does the same. Three things still use Python's own HTTP code: a download that answers with a redirect (it is retried through urllib with the QGIS proxy; following the redirect through QGIS failed in testing and the cause was not found), the check that every redirect of a fetched URL is safe (QGIS follows redirects without letting the plugin look at each step), and Ollama (a local server whose answers can take longer than QGIS's 60 second network timeout).
- Scripts do not run without isolation: If QGIS cannot be loaded, the script tool now refuses to run a script instead of running it in the plugin's own process.
- Directory checks reproduced: The plugin directory's own upload rules are now an automated test against the built zip, and the code passes the pyflakes checks (unused re-exports and conditional redefinitions removed).
- Contact address: The project contact address is now cartogenai@gmail.com.
- Not hand-tested: CI is green, including the live checks in QGIS 4.2.2 against a local test server, but none of this has been hand-tested in desktop QGIS, and the new download path has not been run against Geofabrik or any real service.

## What's new in 1.16.0-rc29

Built on rc28. GitHub Actions ran green on the merged head (Ubuntu, Windows, the QGIS 4.2.2 live job and the secret scan); **not hand-tested** in desktop QGIS and not run with a real model or API key. Full list: the `v1.16.0-rc29` block in [metadata.txt](metadata.txt) and [CHANGELOG.md](CHANGELOG.md).

- Replies can no longer forge internal links: A reply (or a layer attribute it quoted) could draw a look-alike Apply edit link that resolved a real pending confirmation, and a quote in a link address could add attributes to the link. Replies can now create only the four chip links (action, export, prompt, zoom); a quote, angle bracket or space in a link address is encoded; and a file link opens only an existing file of a type the tools write (pdf, png, html, csv and similar).
- Limits on remote data: Data fetches no longer read an unbounded answer into memory. JSON and CSV answers are capped at 64 MB, downloads at 1.5 GB, and a gzip tile or zip member that would expand past 256 MB is refused instead of inflated.
- Smaller, cleaner package: The release zip no longer carries hidden files (a build once included a 92 KB .coverage file) or about 70 internal development documents; only the README, user guide, tools reference, humanitarian catalogue and screenshots ship (206 files instead of 288).
- Diagnostics in the QGIS Message Log: Startup, unload and error messages that were printed to the Python console now go to the QGIS Message Log, with the same redaction as every other log line and no exception text.
- Not hand-tested: CI is green, including the live checks in QGIS 4.2.2, but none of this has been hand-tested in desktop QGIS, and no real API key has been used through the QGIS network path.

## What's new in 1.16.0-rc28

Built on rc27. GitHub Actions ran green on the merged head (Ubuntu, Windows, the QGIS 4.2.2 live job and the secret scan); **not hand-tested** in desktop QGIS and not run with a real model or API key. Full list: the `v1.16.0-rc28` block in [metadata.txt](metadata.txt) and [CHANGELOG.md](CHANGELOG.md).

- Warning about an old install: If an install from rc24 or earlier (folder cartogen-ai) is still present next to this one, the plugin now shows a warning when it starts, because both copies would otherwise load together. Delete the old folder and restart QGIS.
- Documentation and Qt6 tidy-up: The README and user guide no longer tell users to pick OpenAI or Claude, which have not been offered since rc25. The label line-placement flags use their scoped Qgis names, and CI confirms they and the QVariant field types exist in QGIS 4.2.2.
- Not hand-tested: CI is green, including the live checks in QGIS 4.2.2, but none of this has been hand-tested in desktop QGIS, and no real API key has been used through the new network path.

## What's new in 1.16.0-rc27

Built on rc26. GitHub Actions ran green on the merged head (Ubuntu, Windows, the QGIS 4.2.2 live job and the secret scan); **not hand-tested** in desktop QGIS and not run with a real model or API key. Full list: the `v1.16.0-rc27` block in [metadata.txt](metadata.txt) and [CHANGELOG.md](CHANGELOG.md).

- AI provider calls use QGIS's network stack: Requests to OpenRouter, Google Gemini and the Cartogen API entry now go through QGIS's own network stack, so QGIS proxy, authentication and SSL settings apply to them. A call waits at most the timeout set in QGIS (Settings > Options > Network, default 60 seconds). Ollama (a local server that can take minutes to answer) and the Cartogen account client still use the requests library. While QGIS's Network Logger panel is open, request headers, including the API key, appear in it on your own machine. This path has been tested in CI against a local server only, not against a real provider.
- Qt6 enum names: The 38 unscoped enum uses the plugin directory's Qt6 check flagged (for example QgsProcessing.TypeVectorPoint) now use the scoped names, and a live test confirms each resolves in QGIS 4.2.2.
- Not hand-tested: CI is green, including the live network and enum tests in QGIS 4.2.2, but none of this has been hand-tested in desktop QGIS or run with a real model or API key.

## What's new in 1.16.0-rc26

Built on rc25. GitHub Actions ran green on the merged head (Ubuntu, Windows, the QGIS 4.2.2 live job and the secret scan); **not hand-tested** in desktop QGIS and not run with a real model. Full list: the `v1.16.0-rc26` block in [metadata.txt](metadata.txt) and [CHANGELOG.md](CHANGELOG.md).

- Network requests use QGIS: Data-fetch tools (OpenStreetMap, HDX, hazard feeds, STAC and the like) now send their requests through QGIS's own network stack, so QGIS proxy, authentication and SSL settings apply. QGIS sets the User-Agent and applies its own network timeout (Settings > Options > Network, default 60 seconds) on these calls. Large downloads (Geofabrik extracts, model checkpoints) are still streamed with urllib, using the QGIS proxy. The AI provider clients still use the requests library; moving them is planned (#71).
- Security scan fixes: Short-key hashes are marked as non-security, a failed restore of the database session's read-only mode is now logged, and the reviewed best-effort handlers carry a reason, so the plugin-directory security scan reports far fewer findings.
- Not hand-tested: CI is green, including the new live network tests in QGIS 4.2.2, but none of this has been hand-tested in desktop QGIS or run with a real model.

## What's new in 1.16.0-rc25

Built on rc24. GitHub Actions runs on every push; **not hand-tested** in desktop QGIS and not run with a real model. Full list: the `v1.16.0-rc25` block in [metadata.txt](metadata.txt) and [CHANGELOG.md](CHANGELOG.md).

- Providers limited to tested ones: Settings and the quick switcher now offer OpenRouter, Google Gemini, Ollama (local) and the Cartogen API entry only. OpenAI and Claude are no longer listed or run, because they were not tested. A provider saved by an earlier version (for example OpenAI) falls back to OpenRouter and its saved key and settings are left untouched. The Cartogen API entry is a stub: no hosted gateway is deployed yet, so it cannot be used until one exists.
- Plugin-directory fixes: metadata.txt now parses (no percent sign), gives the project email and GitHub homepage, states requirements and the data sent to a cloud provider, and the package leaves out hidden git files, sample data and binary documents.
- Opt-in API trace and local layer list: A Settings checkbox (off by default) records every model request and reply to a local file for diagnosing call counts. 'List the layers' is answered in the dock with no model call.
- Plugin folder renamed: Plugin folder renamed: the zip's top-level folder is now cartogen_ai_plugin (a valid Python identifier, which plugins.qgis.org requires) instead of cartogen-ai. If you installed rc24 or earlier, delete the old cartogen-ai folder from your profile's plugins directory, otherwise two copies load.
- Not hand-tested: CI is green, but none of this has been hand-tested in desktop QGIS or run with a real model.

## What's new in 1.16.0-rc24

Built on rc23. GitHub Actions ran green on the merged heads (Ubuntu, Windows, the QGIS 4.2.2 live job with a real PostGIS server, and the secret scan); **not hand-tested** in desktop QGIS and not run with a real model. Full list: the `v1.16.0-rc24` block in [metadata.txt](metadata.txt) and [CHANGELOG.md](CHANGELOG.md).

- Replies checked against tool results: A reply is footnoted when it names an identifier no tool returned (District_4), gives a total, mean or preliminary figure that matches no tool result, or says a style was applied when no styling call succeeded (#228). These are wording checks, not a fix for the model inventing values.
- Guessed file paths: After two 'file not found' errors in a row the agent is told once to stop guessing and use a path you gave or a tool returned, or ask you (#231).
- Less freezing: Approved native Processing algorithms (buffer, clip and the like) now run in the background with Stop available, except ones that change your own layer. The raster tools use GDAL algorithms, which crashed the CI job when run on a worker thread, so they and contours, task-grid statistics and some logistics steps still run on the main thread (#221 is only partly done).
- Safer scripts and SQL: Database and web layers are read-only inside the script worker (#220), and the result layer of execute_read_only_sql cannot be edited (#151). A read-only database role is still the real guarantee for SQL.
- Not hand-tested: CI is green, but none of this has been hand-tested in desktop QGIS or run with a real model.

## What's new in 1.16.0-rc23

Built on rc22. GitHub Actions ran green on the merged head (Ubuntu, Windows, the QGIS 4.2.2 live job and the secret scan); **not hand-tested** in desktop QGIS, and no real model has yet run `run_steps`, the chains or the request queue. Full list: the `v1.16.0-rc23` block in [metadata.txt](metadata.txt) and [CHANGELOG.md](CHANGELOG.md).

- Cost: every model call is measured (provider-reported input, cached and output tokens, latency, tools offered; estimates are labelled and kept apart) and each reply's footer shows what the request used. A loop guard stops a turn that repeats an identical call, fails three times in a row or makes no progress, and says what was done. A per-turn token budget (default 450,000, a provisional figure taken from the rc22 hand-test logs; 0 = no limit; Settings) stops a request BEFORE a call that would pass it and reports what finished.
- Routing: the tools a request needs are chosen from the data sources and actions it names (OpenStreetMap, HDX, buffer, clip, slope, contours and so on) instead of weak word matches, with find_tools for a step the offered list did not cover. A task that names one hazard (drought, extreme heat) only matches when the request names it. Several separate requests pasted together are shown as a queue and run one at a time after you confirm.
- New tools: split_lines_by_zones (a road or highway split by exclusion zones, with total passable length AND longest continuous passable segment, ellipsoidal), generate_contours, and fetch_dem (Copernicus DEM GLO-30, about 30 m, no account needed; a surface model, not bare earth; the result records source, tiles, date and datum and returns the licence's required notices). Print layouts and PDFs are NOT stamped with the Copernicus notice: add it yourself when you publish.
- Fewer model round trips: run_steps lets the model send up to 8 tool calls in one step, checked against the open project before anything runs (layers exist and are the right kind and geometry, no buffering a geographic-CRS layer, numeric style fields) and stopped at the first error or pending confirmation. Eleven vetted chains (exclusion-zone split, buffer then clip, coverage gap, outside distance, terrain contours, terrain slope, clip DEM then slope, clip-style-zoom, reproject then export, population exposure, admin boundary validation) are offered when a request names all their steps, with a project check that binds layers and suggests the UTM zone. The coverage-gap chain is a straight-line distance gap only, not a service gap.
- Evidence (off by default, Settings): each request can write a folder with every tool call's real arguments, results, timings and layers created, copies of written files with SHA-256, and a canvas screenshot. It stores raw values, unlike the logs, so check it before sharing.
- Fixes from the rc22 hand test: a relative output path is anchored to the saved project's folder and the reply names the full path; export_layer writes a GeoTIFF for a raster; a print layout map follows the canvas rotation; 'show the severity on the map' no longer asks which hazard; after a confirmed Apply edit the 'show it on the map' part runs; a project change drops the previous plan so a plain 'Yes' cannot resume it; apply_graduated_style accepts color_from and color_to; 'cluster ... into N groups' reaches unsupervised classification.
- Fixes after that: a natural 'Yes, proceed.' at the preview now runs the original request; when a tool hands over its map hint and the request asked to see the result, the agent asks once for the styling call, and point layers are lifted above polygon layers that cover them; a layout built over JIAF-support results carries the 'not the JIAF method, not endorsed by OCHA or the IASC' statement; people-in-need legends say 'people' and a value exactly on a class limit now draws in the class its label gives.
- Verification: GitHub Actions ran green on the merged head (Ubuntu with Python 3.10 and 3.11, Windows, the QGIS 4.2.2 live job with PostGIS, and the gitleaks scan), and the live tests reproduced the preview-reply fix before fixing it. NOT hand-tested in desktop QGIS: every item above, and no real model has yet run run_steps, the chains or the request queue. Open and not fixed: invented or wrong facts in replies (model behaviour, issue 228), reply-wording requirements (issue 229), legend entries hidden under opaque polygons (issue 165). No issue is closed by this build.

## What's new in 1.16.0-rc22

Built on rc21; verified offline and in a local QGIS 4.2.2 run (GitHub Actions did not run), **not by hand**. Full list: the `v1.16.0-rc22` block in [metadata.txt](metadata.txt) and [CHANGELOG.md](CHANGELOG.md).

- Fix: a result that replaces a layer of the same name no longer overwrites a layer you made yourself. Plugin results are marked as the plugin's own; a same-named layer of yours is set aside (renamed) and the reply says so (rc20 audit A02).
- Fix: feature extraction from imagery only outlines the detected object, not the surrounding background (A01), and a rotated or non-square mask keeps its true geometry (A10).
- Fix: a long-running agent turn that was stopped or superseded can no longer deliver a stale result or act after the project changed (A04); the data-egress gate now follows layer lineage through renames and duplicates, so a derived layer keeps the protection of its source (A05); feature edits report a refused commit or delete instead of claiming success (A03).
- Fix: histogram equalisation no longer turns the lowest valid pixels into NoData: valid cells are 1-255 and 0 is NoData only (A09). Slope and hillshade on a projected DEM in feet convert metres into the DEM's own units (A11). GeoJSON export is RFC 7946: WGS84 coordinates, no legacy crs member (A12). A failed CRS transform is now an error instead of zooming or building a layout in the wrong place (A13).
- Safety: the isolated script worker (execute_pyqgis_script) receives COPIES of file-backed layers, so a script cannot modify your files; edits it makes to such a layer are discarded. Database and web-service layers have no file to copy and remain writable by a script (A06, issue 220).
- Memory: classification refuses rasters over 25 million cells or 60 million cell-band values (A15). Abandoned background-analysis objects are released once their task finishes (A16). The plugin's last-resort import bootstrap removes only its own modules (A18).
- Responsiveness: zonal_statistics (zones of 200 or more) and the model and outline steps of extract_features_from_imagery run off the GUI thread and honour Stop. Every other expensive tool still blocks QGIS while it runs (A14, issue 221 stays open).
- Verification: the full local run passed on the audit-fix build (offline suite, ruff, zip check, 360 QGIS 4.2.2 live tests against PostGIS). NOT hand-tested: every fix above. Imagery extraction needs the FastSAM model and was not run live. GitHub Actions did not run (account billing), so the Windows job and the gitleaks scan did not run. No audit issue (220-224) is closed by this build.

## What's new in 1.16.0-rc21

Built on rc20; verified offline and in a local QGIS 4.2.2 run (GitHub Actions did not run), **not by hand**. Full list: the `v1.16.0-rc21` block in [metadata.txt](metadata.txt) and [CHANGELOG.md](CHANGELOG.md).

- Fix: manual class boundaries passed to apply_graduated_style must be finite, distinct numbers inside the field's own range. A boundary of 100 for values 5-15 used to make an inverted "100 - 15" class and a legend that matched nothing (rc20 hand test, #165); it is now an error that names the data range.
- Fix: the north arrow on a print layout is linked to the map, so it turns with a rotated map. In rc20 it stayed at 0 degrees on a map rotated 30 degrees (rc20 hand test, #165). Checked in real QGIS 4.2.2: the new test fails on the old code and passes on this one.
- Fix: a short pasted fragment shaped like key: value (for example "template: access_map") can no longer make the agent create, change, delete or export anything. In the rc20 hand test a real model called get_layers and create_print_layout for that fragment alone and left a layout behind (#130). The agent may still read the project and ask what you want. Natural short replies ("yes", a layer name, "EPSG:3857" after a question) and any turn with a confirmation card pending are not affected.
- Dev: tools/local_ci.sh runs what the CI workflow runs on a developer machine (offline suite, byte-compile, ruff, release zip check, and the QGIS 4.2.2 live job with PostGIS in Docker). It does not cover the Windows job or the secret scan.
- Verification: the full local run passed (3,669 offline tests, ruff, zip check, 345 QGIS 4.2.2 live tests against a real PostGIS server). NOT hand-tested: every fix above. The stray-fragment gate was tested with fakes at the tool-dispatch layer, not against a real hosted model. GitHub Actions did not run for this build (account billing), so the Windows job and the gitleaks scan did not run. No audit issue is closed by this build.

## What's new in 1.16.0-rc20

Built on rc19; tested offline and in CI on QGIS 4.2.2 (including a real PostGIS server), **not by hand**. Full list: the `v1.16.0-rc20` block in [metadata.txt](metadata.txt) and [CHANGELOG.md](CHANGELOG.md).

- Fix (rc19 regression): a PostGIS read-only query left the shared QGIS database connection read-only for everything else that used it, because the guard set the session read-only and never put it back. It now reads the previous mode, runs the guard and restores it on every path. Found by the first CI run against a real PostGIS server (#151).
- Fix: raster arithmetic on mismatched grids (NDVI, NDWI, NDRE, weighted overlay, change detection) warps the other rasters onto the first raster's grid into temporary files and says so; project layers are not touched (#153). DEM vertical unit is an argument ('m', 'ft', 'us_ft') on elevation_profile, slope_analysis and build_composite_impedance_field (#154). A population raster named like a density raster is refused until raster_unit says people_per_km2 or people_per_cell (#160).
- Fix: severity, presence-gap, population-in-need and damage-exposure tools label units uniquely and write each score to its own feature instead of collapsing same-named units (#159); incident and footprint points are moved into the admin CRS before assignment (#161).
- Fix: a task or function that finishes after the plugin was unloaded no longer calls back into the destroyed UI (#167). The standard print-layout legend lists only layers that meet the map, and right and top graticule labels that were clipped by the legend frame are hidden (rc18 hand test R7/N8).
- Fix: renaming a protected layer, or giving an open layer the same name, no longer lets a layer derived from it look open to the cloud-egress gate. Lineage now also records source layer ids, and a name shared by several layers takes the strictest level (#150).
- Fix: scheduling a stored workflow (schedule_recurring_workflow) is treated like running one: with a cloud provider it needs the same override, because each tick posts results into the chat the model reads next (#149).
- Fix: estimate_road_speeds, add_incident_point, add_named_points and the NASA FIRMS, EONET and GDACS layer refresh reported success when the provider refused the save, and committed edits you had pending on the same layer. A refused save is now an error that keeps the previous contents, and a layer you are editing stays in your own edit session (#144, #143).
- Fix: a roads layer with a few segments that have no direction (NULL or empty) was no longer recognised as the Geofabrik F/T/B encoding, so every one-way street was routed as two-way. Blank directions are ignored when the encoding is detected (#132). Two dashboards with one title in one second no longer overwrite each other (#158).
- CI: the live job now starts a PostGIS 16 server and runs the read-only SQL tool against it, plus new live tests for edit-session undo, project switching, lineage, admin-boundary styling and the population ramp.
- Verification: offline suite, ruff and the QGIS 4.2.2 live job (including PostGIS) pass. NOT hand-tested: every fix above. The rc19 sheet's rows V, T, J and P and the rc18 hand-test findings are still unverified in a desktop session. No audit issue is closed by this build.

## What's new in 1.16.0-rc19

Built on rc18; tested offline, **not by hand**. Full list: the `v1.16.0-rc19` block in [metadata.txt](metadata.txt) and [CHANGELOG.md](CHANGELOG.md).

- Fix: a polite yes now confirms a task card ("Yes, proceed.", "Yes please", "ok go ahead"). In rc18 only a bare "yes" did, so the reply went to the model as a new message and the card was lost (rc18 hand test R2). A reply with extra content ("yes but use the roads layer") is still an edit, and destructive confirmations keep their strict wording.
- Fix: the imagery model checkpoint is downloaded with a plain whole-file request into the weights folder (no Range header, so HTTP 416 cannot happen; a short file is never accepted) before the ultralytics downloader is tried (rc18 R3 failed with 416 after 357 s). The real asset was checked: a plain request returns it complete (23,851,578 bytes).
- Fix: after you press Stop, or when a tool failed in the turn, no follow-up turn asks the model for a report you did not request. "Report the model used and the count" (report as a verb) no longer makes a report file the deliverable; "write a report" still does (rc18 R3, N5).
- Fix: task matching. A request that names a loaded raster no longer gets "imagery = most recent low-cloud scene" assumed, and a tool you name leads the suggested tool chain.
- New: get_layer_extent returns a layer's (or the map view's) extent in its own CRS and in WGS84, with the box in both orders named (south-west-north-east for OSM and building footprints, west-south-east-north for the STAC search). A prompt rule tells the model never to write a bounding box from memory. In rc18 the model passed a Damascus box for a fixture in Jordan to the STAC and building-footprint tools (N4, N5).
- Fix: a result drawn by apply_humanitarian_look is lifted above raster layers that were hiding it (rc18 N2), and the Layers panel legend is refreshed after a raster colour ramp (rc18 R4). The layer is only moved, never hidden or deleted; a layer inside a group is left alone.
- Fix: a web link inside a table cell (a STAC thumbnail) is no longer turned into a broken file link by the output-path matcher (rc18 N4).
- Docs: the rc18 live smoke report as received, with its triage (docs/RC18_LIVE_SMOKE_REPORT_2026-10-06.md, docs/RC18_SMOKE_TRIAGE_2026-10-06.md) and a re-test sheet for this build (docs/SMOKE_RUN_SHEET_rc19_2026-10-06.md).
- Verification: offline suite and ruff pass. NOT hand-tested: every fix above. NOT run in CI at the time of writing: the new live tests (renderer looks, lift above rasters). Rows V, T, J and P of the rc18 sheet were not executed in the rc18 hand test, so the new JIAF, IPC/INFORM/UNOSAT and plain-language changes are still unverified in a desktop session. No audit issue is closed by this build.

## What's new in 1.16.0-rc18

Built on rc17; tested offline and in CI on QGIS 4.2.2, **not by hand**. Full list: the `v1.16.0-rc18` block in [metadata.txt](metadata.txt) and [CHANGELOG.md](CHANGELOG.md).

- Fix: a fresh full request typed while a clarification question is open no longer gets pasted under the old request as "Details: ...", which ran the old request with the new one underneath. This was behind the wrong clarification questions, previews and the unrelated OpenStreetMap offer in the rc15/rc17 smoke runs. Short answers behave as before.
- Fix: after you click Apply edit on a confirmation card, a request with more than one step ("write the score, then style the layer") resumes once, up to three times per request. Before, it stopped after the confirmed step.
- Fix: a short follow-up such as "EPSG:3857" keeps the tools the previous turn used (at most six, for two turns), so the CRS question can finally be answered with the point being placed (the rc16 retry could not work because the tool was not in the turn's tool list).
- Fix: the reply guard no longer reads metres as millions ("886.49 m" was footnoted as general knowledge), and no longer deletes a table whose rows are found in the tool results just because an unrelated call failed.
- Fix: task matching. A request that names a tool is only matched to a task that uses it; a weak cross-section tie (under 25% keyword coverage) and a single shared word in a long request give no directive; a request that names a loaded layer is not asked "Which facility or service type?"; hub, depot, site and similar words answer that question. The register's own task descriptions match as often as before (453 and 466 of 748, pinned by a test).
- Fix: exporting over a non-empty file the plugin did not write (or one changed since) now asks for confirmation (export_to_csv, export_layer). Hub siting, allocation, route stops and travel-time origins label results with the layer's name field instead of the GeoPackage id. save_project lists temporary layers that come back empty. Raster colour ramps keep their range after a save. buffer_analysis accepts output_name.
- Fix: extract_features_from_imagery downloads its model checkpoint on a background thread (QGIS no longer stops responding for the download), removes a partial file after a failure and retries once, and never prints the signed download URL. Web searches for the latest or current thing carry today's date; script-sandbox "Algorithm not found" errors name the real tools; the agent is nudged once when a tool you named is still not called after four other calls.
- Docs: the rc15 and rc17 live smoke reports as received, their triage, and a re-test sheet for this build (docs/SMOKE_RUN_SHEET_rc18_2026-10-06.md).
- Verification: offline suite and ruff pass; the live-QGIS tests passed in CI on QGIS 4.2.2 (PRs #204-#206). NOT hand-tested: the chat flow, task matching and the CRS retry in a real conversation, the continuation after Apply edit, and the imagery download with a real model. No audit issue is closed by this build.

## What's new in 1.16.0-rc17

Built on rc16; tested offline and in CI on QGIS 4.2.2, **not by hand**. Full list: the `v1.16.0-rc17` block in [metadata.txt](metadata.txt) and [CHANGELOG.md](CHANGELOG.md).

- Fix: a request that names a tool ("Use optimal_hub_siting ...", "Run extract_features_from_imagery ...") is only matched to a registered task that uses that tool; otherwise it is sent as typed. In rc15 such requests were matched to unrelated OpenStreetMap export or download tasks and the injected tool list steered the model away (smoke report D01).
- Fix: hub siting, location allocation, route stops and travel-time origins label their results with a name-like field (name, label, title, *_name) instead of the first attribute. On a GeoPackage the first attribute is the primary key, so hubs came back as "1", "2", "3" and the model had to guess which was which (D03). The distances themselves were already correct.
- Fix: save_project lists temporary (memory) layers and warns that they come back empty when the project is reopened (D07).
- Fix: pseudo-colour rasters record their stretch range on the renderer; saved projects had classificationMin/Max = nan and the reopened legend read nan (D08).
- Fix: a failed FastSAM model download no longer prints the signed download URL and says what to do about a partial checkpoint (HTTP 416) (D06). The download still blocks QGIS while it runs; that is not fixed.
- Docs: the rc15 installed-profile smoke report as received and a per-defect triage (docs/RC15_LIVE_SMOKE_REPORT_2026-10-06.md, docs/RC15_SMOKE_TRIAGE_2026-10-06.md). Still open there: no follow-up model turn after Apply edit (D05, needs a decision), the main-thread model download, requests in a cross-section tie that name no tool, D09 and D10.
- Verification: offline suite and ruff pass; the live-QGIS tests passed in CI on QGIS 4.2.2 (PR #204), including new live tests for the raster range and the hub-siting labels and distances. Model-dependent behaviour (task matching in a real chat, the CRS retry from rc16) and the print layout have NOT been hand-tested; no audit issue is closed by this build.

## What's new in 1.16.0-rc16

Built on rc15; tested offline and in CI on QGIS 4.2.2, **not by hand**. Full list: the `v1.16.0-rc16` block in [metadata.txt](metadata.txt) and [CHANGELOG.md](CHANGELOG.md).

- Fix: list-returning tools (get_layers, get_attributes) were reported as "Execution failed unexpectedly." since rc12 (a dict-only check in the main-thread wrapper added with audit item #138). Found in the rc15 hand test; they return their results again, confirmed by a new live test in CI on QGIS 4.2.2.
- Fix: when the CRS question for point coordinates (#119) was answered, the model made no tool call and pasted a script instead. The "ask" result now says how to retry and the prompt rule spells it out. Depends on the model; needs a hand re-run.
- Fix: a print layout zoomed to a one-point layer had a zero-size extent ("Scale unavailable", "Invalid scale!", a map stuck on "Rendering map"). The extent is padded around the point (about 2 km, a guess, not a measured value); an empty layer keeps the old fallback. Needs a hand re-run.
- Internal: one tool-result contract (core/agent/tool_result.py) replaces scattered dict checks, and the CI live-test job discovers tests/test_*_live.py by name (a module that does not run must be listed with a reason). test_agent_live is excluded with its reason stated.
- Docs: a blank run sheet for the live smoke test (docs/SMOKE_RUN_SHEET_rc15_2026-10-05.md).
- Verification: offline suite and ruff pass; the live-QGIS tests passed in CI on QGIS 4.2.2 (PR #202). The B1 retry and the layout fix have NOT been hand-tested; no audit issue is closed by this build.

## What's new in 1.16.0-rc15

Built on rc14; tested offline and in CI on QGIS 4.2.2, **not by hand**. Full list: the `v1.16.0-rc15` block in [metadata.txt](metadata.txt) and [CHANGELOG.md](CHANGELOG.md).

- New: when a service-area run replaces a same-named result layer that was built with different parameters (strategy, travel cost, speed or direction field, default speed, road layer), the tool result lists what changed and the reply must say so (issue #130, point 3). An identical re-run and layers made before this change stay silent. It reports after the replacement and does not ask first; only the service-area layers record their parameters so far (optimize_delivery_route and the access reach polygons are unchanged).
- Docs: a per-issue hand-verification checklist (docs/ISSUE_VERIFICATION_CHECKLIST_2026-10-05.md) and a corrected README audit-status line (#151 needs a database; #152-#168 addressed in work packages 1-6, some with parts still open; all 32 audit issues stay open until hand-verified).
- Unchanged from rc14: the JIAF 2 analysis-support tools. Flag-formula comparison still awaits the owner's closure and the Annex 4 reader is still an unsupported optional format; do not describe the result as a faithful or complete JIAF implementation.
- Verification: offline suite and ruff pass; the QGIS-side code ran in CI on QGIS 4.2.2, including the new live test for the replacement warning. Nothing in rc15 has been hand-tested in a desktop session, and no audit issue is closed by this build.

## What's new in 1.16.0-rc14

Built on rc13; tested offline and in CI on QGIS 4.2.2, **not by hand**. Full list: the `v1.16.0-rc14` block in [metadata.txt](metadata.txt) and [CHANGELOG.md](CHANGELOG.md).

- New: JIAF 2 analysis support (HX5), eight tools -- import_jiaf_inputs, record_jiaf_setup, get_jiaf_setup, compute_jiaf_preliminary, record_jiaf_decisions, get_jiaf_decisions, finalize_jiaf_results, compute_jiaf_patterns. Support for people running the JIAF 2 process: NOT the JIAF method, not endorsed by OCHA or the IASC, and nothing is a final figure. They read sector inputs (OCHA Worksheet 3A/3B read through its Excel tables, HXL tables), compute the preliminary joint PiN (highest sector, never summed or averaged), preliminary severity and the PiN and severity flags, record the multi-partner group's decisions in the project, and keep the preliminary result, review status, final result and justification apart. Intersectoral severity is per unit; there is no national severity.
- New: the flag rules are OCHA's own worksheet formulas (profile ocha_worksheet_2026, read from the official example and template workbooks): ranks of distinct values, a tie for the highest switches flags 2 and 3 off, flag 1 at two missing-or-zero sectors, flag 6 in two parts, and the worksheet's rule that the preliminary PiN is the highest PiN only where severity is above 2. Thresholds come from the workbook's Thresholds cells, else the template defaults, and every result says which. The older reading of the manual is kept as profile manual_reading, comparison only.
- New: incomplete sector coverage is never turned into phase 1 (the unit has no preliminary severity, with lower and upper bounds); missing and zero PiN stay distinct; bulk closure of flags needs a recorded rationale; published final values are shown beside, never over, the calculated ones; blank outcome evidence is not assessable, not passed.
- Change: the Annex 4 sector-template reader is an explicit UNSUPPORTED optional format (implemented from the manual's screenshots, never auto-detected, compatibility unverified).
- Not closed: flag 6 on real output, a zero third-highest PiN in flag 3 (from the formula text, no cached example row), the header/formula mismatch of severity flag 4, a real country's thresholds, and the Yemen analysis team's own flag decisions. Do not describe the result as a faithful or complete JIAF implementation.
- Verification: offline suite and ruff pass; the QGIS-side code ran in CI on QGIS 4.2.2 (live tests written without a local QGIS). The check against OCHA's example workbook (all flag columns, severity and preliminary PiN of its 6 units) and against the Yemen worksheet was run locally; those workbooks are not committed. Nothing in rc14 has been hand-tested in a desktop session, and no audit issue is closed by this build.

## What's new in 1.16.0-rc13

Built on rc12; tested offline and in CI on QGIS 4.2.2, **not by hand**. Full list: the `v1.16.0-rc13` block in [metadata.txt](metadata.txt) and [CHANGELOG.md](CHANGELOG.md).

- New: automatic humanitarian map looks (HX1) -- apply_humanitarian_look draws severity (five classes matching the tool's own), people-in-need / exposure (quantile classes, zero its own class), presence-gap and rank results; the analysis tools return a map_look hint; footprints, OSM layers, roads and detected features get humanitarian styles; a situation-report layout.
- Change: the humanitarian task register was corrected (HX2) -- the new H1-H6 tools are attached to the tasks they serve, and a coverage test keeps every non-guidance task tied to a tool that can acquire its data.
- New: calculate_allocation_envelope (HX3a) -- splits a budget you supply over areas by need (optionally x population) with ceiling, floor, need threshold and rounding; areas with missing values are excluded and listed, never imputed; an advisory calculation, not a recommendation of who should receive what.
- New: import_humanitarian_table (HX3b) -- file-based import and validation of IPC phase, INFORM Risk and UNOSAT damage tables with a P-code join to an admin layer. UNVERIFIED: the recognised column names were not checked against real HDX files; the result shows the mapping used and an explicit mapping overrides it.
- New: analyze_critical_links (HX3c) -- screens a road network for bottlenecks (how much origin-to-destination demand has its shortest path through each segment). A screening of dependence, not a closure simulation or traffic forecast. Performance on a national network has not been measured.

## What's new in 1.16.0-rc12

A pre-release; every item below was tested offline and, for the QGIS-side code, in CI on QGIS 4.2.2 -- **not yet by hand** in a
desktop session. The full list is the `v1.16.0-rc12` block in [metadata.txt](metadata.txt) and [CHANGELOG.md](CHANGELOG.md).

- **Six new humanitarian tools**: `apply_network_barriers`, `evaluate_forecast_trigger`, `generate_mapping_task_grid`,
  `design_sampling_frame`, `calculate_mcda_ranking`, `aggregate_survey_indicator` -- see [Humanitarian tools](#humanitarian-tools).
- **Hydrology engineering tools**: `parse_dms_location`, `assess_watershed_hydrology_request` and
  `calculate_rational_watershed_peak_flow`. They refuse to invent a DEM, rainfall intensity or runoff coefficient and do **not**
  delineate a watershed ([docs/HYDROLOGY_ENGINEERING_TOOLS_2026-10-04.md](docs/HYDROLOGY_ENGINEERING_TOOLS_2026-10-04.md)).
- **Audit hardening (issues #137-#151)**: no code execution through Processing parameters; owned, checked edit sessions that never
  commit a layer you are editing; SI-unit area/length and ellipsoidal distances; safer script-isolation results; the cloud egress
  gate and layer lineage now see SQL, workflow and list-valued arguments; a running request stops and writes nothing if you switch
  project; read-only SQL fails closed.
- **Honesty guard** (#75): a footnote when an answer contains place names, large totals, file sizes or terrain claims that no tool
  result or user message supports. A heuristic over three claim shapes, not a fact checker.
- **Routing and map polish**: faster two-stop routes, `strategy='fastest'` for delivery routes with an estimated time, one-way road
  codes honoured, readable defaults for task grids, barrier segments, hazard alerts and before/after difference rasters, and
  `tidy_project_layers` to clean up projects made by older builds.

## Humanitarian tools

The humanitarian tools follow the six workflows in the "Humanitarian Mapping Workflows" document: field operations first, then
strategic orchestration. The full catalogue -- what each tool does, what it draws on the map, and how to get better results -- is
in [docs/HUMANITARIAN_TOOLS_CATALOGUE.md](docs/HUMANITARIAN_TOOLS_CATALOGUE.md); exact arguments are in
[docs/TOOLS_REFERENCE.md](docs/TOOLS_REFERENCE.md), and what is still missing is in
[docs/HUMANITARIAN_WORKFLOW_GAP_ANALYSIS_2026-10-04.md](docs/HUMANITARIAN_WORKFLOW_GAP_ANALYSIS_2026-10-04.md).
1.17.0-rc42, 1.17.0-rc43 and 1.17.0-rc44 added tools outside these workflows (see their notes and `docs/TOOLS_REFERENCE.md`), so none is marked **new** here; the newest are `search_fact_checks` (1.16.0-rc40) and `find_incident_reports` (1.16.0-rc37), tested offline and in CI on QGIS 4.2.2 and, for the rc37 tool, in the rc40 hand test.

| Workflow | Tools |
|---|---|
| **1. Rapid crisis and base mapping** | `search_hdx_datasets`, `fetch_hdx_admin_boundaries`, `fetch_geoboundaries`, `fetch_osm_features`, `ingest_osm_features`, `fetch_building_footprints`, `search_stac_satellite_imagery`, `calculate_raster_change_detection`, `calculate_damage_exposure_severity`, `extract_features_from_imagery`, `add_incident_point`, `add_point_layer`, `generate_mapping_task_grid`, `import_humanitarian_table` |
| **2. MSNA and field data** | `design_sampling_frame`, `fetch_worldpop_population`, `estimate_population_exposure`, `load_tabular_data_as_layer`, `extract_pdf_tables`, `extract_word_tables`, `aggregate_data`, `aggregate_survey_indicator` |
| **3. Logistics, routes and catchments** | `estimate_road_speeds`, `build_composite_impedance_field`, `apply_network_barriers`, `calculate_service_area`, `classify_facilities_by_access`, `travel_time_matrix`, `population_access_gap`, `optimal_hub_siting`, `location_allocation`, `optimize_delivery_route`, `score_route_incident_risk`, `analyze_critical_links` |
| **4. Severity mapping (JIAF-style)** | `calculate_severity_index`, `calculate_presence_gap`, `load_3w_data`, `calculate_population_in_need`, `hotspot_analysis`, `analyze_incident_trend`, `forecast_trend`, `import_jiaf_inputs`, `record_jiaf_setup`, `get_jiaf_setup`, `compute_jiaf_preliminary`, `record_jiaf_decisions`, `get_jiaf_decisions`, `finalize_jiaf_results`, `compute_jiaf_patterns` |
| **5. Allocation and prioritisation** | `calculate_mcda_ranking`, `fetch_fts_funding_data`, `generate_sector_coverage_report`, `weighted_overlay_analysis`, `calculate_allocation_envelope` |
| **6. Anticipatory action** | `evaluate_forecast_trigger`, `fetch_gdacs_disaster_alerts`, `fetch_nasa_eonet_events`, `fetch_usgs_earthquakes`, `fetch_ucdp_conflict_events`, `find_incident_reports`, `search_fact_checks`, `fetch_nasa_active_fires`, `generate_situation_dashboard`, `run_monitoring_workflow`, `schedule_recurring_workflow`, `stop_recurring_workflow`, `list_scheduled_workflows` |
| **Data quality and governance** | `check_pcode_uniqueness`, `check_pcode_hierarchy`, `validate_schema`, `list_schema_contracts`, `get_dataset_status`, `set_dataset_status`, `advance_dataset_status`, `get_provenance_record`, `write_provenance_sidecar`, `set_layer_sensitivity`, `get_layer_sensitivity`, `generate_map_product_qa_checklist` |
| **Reporting and products** | `generate_chart`, `generate_html_dashboard`, `generate_temporal_dashboard`, `generate_spatial_report`, `generate_report`, `apply_humanitarian_look` |
| **Engineering hydrology** | `parse_dms_location`, `assess_watershed_hydrology_request`, `calculate_rational_watershed_peak_flow` |

Where a number is a judgement call -- a trigger threshold, criteria weights, a design effect, a minimum survey cell size -- the tool
asks you for it and repeats it in the result instead of choosing one.

## Editions

This is a free, GPL v2 open-source project — everything in this README and in
[docs/TOOLS_REFERENCE.md](docs/TOOLS_REFERENCE.md), no account or license key required. It runs fully
offline via a local Ollama server, or with any cloud provider using your own API key. Nothing in this
repository is tier-gated.

## Installation

**From the release zip** (recommended). The current build is the
[1.16.0-rc37 pre-release](https://github.com/http-solution/cartogen-ai-qgis-plugin/releases/tag/cartogen-ai-v1.16.0-rc37); the release
also carries a `SHA256.txt` file to check your download against. It is a pre-release, so expect rough edges and report
them as issues.
1. In QGIS: `Plugins` → `Manage and Install Plugins…` → `Install from ZIP`.
2. Select `cartogen_ai.zip` (or the versioned archive under `dist/`). From a GitHub release,
   download the attached asset `cartogen_ai_v<version>.zip`, **not** GitHub's auto-generated
   "Source code (zip)" (see below).
3. Enable the plugin if it isn't auto-enabled.

> **Don't install GitHub's "Source code (zip)".** QGIS uses the zip's top-level folder name as
> the plugin's Python module name. GitHub names that folder `<repo>-<tag>`, for example
> `cartogen-ai-qgis-plugin-cartogen-ai-v1.16.0-rc15`. The dots in the version make it an
> invalid module name, so QGIS fails with
> `ModuleNotFoundError: No module named 'cartogen-ai-qgis-plugin-cartogen-ai-v1'`
> (seen live on QGIS 4.2.2 with an earlier release candidate). The release asset built by
> `plugin_upload.py` always uses the folder `cartogen_ai_plugin`. If you already installed the source
> zip, or an older release that used the folder `cartogen-ai` (rc24 and earlier), delete that folder from your profile's `python/plugins/` directory and install the asset.

**From source** (development):
1. Copy this repository into your QGIS profile's plugin folder as `cartogen_ai_plugin` (the same
   folder name the release zip uses), e.g.
   `%APPDATA%\QGIS\QGIS4\profiles\default\python\plugins\cartogen_ai_plugin` on Windows.
   Don't name it exactly `cartogen_ai`: that folder would shadow the `cartogen_ai` namespace package
   under `src/` and break every `cartogen_ai.core` import (see `plugin_upload.py`'s
   `PACKAGE_DIR` comment). Don't include dots in the name either, for the reason above.
2. Restart QGIS, or use the Plugin Reloader plugin.

This build is not currently published on the public QGIS plugin repository
(plugins.qgis.org); install it via one of the methods above.

### Optional dependencies

Document parsing (PDF/Word/Excel attachments), `search_web`, chart/dashboard generation, and PDF
table extraction need a few extra Python packages, listed in [requirements.txt](requirements.txt).
Install them either:
- through the bundled `qpip` plugin dependency (QGIS will offer to install them), or
- manually in the OSGeo4W Shell: `python -m pip install -r requirements.txt`.

Everything else works without them — a missing optional package degrades that one
feature with a clear error message rather than breaking the plugin.

**Install optional dependencies with QGIS fully closed, not while it's running.** A package install
that replaces a module QGIS already has loaded — most likely with the heavier
`extract_features_from_imagery` dependency group, which shares `jinja2`/`markupsafe` with `folium` —
can fail on Windows with `PermissionError: [WinError 5] Access is denied` on a locked `.pyd` file.
This is a Windows file-lock issue, not a plugin bug, and no code running inside the same locked
process can work around it. Close QGIS completely, install (via `qpip` on next launch, or the
OSGeo4W Shell), then reopen QGIS.

## Quick start

1. Open the **Cartogen AI** panel (toolbar icon or `Plugins` menu).
2. Click the ⚙ settings icon, pick a provider, and paste an API key (or point at a
   local Ollama server — no key needed). Get a key from the provider you picked:
   - OpenRouter (has a genuinely free tier): https://openrouter.ai/keys
   - Google Gemini: https://aistudio.google.com/apikey
   - Ollama needs no key — just a local server endpoint URL.
3. Type a request, e.g. *"List all layers in the project"* or *"Calculate the area for
   the active layer"*. See the in-app **Help** tab for more examples, or
   [docs/USER_GUIDE.md](docs/USER_GUIDE.md) for a full walkthrough.

## Documentation

`docs/` also has its own [index](docs/README.md) with the same grouping, for anyone browsing
the folder directly on GitHub.

### Getting started

| Doc | Covers |
|---|---|
| [docs/USER_GUIDE.md](docs/USER_GUIDE.md) | Chat, Task Manager, memory, file attachments, settings, live hazard monitoring — with screenshots |
| [docs/TOOLS_REFERENCE.md](docs/TOOLS_REFERENCE.md) | All 294 tools, auto-generated from the live registry |
| [site/](site/) | The documentation site (architecture, security and privacy, tool reference by category, development guides), built from the documents in this repository by `site/build.py` and published to GitHub Pages by `.github/workflows/docs-site.yml`; it will be at https://http-solution.github.io/cartogen-ai-qgis-plugin/ once Pages is switched on for the repository |

### Security & compliance

| Doc | Covers |
|---|---|
| [SECURITY.md](SECURITY.md) | Threat model, protections, adversarial testing results, known limitations |
| [docs/GDPR_COMPLIANCE_REVIEW.docx](docs/GDPR_COMPLIANCE_REVIEW.docx) | GDPR compliance review |
| [docs/DPIA_SCREENING_WORKSHEET.docx](docs/DPIA_SCREENING_WORKSHEET.docx) | Data Protection Impact Assessment screening worksheet |
| [docs/GDPR_HOSTED_ACCOUNT_ADDENDUM_2026-09-08.md](docs/GDPR_HOSTED_ACCOUNT_ADDENDUM_2026-09-08.md) | GDPR addendum specific to the planned hosted-account (Professional tier) data flows |

### Engineering & process

| Doc | Covers |
|---|---|
| [docs/IMPLEMENTATION_TRACKER.md](docs/IMPLEMENTATION_TRACKER.md) | **Start here for "what's open right now."** Living doc consolidating every genuinely open item from the dated review/audit/spec docs, kept current as things resolve |
| [docs/BUG_TRACKER.md](docs/BUG_TRACKER.md) | Living, in-repo bug tracker — currently-open real defects only, plus the known sandbox test-artifact baseline so it's never mistaken for a regression |
| [docs/RELEASE_SMOKE_TEST.md](docs/RELEASE_SMOKE_TEST.md) | ~15-minute manual checklist to run in a real QGIS session before each release |
| [docs/LIVE_TEST_SCENARIOS.md](docs/LIVE_TEST_SCENARIOS.md) | Multi-turn workflow scenarios (task routing, confirmation gates, map visualization accuracy, technical-analysis accuracy) that a single-prompt smoke test can't catch |
| [docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md](docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md) | 27-point production-readiness architecture review |
| [docs/CODE_REVIEW_2026-09-08.md](docs/CODE_REVIEW_2026-09-08.md) | Dated code review with concrete findings |

### Product & humanitarian standards

| Doc | Covers |
|---|---|
| [docs/HUMANITARIAN_CARTOGRAPHY_STANDARDS.md](docs/HUMANITARIAN_CARTOGRAPHY_STANDARDS.md) | Cartographic design/QA standards the agent's styling and layout tools follow |
| [docs/HUMANITARIAN_TOOLS_CATALOGUE.md](docs/HUMANITARIAN_TOOLS_CATALOGUE.md) | Every humanitarian tool by workflow: what it does, what it draws on the map, how to get better results, and a map-styling review |
| [docs/HUMANITARIAN_MAPPING_TASK_REFERENCE.md](docs/HUMANITARIAN_MAPPING_TASK_REFERENCE.md) | Humanitarian mapping task taxonomy for tool coverage, prompts, workflows, and acceptance testing |

### Current reviews and plans (dated, not archived)

| Doc | Covers |
|---|---|
| [docs/RC10_RC12_AUDIT_2026-10-02.md](docs/RC10_RC12_AUDIT_2026-10-02.md) | Audit of the rc10-rc12 changes |
| [docs/RC12_LIVE_TEST_AND_AUDIT_PLAN_2026-10-04.md](docs/RC12_LIVE_TEST_AND_AUDIT_PLAN_2026-10-04.md) | What to test by hand in rc12, in what order |
| [docs/HUMANITARIAN_WORKFLOW_GAP_ANALYSIS_2026-10-04.md](docs/HUMANITARIAN_WORKFLOW_GAP_ANALYSIS_2026-10-04.md) | Humanitarian workflow document compared with the tools: what is covered, partial, missing, and the build plan |
| [docs/VISUALIZATION_AND_ANALYSIS_GAP_ANALYSIS_2026-10-01.md](docs/VISUALIZATION_AND_ANALYSIS_GAP_ANALYSIS_2026-10-01.md) | Output styling and analysis gaps found on the rc10 smoke test |
| [docs/JIAF2_ANALYSIS_SUPPORT_PLAN_2026-10-04.md](docs/JIAF2_ANALYSIS_SUPPORT_PLAN_2026-10-04.md) | What the JIAF 2.0 Technical Manual specifies, what a JIAF 2 analysis-support module would compute versus record, the build stages, and what is still needed (plan and specification only, nothing built) |
| [docs/HYDROLOGY_ENGINEERING_TOOLS_2026-10-04.md](docs/HYDROLOGY_ENGINEERING_TOOLS_2026-10-04.md) | The hydrology engineering tools and their limits |

### Roadmap, specs & dated reviews (archive)

Frozen historical documents — accurate to when they were written, never edited after the fact
(see [CLAUDE.md](CLAUDE.md)). Corrections live in newer docs that supersede them, not in-place
edits. See [docs/archive/README.md](docs/archive/README.md) for the full, one-line-each index of
every archived file; a few of particular note:

| Doc | Covers |
|---|---|
| [docs/archive/STATUS_REVIEW_2026-08-20.md](docs/archive/STATUS_REVIEW_2026-08-20.md) | Full-codebase status review: architecture, tool registry, security, docs, open items, next steps |
| [docs/archive/DESTRUCTIVE_TOOLS_AUDIT_2026-08-21.md](docs/archive/DESTRUCTIVE_TOOLS_AUDIT_2026-08-21.md) | Audit of which destructive tools have the preview/confirm safety gate and which don't, with an open product decision on 4 humanitarian analysis tools |
| [docs/archive/DOCUMENTATION.md](docs/archive/DOCUMENTATION.md) | Earlier, superseded full-repo documentation pass |

### Project reference

| Doc | Covers |
|---|---|
| [CONTRIBUTING.md](CONTRIBUTING.md) | How this codebase is written: comment discipline, honest status labeling, testing conventions |
| [CHANGELOG.md](CHANGELOG.md) | Version history, `[1.4.0]` onward -- see [CHANGELOG_ARCHIVE.md](CHANGELOG_ARCHIVE.md) for `[1.3.0]` and earlier |
| [LICENSE](LICENSE) | GNU GPL v2 |

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) — it's short and specific to this codebase, not a generic
PR-process doc. It covers comment discipline (explain *why*, not *what*), honest status labeling
for anything unverified in a non-QGIS sandbox, and the testing conventions the suite expects.
Issues and PRs go through [github.com/http-solution/cartogen-ai-qgis-plugin](https://github.com/http-solution/cartogen-ai-qgis-plugin).

## Development

```bash
# Run the full test suite (no QGIS installation required -- every module
# degrades gracefully outside QGIS via its own QGIS_AVAILABLE guard).
# -t . is required -- see CLAUDE.md's "Running things" section for why.
python -m unittest discover -s tests -t . -p "test_*.py" -v

# Regenerate docs/TOOLS_REFERENCE.md after adding/changing a tool
python docs/generate_tools_reference.py

# Build the release zip (reads the version from metadata.txt)
python plugin_upload.py
```

CI runs the same test suite automatically on every push/PR — see
[.github/workflows/tests.yml](.github/workflows/tests.yml). See
[CLAUDE.md](CLAUDE.md) for an orientation aimed at AI coding agents working in
this repo.

The codebase is organized as:
- `src/cartogen_ai/processing/` — Native QGIS Processing provider (`CartogenProcessingProvider`) and algorithms for Processing Toolbox / Model Designer.
- `src/cartogen_ai/infrastructure/` — Infrastructure boundary (QGIS proxy settings, credentials, environment abstractions).
- `src/cartogen_ai/core/` (PEP 420 namespace package):
  - `models/` — Domain models, transaction logging (`TurnTransactionLog`), and QA gate lifecycle states.
  - `validators/` — Schema contract and P-code depth validation engines.
  - `services/` — Core orchestration services (tool router, prompt refiner, background task runners).
  - `agent/` — Tool-calling loop, multi-provider interfaces (Gemini, OpenRouter, Ollama; the OpenAI and Claude clients stay in the code but are not offered since rc25), and 294 tools across the domain modules.
  - `ui/` — Dock widget, settings, layer context picker, and theme integration.
  - `exceptions.py` & `logger.py` — Exception hierarchy and structured `QgsMessageLog` logging.
- `tests/` — 3,069 automated unit and integration tests, runnable outside QGIS; the `*_live.py` modules (247 tests) need a real QGIS and run in the CI job `qgis-live-tests` on QGIS 4.2.2.
- `docs/` — User guide, auto-generated tools reference, living implementation tracker, and specs.
- `branding/` — Logo and visual assets.

This is a single tree — there is no second copy to keep in sync. (An earlier
version of this project did maintain two parallel trees; see the note at the
top of this file.)

## Support

For bugs, use the
[GitHub issue tracker](https://github.com/http-solution/cartogen-ai-qgis-plugin/issues); for questions and
ideas, use [Discussions](https://github.com/http-solution/cartogen-ai-qgis-plugin/discussions). Security problems go through
[private vulnerability reporting](https://github.com/http-solution/cartogen-ai-qgis-plugin/security/advisories/new), not a public issue
(see [SECURITY.md](SECURITY.md)). Everyone taking part is expected to follow the [Code of Conduct](CODE_OF_CONDUCT.md). General contact: cartogenai@gmail.com.
