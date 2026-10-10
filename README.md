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

**Community edition · Version 1.16.0-rc26 (pre-release) · GNU GPL v2 · QGIS 4.2–4.99 · [cartogenai.com](https://cartogenai.com)**

Cartogen AI is built for GIS analysts, humanitarian teams, researchers, and anyone who
needs to move from a question to a reproducible spatial result without leaving QGIS.
The agent exposes its plan, tool calls, progress, and errors instead of returning a
black-box answer.

> **Project status (2026-10-06):** active Community edition, currently at the **1.16.0-rc26 pre-release** build (rc20 to rc26 add the audit fixes, hand-test fixes and the cost and routing work made after rc19).
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

- **Multi-provider**: OpenRouter, Google Gemini, OpenAI, Anthropic Claude, or a local
  Ollama server — switch anytime, bring your own API key (OpenRouter has a free tier;
  Ollama is free and fully local).
- **Native QGIS Processing Provider**: Registered under `QgsApplication.processingRegistry()`
  (`cartogen_ai.processing`), exposing native algorithms (e.g. `OptimalHubSitingAlgorithm`,
  `CalculateServiceAreaAlgorithm`) directly to the QGIS Processing Toolbox, Graphical Model Designer,
  batch processing, and headless `qgis_process` CLI execution.
- **208 tools** covering vector and raster geoprocessing, OGC SLD 1.1.0/1.0.0 export, point cluster
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
- **Native web search grounding** on Gemini and OpenAI, with automatic model fallback
  if a configured model is retired.
- **Stop button**: cancel an in-progress request instead of waiting it out.
- **Security-conscious by design** — see [SECURITY.md](SECURITY.md) for the full
  threat model and what was actually adversarially tested (not just intentions):
  a restricted execution sandbox for model-generated PyQGIS scripts, fail-closed
  read-only SQL enforcement, an SSRF guard on fetched URLs, and a destructive-action
  confirmation gate the model cannot self-approve.

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
Tools marked **new** were added in 1.16.0-rc25 or 1.16.0-rc26 and have been tested offline and in CI on QGIS 4.2.2, not by hand.

| Workflow | Tools |
|---|---|
| **1. Rapid crisis and base mapping** | `search_hdx_datasets`, `fetch_hdx_admin_boundaries`, `fetch_geoboundaries`, `fetch_osm_features`, `ingest_osm_features`, `fetch_building_footprints`, `search_stac_satellite_imagery`, `calculate_raster_change_detection`, `calculate_damage_exposure_severity`, `extract_features_from_imagery`, `add_incident_point`, `add_point_layer`, `generate_mapping_task_grid`, `import_humanitarian_table` |
| **2. MSNA and field data** | `design_sampling_frame`, `fetch_worldpop_population`, `estimate_population_exposure`, `load_tabular_data_as_layer`, `extract_pdf_tables`, `extract_word_tables`, `aggregate_data`, `aggregate_survey_indicator` |
| **3. Logistics, routes and catchments** | `estimate_road_speeds`, `build_composite_impedance_field`, `apply_network_barriers`, `calculate_service_area`, `classify_facilities_by_access`, `travel_time_matrix`, `population_access_gap`, `optimal_hub_siting`, `location_allocation`, `optimize_delivery_route`, `score_route_incident_risk`, `analyze_critical_links` |
| **4. Severity mapping (JIAF-style)** | `calculate_severity_index`, `calculate_presence_gap`, `load_3w_data`, `calculate_population_in_need`, `hotspot_analysis`, `analyze_incident_trend`, `forecast_trend`, `import_jiaf_inputs`, `record_jiaf_setup`, `get_jiaf_setup`, `compute_jiaf_preliminary`, `record_jiaf_decisions`, `get_jiaf_decisions`, `finalize_jiaf_results`, `compute_jiaf_patterns` |
| **5. Allocation and prioritisation** | `calculate_mcda_ranking`, `fetch_fts_funding_data`, `generate_sector_coverage_report`, `weighted_overlay_analysis`, `calculate_allocation_envelope` |
| **6. Anticipatory action** | `evaluate_forecast_trigger`, `fetch_gdacs_disaster_alerts`, `fetch_nasa_eonet_events`, `fetch_nasa_active_fires`, `generate_situation_dashboard`, `run_monitoring_workflow`, `schedule_recurring_workflow`, `stop_recurring_workflow`, `list_scheduled_workflows` |
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
[1.16.0-rc26 pre-release](https://github.com/http-solution/cartogen-ai-qgis-plugin/releases/tag/cartogen-ai-v1.16.0-rc26); the release
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
   - OpenAI: https://platform.openai.com/api-keys
   - Anthropic Claude: https://console.anthropic.com/settings/keys
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
| [docs/TOOLS_REFERENCE.md](docs/TOOLS_REFERENCE.md) | All 208 tools, auto-generated from the live registry |

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
  - `agent/` — Tool-calling loop, multi-provider interfaces (Gemini, Claude, OpenAI, OpenRouter, Ollama), and 208 tools across the domain modules.
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
(see [SECURITY.md](SECURITY.md)). Everyone taking part is expected to follow the [Code of Conduct](CODE_OF_CONDUCT.md). General contact: info@cartogenai.com.
