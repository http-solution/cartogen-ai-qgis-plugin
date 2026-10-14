# Roadmap: full QGIS control through the chat (2026-10-14)

Plain-language plan. Behind it are `docs/QGIS_COVERAGE_GAP_ANALYSIS_2026-10-14.md` (the evidence) and the two spreadsheets in `docs/qgis_coverage/`.

## 1. You are right that most of this used to be possible - here is the evidence

I tested your recollection instead of assuming it.

| Question | Answer | How I know |
|---|---|---|
| Was a tool removed or renamed in a later release? | **No.** 202 tools in rc14, 203 in rc21, 208 in rc30, 212 now; not one name lost | tool lists built from the code at four release commits |
| Did a basic request stop reaching its tool? | **Yes, twice, both fixed.** rc23 (generic words removed from tool matching, fixed in 1.16.3) and the 40 foundation tools that never had aliases (fixed in PR 316) | replay of plain requests through 43 releases |
| Do any of the 89 actions that have a tool fail now but worked before? | **No.** 0 regressions in routing across 40 probed releases (rc12 to rc41); 10 actions that have a tool were never offered in any release up to rc41; all are offered now | the same replay applied to the 163 documented actions |
| Then why does it feel like things were lost? | **The script tool was the "do anything" route, and it was closed for security.** The 1.16.0-rc4 changelog says the sandbox let a script reach `qgis.utils` and `processing`, and fixed it; from rc7 (28 September) scripts run in a separate process on a COPY of the project, so changes to your layer tree, styles, order, removal and file layers are not applied to your project (the reply now says so since 1.16.1). Before that, a script could reach `processing` and `qgis.utils` (so, in principle, groups, CRS, zoom and any Processing algorithm) in your live project; I could not replay those releases to confirm each ability | CHANGELOG rc4, rc7, rc8; `script_isolation.py`; the worker gives a script 9 names and never starts Processing |

What I could not check: this repository starts at 2026-10-02, so the 1.15.x releases and rc1 to rc3 (where the open script route existed) cannot be replayed here. If you remember a specific request that worked, send it to me: it becomes a test row.

**So the loss is not a bug to revert. It is the price of closing the script route. The roadmap pays it back by giving each of those abilities its own safe tool.**

## 2. The principle

Each missing ability becomes a dedicated tool that is: checked (inputs validated), undoable (goes through the existing edit session and transaction log), confirmed when destructive, tested in real QGIS in CI, and guarded by a test that fails if it ever stops working. No ability is brought back by reopening the script route.

## 2b. Showcase pack: four live-demo scenarios that must work (added 2026-10-14)

The owner reported four regressions from live demos. They are acceptance scenarios, built right after M0, each with a CI test.

| # | Scenario | Why it fails today (read from the code) | Fix | Test |
|---|---|---|---|---|
| S1 | "Determine watershed area, stream length, H, slope, 20-year return period, intensity, tc and peak flow at 32 01 47.39 N, 35 48 21.00 E" | Task 36.01 blocks with 3 questions (DEM, IDF, runoff coefficient have no defaults); no tool delineates a basin or longest flow path from a DEM | DEM-based delineation tool (Copernicus 30 m, pour-point snapping, area, longest flow path, H, slope), Kirpich Tc, rational Q, report and map; ask once, then proceed with assumptions listed in the report | synthetic DEM, pure numpy, plus a live-QGIS CI test |
| S2 | Basic instructions | Router regression, fixed in 1.16.3 and #316 | keep the golden tests | exists |
| S3 | "Find the information on the internet and give the source" | `search_web` needs the `ddgs` package, absent in clean installs; grounded search works only with Gemini and OpenAI | search path without extra dependencies; every answer lists URL and date | offline fixtures |
| S4 | "Check the internet for major incidents from the news and list them on the map" | `find_incident_reports` uses fixed official sources only (rc37); no news, geocode, plot path | news search, geocoding, points with link, date and "reported by" wording; no model-typed coordinates | offline fixtures |

Policy decisions (owner, 2026-10-14):
- `env()` is denied in model-written expressions. The file functions (`file_exists`, `file_path`, `file_name`, `base_file_name`, `file_suffix`, `file_size`, `is_file`, `is_directory`) are denied **on condition that nothing the plugin does depends on them**. Checked: the plugin's own code calls none of them as QGIS expression functions (the grep hits are unrelated Python helpers), so denying them breaks no existing feature. The rule is a regression test: a model-written expression using a denied name is refused with a clear message, and every expression the plugin generates itself still passes the screen. Expressions the user types, or asks for by name, are allowed after a confirmation.
- The raster calculator is `native:rastercalc` with a friendly wrapper, added after the expression screen.
- Order: M0 to M9 and S1 to S4 as agreed above. Further showcase scenarios are planned only after those are done; each will be added here as a row with its own test.

## 3. Milestones

Sizes: S = about one pull request, M = a few, L = a series. "Rows" are the 163 documented actions; the Processing numbers come from the 772-algorithm registry.

| # | Milestone | What the user can do afterwards | Status today | Size |
|---|---|---|---|---|
| **M0** | **Safety net** | Nothing new; nothing can silently disappear again | ratchet and golden tests exist; schema snapshot, size pins, release gate and the live run of all 42 allow-listed algorithms are missing | S to M |
| **M1** | **Data and layers** | Open any file or layer inside a container, any raster, zip and KMZ; add basemaps and web layers (XYZ, WMS, WMTS, WFS, ArcGIS REST) from a vetted list; create empty layers with chosen fields; create lines and polygons from coordinates or WKT; save as with another CRS, extent or fields; fix broken paths; package layers; layer metadata | 17 missing, 4 partial (P1: 8, P2: 8, P3: 5) | L |
| **M2** | **Project and map** | Layer groups; set the project CRS or a layer's CRS; zoom to scale or extent, pan, rotate; bookmarks; project title and variables; measure; identify by coordinate | 13 missing, 2 partial (P1: 4, P2: 6, P3: 5) | M |
| **M3** | **Attributes and editing** | Clear and select all; add, delete, rename and change fields; change values; add, delete, move, rotate, split, merge features; layer filter; live joins and relations | 17 missing, 8 partial (P1: 11, P2: 6, P3: 8) | L |
| **M4** | **Symbology and labels** | Outline, width, marker, line pattern, fill pattern; every renderer; rule-based labels, halos, callouts; diagrams; raster renderers; saved symbols | 5 missing, 2 partial (P1: 2, P2: 2, P3: 3) | L |
| **M5** | **Layouts** | Add pictures, shapes, arrows, tables, charts, HTML; set map scale and extent; pages, grid; save and load templates; SVG and GeoPDF; reports | 5 missing, 1 partial (P1: 1, P2: 4, P3: 1) | M |
| **M6** | **Processing** | Any of the safe QGIS tools by name, with the same checks as today | 88 geometry, 36 table and selection, 36 analysis and creation, 31 geometry-quality tools, 19 other; then 16 that take an expression, and 77 that write files or read paths | L, one family per PR |
| **M7** | **Raster and terrain** | Raster calculator (`native:rastercalc`), warp, resample, polygonize, rasterize, proximity, terrain indices, cell statistics | 8 missing, 1 partial (P1: 2, P2: 5, P3: 2); plus 73 processing algorithms | L |
| **M8** | **New layer types** | Mesh, point cloud, vector tiles, 3D tiles, annotation layers, 3D view, temporal and elevation controllers, GPS | 34 algorithms wait for these; specialised rows: 2 missing, 1 partial (P1: 0, P2: 0, P3: 3) | L |
| **M9** | **Optional** | GRASS, only when installed | 307 algorithms | S |

## 4. Order, and why

1. **M0 first.** It is the only milestone that changes nothing for users and prevents every future "it was working before".
2. **M1 and M3 next.** Opening data and editing it are the two things a QGIS user does all day, and they are where the closed script route hurt most.
3. **M2** (groups, CRS, scale) is small and removes many daily annoyances.
4. **M6 in families**, interleaved: one family (for example vector geometry) after each large milestone, so there is always something new to hand-test. Each family is added only when its algorithms pass the registry check, have a live test and have a parameter-rule row.
5. **M4 and M5** (looks and layouts) once data, editing and analysis are solid.
6. **M7** after the expression screen exists (`native:rastercalc` takes an expression).
7. **M8 and M9** last: they depend on new layer types or optional software.

You can reorder everything except M0 first and the expression screen before M6's expression group and M7.

## 5. How each milestone is released

1. Build the tools; unit tests; a live test in the QGIS 4.2.2 image for every tool.
2. Add the golden requests for the new abilities and move the matching rows in `tools/qgis_coverage_actions.py` from missing to covered; `python tools/build_qgis_coverage.py --write-baseline` records the new floor in the same pull request.
3. CI must pass the ratchet, the golden suites and the 26-session replay.
4. A release candidate is cut; **you run the "START HERE" rows plus the new milestone's rows**; results come back as the results file.
5. Only then a stable number.

## 6. What it will not do

- It will not reopen free Python in your live QGIS session. Anything the script route used to do is rebuilt as a tool; what has no tool yet is listed in the spreadsheet with its priority.
- It will not enable installing plugins, running SQL or Python algorithms, or downloading and uploading files through Processing (14 algorithms are excluded for exactly those reasons).
- It does not make the AI pick the right tool by itself. It makes sure the right tool exists, is offered, and is tested. How the model uses it is checked by the hand-test rows.

## 7. What I need from you

1. Tell me one or two requests that used to work for you and do not now. They become the first test rows.
2. Confirm or change the order in section 4.
3. Decide the two policy questions the plan depends on: (a) deny `env()` and the file functions in model-written expressions, (b) use `native:rastercalc` as the raster calculator.
