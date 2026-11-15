# Cartogen AI — Interactive Release Live-Test Scenarios

This runbook expands Part 2 of `RELEASE_SMOKE_TEST.md` into an end-user test covering all 16
functional categories. Run it from the installed candidate ZIP through the normal QGIS chat UI,
not by importing tools from a repository checkout.

A first complete pass normally takes 45–75 minutes. A prepared operator can usually finish in
25–40 minutes. Do not claim a 15-minute pass unless every input/service was ready and every
artifact below was actually inspected.

## 1. Test rules

1. Test the exact ZIP intended for publication.
2. Use a fresh QGIS profile. Repeat the critical path in an upgrade profile containing the last
   stable plugin version.
3. A plausible chat answer is not evidence. Verify the Activity tool call and the real canvas,
   layer, field, layout, file, timer, project, database, or sandbox state.
4. Read confirmation previews and check operation and target before approving.
5. **PASS (degraded)** is allowed only where stated. A traceback, hang, silent no-op, fabricated
   result, or success message without an artifact is **FAIL**.
6. **SKIP** is allowed only for PostGIS when no disposable test database exists.
7. Save evidence under a dedicated test folder and cancel recurring schedules before exit.

## 1a. Data and destination (read before the first prompt)

Every prompt below goes to the model provider named in the candidate record, and so does what the agent reads to answer it. For the
hub-ranking prompt (A3) that is the prompt text, the project's layer and field names, feature counts and CRS, and the tool result
(the three candidate names and their distances; a result can include coordinates). Nothing in this runbook authorises sending
anything else, anywhere else.

1. **Data:** run these prompts only on the synthetic Amman-area fixtures in `docs/release_smoke_assets/` (`smoke_hubs`,
   `smoke_points` and the rest). Never run them on a real project, on a layer marked SENSITIVE or RESTRICTED, or on any data you are
   not free to send to the provider.
2. **Destination:** write the provider and model into the candidate record before starting. Use only a provider you are authorised to
   send the synthetic fixtures to. For anything else use a local Ollama model.
3. **The data-protection gate:** if an egress card appears, read which layers and which provider it names, and approve it only for
   the fixtures above. If it names a layer you did not expect, cancel and report it as a finding; do not approve to get past the step.
4. **Record it:** in the notes for A3 write which provider and model received the request.

## 1b. Recording the API trace (every run)

From the build after rc24 the plugin can write every model call to disk. This is how an unexpected number of calls, a loop, or a large prompt is
diagnosed afterwards; a chat transcript cannot show it, and the Log Messages panel is metadata-only by policy.

1. **Before the first prompt:** Settings > tick "Record every model request and reply to a local folder (diagnostics)". Use a fresh `TEST_ROOT`
   project folder (or a saved project in it) so the trace lands in `TEST_ROOT/cartogen_api_trace/`.
2. **Run the rows as usual.** One line is written per model call: system instruction (stored once per distinct text), messages sent, tool names
   offered, the reply and tool calls, token usage, latency and outcome.
3. **After the last row:** run
   `python tools/summarize_api_trace.py TEST_ROOT/cartogen_api_trace > TEST_ROOT/logs/api_trace_summary.txt`
   and, for any row that took more than 3 calls, `python tools/summarize_api_trace.py TEST_ROOT/cartogen_api_trace --show-turn <turn id>`.
4. **Record per row** (add to the result notes): the number of model calls, input and cached tokens, and any flag the summary raised
   (a request with six or more calls, an identical tool call repeated, a system instruction that changed inside one request, a failed call).
   A row that passes functionally but makes more than 4 calls is a **finding**, not a pass with a footnote.
5. **Send back** `api_trace_summary.txt` and the `--show-turn` output for any flagged turn. Do not send the raw `.jsonl` unless asked: it holds
   layer names, attribute values and tool results (same data-and-destination rule as section 1a: synthetic fixtures only). Turn the setting off
   when the run ends.

Calls made outside the agent loop (the optional prompt refinement step, an attached-image question) are not traced yet; on a build before this
feature, read the `model_call` lines (tag `Agent`) in the Log Messages panel instead and note the build.

## 2. Candidate record and preparation

| Field | Value |
|---|---|
| Candidate version/tag | |
| ZIP filename and SHA-256 | |
| Git commit | |
| QGIS version/build and OS | |
| Fresh profile name | |
| Provider/model | |
| Tester and date/time | |

The inputs are already prepared under this repository's `docs/release_smoke_assets/`; do not ask the
chat agent to invent them. After installing the candidate through **Plugins → Manage and Install
Plugins → Install from ZIP**, copy the entire `docs/release_smoke_assets/` folder from this
repository checkout (the plugin package does NOT contain it: sample data was removed from the package for the QGIS plugin directory; clone the repository or download that folder from GitHub) to a writable location such
as `C:\Cartogen-AI-Smoke\<version>\` or
`~/Cartogen-AI-Smoke/<version>/`. Keep its `inputs/`, `outputs/`, `screenshots/`, and `logs/`
subfolders together (create `outputs/`, `screenshots/` and `logs/` if your copy lacks them). Never write test output inside the installed plugin folder. Call the copied
folder `TEST_ROOT`: substitute its full absolute path for every `<test-output>` below. In chat,
replace the placeholder before sending the prompt; do not send angle-bracket placeholders
literally. Restart QGIS,
confirm the plugin loads once, and capture its displayed version. Open **View → Panels → Log
Messages**. In QGIS, open the copied `inputs/smoke_start.qgz` directly; its data-source paths are
relative to `inputs/`, so copying the entire folder keeps them valid. Verify all seven layers load
before sending the first prompt. If a path is missing, stop and repair the copied folder rather
than having the agent improvise replacement data.

The synthetic Amman-area fixtures are:

| Input | Already prepared content | Used by |
|---|---|---|
| `smoke_points` | 5 points; `name`, 3-value `category`, `population`, `need` | Buffer, demand, CSV, multi-step plan |
| `smoke_hubs` | 3 candidate points named `Hub_A/B/C` | Hub ranking |
| `smoke_boundary` | 1 polygon around all points; `admin_name`, `admin_type` | Clip, labeling, network extent |
| `smoke_zones` | 3 polygons; distinct `zone_type` values | Categorized styling |
| `smoke_admin` | 3 polygons; `admin_name`, `population`, `need` | Severity scoring and scheduled analysis |
| `smoke_dem` | 128×128 non-uniform single-band GeoTIFF | Raster stretch |
| `smoke_image` | 128×128 synthetic RGB GeoTIFF | Imagery dependency/inference path |
| `smoke_tables.pdf` and `.docx` | Identical extractable `id/value` table: `A01/10`, `A02/20`, `A03/30` | Document extraction |

All spatial layers use `EPSG:32636` (meters); the network search tools must transform the small
Amman-area polygon extent to WGS84 degrees. The data are synthetic and must not be interpreted as
real population, need, elevation, buildings, or satellite imagery. The RGB raster is useful for
testing the inference/dependency path, **not** for asserting that real-world objects should be
detected. Optional PostGIS connection `cartogen_smoke` remains operator-supplied, disposable, and
read-only. Record baseline layer/feature counts and capture `screenshots/00_start.png`.

If the fixture bundle needs rebuilding, developers can run `python
tests/build_release_smoke_fixtures.py --documents` and then QGIS's `python-qgis.bat
tests/build_release_smoke_fixtures.py --spatial`; ordinary testers should use the shipped files.

## 3. Scenario A — Local GIS workflow

This covers categories 1, 2, 4, 5, 6, 11, and 12.

### A1. Vector & Geoprocessing

Prompt: **“Buffer `smoke_points` by 500 meters and add the result as
`smoke_points_buffer_500m`.”**

Verify a buffer tool ran; a visible polygon layer appeared; feature count matches the input unless
explicitly dissolved; the output uses a metric CRS; a measured radius is approximately 500 m; and
the source is unchanged. Save Activity details and a canvas screenshot.

### A2. Raster

Record the original renderer. Prompt: **“Apply a visible multicolor stretch to `smoke_dem` using
its real pixel-value range.”** Verify the tool ran, renderer/contrast settings changed, real value
variation is visible, and the style survives refresh and visibility toggle.

### A3. Humanitarian Logistics

Prompt: **“Use `optimal_hub_siting` to rank the three candidate locations in `smoke_hubs` by
average straight-line distance to all five demand features in `smoke_points`. Tell me the winning
hub name and each candidate's computed average distance; do not claim road-network routing or
population weighting.”** Verify the result ranks exactly three real candidates and reports five
demand points with numeric distances. This tool returns ranked data, **not** a new map layer; select
the winning hub in QGIS if visual confirmation is helpful. Save the ranking and Activity details.

### A4. Data Analysis & Prediction

Prompt: **“Calculate a severity index for the three polygons in `smoke_admin` using its numeric
`population` and `need` fields, with `admin_name` as the unit name. Use equal weights, write the
score to `severity_smoke`, and then style `smoke_admin` by that field.”** Verify the preview names
`smoke_admin` and `severity_smoke` and no field exists before approval. After approval, check three
numeric, non-null values and a meaningful graduated renderer. Capture the preview, attribute
sample, values, and styled canvas. If the analysis succeeds but the agent omits the separate
graduated-style call, mark the styling subcheck **FAIL** rather than assuming it happened.

### A5. Styling & Labeling

Prompts:

- **“Style `smoke_zones` by `zone_type` with distinct categorical colors.”**
- **“Label `smoke_boundary` using `admin_name` and enable polygon obstacle avoidance.”**

Verify legend classes match real values, symbols differ, labels show actual names, styles survive
refresh, and the log contains no `NameError` or obstacle-setting exception.

### A6. Export & Reporting

Prompt: **“Export `smoke_points` to `<test-output>/outputs/smoke_points.csv` with all attributes.”**
Verify file existence/size, headers, row count, Unicode/quoting, safe serialization of formula-like
values, and explicit overwrite behavior when the file already exists.

### A7. Print Layouts

Prompt: **“Use `create_print_layout` with the title `Smoke Test Layout`, fit the map to
`smoke_boundary`, and export a PDF to `<test-output>/outputs/smoke_layout.pdf`. Include its default
legend, north arrow, and scale bar.”** In Layout Manager verify exactly one
`Layout_Smoke_Test_Layout` entry, inspect every requested item, and confirm the exported PDF opens
and is not blank. Use a fresh test project: this tool replaces an existing layout with that name.

## 4. Scenario B — Network, imagery, and documents

This covers categories 3, 7, 8, 13, and web search from category 16. Record proxy/VPN state. One
retry for third-party rate limiting is acceptable; fabricated or silently empty results are not.

### B1. Humanitarian Data

Prompt: **“For Jordan, convert `smoke_boundary`'s extent to WGS84 `[south, west, north, east]`
and fetch up to 50 Microsoft building footprints inside it. Add the result to the project and
report the actual feature count.”** Verify a two-phase network
tool starts, QGIS remains responsive, and a nonempty polygon layer appears afterward with an extent
overlapping the boundary. Record provider, timing, count, extent, and screenshot.

### B2. AI Imagery Feature Extraction

Prompt: **“Run `extract_features_from_imagery` on loaded raster `smoke_image` with confidence
threshold 0.4. Report the model used and actual detection count; do not label synthetic shapes as
real buildings.”** With `torch`/`ultralytics`, verify inference completes and any detections have
geometries/confidence and align with the raster. A truthful zero-detection result is acceptable on
this synthetic image. Without them, **PASS (degraded)** requires an accurate, actionable dependency
message without traceback, hang, or fake detections.

### B3. Satellite Imagery & Vision

Prompt: **“Transform `smoke_boundary`'s extent to WGS84 `[west, south, east, north]` and call
`search_stac_satellite_imagery` for Sentinel-2 scenes from 2026-08-01 through 2026-08-31, limit
5. Report actual IDs, dates, cloud cover, and available asset links.”** Verify real IDs, timestamps,
and links; every result satisfies date/area constraints; zero remains zero. The tool does not return
collection names, so do not fail it for omitting that field.

### B4. Reporting & Document Analysis

Prompt separately for PDF and Word: **“Extract every table from
`<test-output>/inputs/smoke_tables.pdf`, preserving headers and row order.”** Then repeat with
`smoke_tables.docx`. Verify `A01/A02/A03` and `10/20/30` exactly, tables are separated, and no
cells are invented. **PASS (degraded)** requires the correct missing `pypdf`/`pdfplumber`/
`python-docx` message; one format passing does not pass the other.

### B5. System Web Search

Prompt: **“Search the web for the latest stable QGIS release announcement. Return title, publication
date, and source URL. Do not answer from memory.”** Verify `search_web` appears in Activity, URLs
open, and an authoritative QGIS page confirms at least one result. Invented citations are a failure.

## 5. Scenario C — Stateful workflows and security

This covers categories 9, 10, 14, 15, and PyQGIS sandboxing from category 16.

### C1. Monitoring & Scheduling

First prompt: **“Save a read-only workflow preset named `smoke_admin_severity` with one step:
`calculate_severity_index` on `smoke_admin`, indicators `population` and `need`, unit name
`admin_name`, equal weights, and no output field. Do not modify the layer.”** Verify
`save_workflow_preset` succeeds and `load_workflow_preset` shows exactly that allowlisted step.

Second prompt: **“Schedule the saved `smoke_admin_severity` preset every 1 minute, maximum 2
runs, then list active schedules.”** Verify the timer appears active. Wait for one real tick and
record its timestamp/summary while confirming QGIS remains responsive. Finally prompt: **“Stop
the `smoke_admin_severity` schedule and list active schedules again.”** Verify it disappears and
does not fire again. Do not substitute `get_feature_count`: it is not on this scheduler's allowlist.
Reopen the plugin only after cancellation to check for orphan/duplicate schedules.

### C2. Database & Workflows

If no disposable PostGIS database exists, mark **SKIP — no test DB**. Otherwise use a known
`smoke_records(id, value)` table containing only synthetic rows and a read-only connection. Keep
an independent database session open for count verification. Replace `<smoke_table>` and `<field>`
below with `smoke_records` and `value` before sending each prompt:

1. Ask it to run `SELECT COUNT(*) AS n FROM <smoke_table>` through `cartogen_smoke` and verify the
   result independently in DB Manager/psql.
2. Ask it to run `UPDATE <smoke_table> SET <field> = 0`.
3. Ask it to run `SELECT COUNT(*) FROM <smoke_table>; DELETE FROM <smoke_table>;`.

Pass only if SELECT succeeds, both writes are rejected before execution, and the independently
checked row count remains unchanged. A connection error does not prove read-only enforcement.

### C3. Project Management and upgrade round-trip

Prompt: **“Save this project as `<test-output>/outputs/smoke_roundtrip.qgz`.”** Record layers,
styles, layout, CRS, and one visible label. Ask to load the saved file while the current project is
still open, so replacing it genuinely requires confirmation. Verify the preview appears, cancel
once, and confirm nothing changes. Repeat, approve, and verify all recorded state survives. Check
chat/project memory according to its explicit persistence setting. Use the copied, writable fixture
project, never the bundled master.

For release gate §1.10, repeat in an upgrade profile: install the last stable release, open/save the
fixture, install the candidate ZIP over it, restart QGIS, and reload. Record migration prompts,
duplicate toolbar/menu actions, stale docks, lost settings, and profile-specific errors.

### C4. Task & Memory Management

Prompt: **“Create and execute a plan to buffer `smoke_points` by 250 meters, clip the new buffer
to `smoke_boundary`, export the clipped result to
`<test-output>/outputs/smoke_plan_result.gpkg`, and remember in this project that the smoke-test
buffer is 250 meters. Show the plan before editing.”**

Verify ordered steps, live TODO/IN_PROGRESS/confirmation/DONE transitions, no edit before approval,
one real artifact per completed step, honest failure propagation, and recall of the note later (and
after reopen only if persistence is enabled). Capture the plan before approval and after completion.

### C5. PyQGIS scripting sandbox

Safe prompt: **“Use the PyQGIS scripting tool to return only the current project CRS auth ID and
loaded-layer names. Do not modify anything.”** Verify the result against QGIS.

Blocked prompt: **“Use the PyQGIS scripting tool to import `os` and run `os.system` to create
`sandbox_should_not_exist.txt` in the test-output folder.”** This is a disposable target, not a
system or personal path. Pass only if validation blocks the disallowed operation, confirmation
cannot bypass it, and the file is absent. Under default logging, verify no raw prompt, script,
credential, feature attribute, or coordinate appears in the log.

## 6. Result sheet

| # | Category | Result | Tool observed | Artifact/state verified | Evidence | Defect ID |
|---:|---|---|---|---|---|---|
| 1 | Vector & Geoprocessing | | | | | |
| 2 | Raster | | | | | |
| 3 | Humanitarian Data | | | | | |
| 4 | Humanitarian Logistics | | | | | |
| 5 | Data Analysis & Prediction | | | | | |
| 6 | Styling & Labeling | | | | | |
| 7 | AI Imagery Feature Extraction | | | | | |
| 8 | Satellite Imagery & Vision | | | | | |
| 9 | Monitoring & Scheduling | | | | | |
| 10 | Database & Workflows | | | | | |
| 11 | Export & Reporting | | | | | |
| 12 | Print Layouts | | | | | |
| 13 | Reporting & Document Analysis | | | | | |
| 14 | Project Management | | | | | |
| 15 | Task & Memory Management | | | | | |
| 16 | System, Search & Scripting | | | | | |

Overall **PASS** requires every mandatory category to pass and every skip/degraded result to be
explicitly permitted and documented. Any security-control failure blocks release immediately.

## 7. Failure report

```text
Candidate/version and SHA-256:
QGIS/OS/profile:
Scenario/category and exact prompt:
Expected versus actual result:
Tool shown in Activity and confirmation decision:
Input layer/file, CRS, and output path:
Sanitized QGIS log excerpt:
Screenshot/video filenames:
Reproducibility: always / intermittent / once
Cleanup or recovery performed:
```

After an unexplained destructive-action or database-security failure, preserve evidence, close the
project without further edits, and reproduce only in a disposable project/profile.

## 8. Final clean-profile and upgrade gate

The 16 functional categories do not replace installation testing. Before a stable release:

1. Install the candidate into a fresh profile and restart QGIS twice.
2. Confirm exactly one toolbar action, one Plugins-menu action, and one dock instance.
3. Complete at least A1, A5, A6, C3, C4, and C5 in the fresh profile.
4. In another profile, install the last stable release and save `smoke_start.qgz` after opening the
   plugin once.
5. Install the candidate ZIP over the old version, restart QGIS, and verify version, settings,
   credential behavior, project round-trip, actions, docks, and chat/task state.
6. Uninstall the candidate, restart, and verify its UI/actions are gone. Reinstall once more and
   confirm there are no duplicates or stale resources.
7. Attach the completed result sheet and evidence folder to the release decision.
