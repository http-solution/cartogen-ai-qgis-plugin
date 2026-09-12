# Cartogen AI — Release Smoke Test Checklist

**Purpose.** Every review round in this project's history (`docs/archive/STATUS_REVIEW_2026-08-20.md` §8.1,
and the round before it, and the round before that) has flagged the same top item: nothing in this
sandbox can run a real QGIS session, so every tool in the registry is "correct per the code and test
suite," never "confirmed working live." Repeating that as a recommendation every round doesn't close
the gap — it just restates it. This document exists to turn it into something a human can actually
*do*: a ~15-minute checklist, one representative tool call per category, run inside a real QGIS
install before each release. Not exhaustive (169 tools, this checks ~16 of them), but it catches the
class of bug no amount of sandboxed code review can: a real PyQGIS API call that doesn't behave the
way the code assumed.

**When to run this.** Before tagging a release (`python plugin_upload.py`), and after any change that
touches `agent/tools/`, `ui/dock_widget.py`, or a provider client's request/response shape.

**Setup (once).** Open QGIS with this plugin installed and enabled. Create or open a project with:
- One point vector layer with at least 3 features and one numeric attribute column (e.g. a
  population or severity field).
- One polygon vector layer (e.g. admin boundaries) overlapping the point layer's extent.
- One single-band raster layer (e.g. a DEM or NDVI GeoTIFF) — any raster with real pixel value
  variation, not a flat/uniform test file.

Configure at least one provider in Settings (Ollama is the cheapest option for this — no API cost).

---

## Checklist

For each row: type the example prompt into the chat, confirm the tool actually ran (not a text-only
reply pretending to), and check the "what to verify" column against what actually happened on the
canvas/project — not just that the chat bubble looks plausible.

| Category | Example prompt | What to verify |
|---|---|---|
| Vector & Geoprocessing | "Buffer the point layer by 500 meters." | A new buffered layer appears on the canvas with the expected geometry, not just a text description of what a buffer would look like. |
| Raster | "Apply a color ramp to the raster layer." (`apply_raster_stretch`, added v1.2.25) | The raster's renderer visibly changes from flat/default to a real color ramp or contrast stretch — this is the tool that closed a previously-flagged "no raster styling exists" gap; confirm it actually renders, not just that the tool call succeeds. |
| Humanitarian Data (HDX / OSM / geoBoundaries) | "Fetch building footprints for the polygon layer's extent." (`fetch_building_footprints` — Microsoft's Global ML Building Footprints dataset, not OpenStreetMap) | A real network call completes and a new layer with real building footprint geometries loads — this is a `TWO_PHASE_TOOLS` call (background-thread fetch, main-thread layer creation), confirm the UI doesn't block during the fetch and the layer still appears correctly on the main thread. |
| Humanitarian Logistics | "Find the optimal hub location to serve the point layer's features." | Tool completes and returns a real computed location, not an error swallowed into a plausible-sounding text reply. |
| Data Analysis & Prediction | "Calculate a severity index for the point layer using its numeric field." | A new field is written to the layer with real computed values, and — per prompt rule 38 — the layer gets auto-styled with `apply_graduated_style` afterward without being asked separately. |
| Styling & Labeling | "Style the polygon layer by a categorized attribute." | Renderer visibly changes; confirm the color/category legend matches the actual attribute values, not a generic default. |
| AI Imagery Feature Extraction | "Extract features from [a small test image]." | Confirm this either runs (if `ultralytics`/`torch` are installed) or degrades with a clear, correctly-worded missing-dependency message — not a silent failure or a stack trace in chat. |
| Satellite Imagery & Vision | "Search for satellite imagery over the polygon layer's extent." | Real STAC search results return with real dates/thumbnails, not placeholder text. |
| Monitoring & Scheduling | "Set up a recurring workflow to check X every 10 minutes," then cancel it. | Confirm the scheduled workflow actually appears as running (check `ui/`'s scheduling indicator if any) and that cancelling it actually stops the `QTimer`, not just removes it from a list. |
| Database & Workflows | "Run a read-only SQL query against [a PostGIS-backed layer]." (skip if no PostGIS test DB available) | Confirm a write attempt in the same query is actually rejected — this exercises `SECURITY.md` §2's fail-closed read-only enforcement, the highest-value thing to verify live since it's a real security control. |
| Export & Reporting | "Export the point layer to CSV." | A real file is written to disk with the layer's actual attribute data, correct headers, no truncation. |
| Print Layouts | "Create a print layout with the current map view." | A real print layout is created in QGIS's Layout Manager, not just a chat confirmation. |
| Reporting & Document Analysis | "Extract tables from [a test PDF/Word file]." | Confirm real extracted table data appears, and that a missing-`pypdf`/`python-docx` environment degrades with the documented clear error instead of crashing. |
| Project Management | "Save the project," then "load it again." | Confirm round-trip: layers, styling, and (if enabled) chat history all survive a real save/load cycle. Also confirm `load_project` shows a confirmation preview before replacing the open project — it's one of the destructive-action-gated tools (`SECURITY.md` §5) and the model cannot self-approve it. |
| Task & Memory Management | Ask a genuinely multi-step question (e.g. "buffer this layer, then clip it to the polygon layer, then export the result"). | Confirm the Tasks tab shows a real live-updating plan with correct step statuses — this exercises `task_manager.py`'s `PREVIEW_READY`/`CONFIRMED` gate and the dock widget's plan-rendering path together, the part of the UI most dependent on a real Qt event loop. |
| System, Search & Scripting | "Search the web for [a current, verifiable fact]," and separately, ask for something that requires `execute_pyqgis_script`. | Confirm the web search returns real current results (not stale training data disguised as a search), and that the PyQGIS sandbox actually executes and actually blocks a disallowed operation if you deliberately ask for one (e.g. a file write outside the project directory) — the second half exercises `SECURITY.md` §1's sandbox live, not just its test suite. |

## After running this

- If everything above passes: note the version tested and today's date somewhere retrievable (a line
  in `CHANGELOG.md`'s entry for the release is enough) — a release that was actually smoke-tested is
  worth being able to point to later. This file's own [Run log](#run-log) below is the retrievable
  place when the release's `CHANGELOG.md` entry is already tagged/pushed and shouldn't be edited after
  the fact (`CONTRIBUTING.md` §2) — append a new dated entry there instead.
- If anything fails: that's real signal this sandbox's test suite structurally cannot produce on its
  own — file it the same way every other review round in this project's history has, with the exact
  prompt used and what actually happened vs. what the code assumed would happen.

## Run log

Append-only; each entry records one actual run against real QGIS, not a plan to run one.

**2026-09-12 — v1.8.3 — headless, not the full interactive checklist above.** No interactive QGIS
session or configured LLM provider was available, so this run drove 14 of the 16 categories
directly against real QGIS 4.2.2 (`python-qgis.bat`, real `QgsProject`/`QgsVectorLayer`/
`QgsRasterLayer`, a real GeoTIFF built with GDAL, real registered tool functions called directly
— not mocked, not a text simulation) instead of typing prompts into a live chat session. All 14
passed:

- **Vector & Geoprocessing** — `buffer_analysis` produced a real new polygon layer with the point
  layer's feature count preserved.
- **Raster** — `apply_raster_stretch` changed the renderer's real contrast-enhancement range.
- **Data Analysis & Prediction** — `calculate_severity_index` wrote a real `severity_score` field
  with 5 distinct computed values. (Auto-styling afterward per prompt rule 38 is a model-driven
  behavior, not code-enforced — not verifiable without a live LLM chat turn; see below.)
- **Styling & Labeling** — `apply_categorized_style` produced a real `QgsCategorizedSymbolRenderer`
  with the correct category count for the test data's distinct values.
- **System, Search & Scripting** — `execute_pyqgis_script` ran a real allowed script and really
  blocked a disallowed one (`open` is not a resolvable name inside the sandbox's restricted
  builtins — confirmed live, not just by reading the code); `search_web` degraded cleanly with the
  documented missing-`duckduckgo-search` message (not installed in this sandbox).
- **Export & Reporting** — `export_to_csv` wrote a real file with the correct row count.
- **Print Layouts** — `create_print_layout` registered a real layout in the project's
  `QgsLayoutManager`.
- **Project Management** — real save/load round trip preserved all 4 layers by name; confirmed
  `load_project` returns `PREVIEW_REQUIRED` without `confirmed=True` first (the destructive-action
  gate, `SECURITY.md` §5, live — not just read from the test suite).
- **Monitoring & Scheduling** — `schedule_recurring_workflow`/`stop_recurring_workflow` registered
  and cancelled a real `QTimer`-backed schedule (confirmed via `list_scheduled_workflows`, not just
  that the calls returned success).
- **Humanitarian Data** — `fetch_building_footprints` made a real network call to Microsoft's
  Global ML Building Footprints index and returned 50 real features from 2 real tiles over central
  Amman, Jordan.
- **Satellite Imagery & Vision** — `search_stac_satellite_imagery` made a real STAC API call and
  returned 3 real results.
- **AI Imagery Feature Extraction** — degraded cleanly with the documented missing-`ultralytics`
  message (not installed in this sandbox).
- **Reporting & Document Analysis** — `extract_word_tables` degraded cleanly with the documented
  missing-`python-docx` message (not installed in this sandbox), against a real `.docx` already in
  this repo (`docs/DPIA_SCREENING_WORKSHEET.docx`).

**Not run, same as every prior round:** Database & Workflows' read-only-SQL check (no PostGIS test
DB available, which the checklist itself says to skip) and Task & Memory Management's live
multi-step Tasks-tab plan (genuinely needs an interactive QGIS GUI event loop plus a configured LLM
provider — a direct function call can't exercise `task_manager.py`'s `PREVIEW_READY`/`CONFIRMED`
gate or the dock widget's plan-rendering path). These two remain open items for a human running
the full interactive checklist before the next release that touches those areas.

No new bugs found this run (the release zip's own packaging bug, `BUG-2026-09-12-2`, was caught
separately while verifying the release zip installs cleanly, before this checklist run, and is
already fixed in v1.8.3).
