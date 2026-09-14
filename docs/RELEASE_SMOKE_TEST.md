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

**2026-09-14 — v1.15.6-rc1 (commit `86cc4f3`, tag `commercial-plugin-v1.15.6-rc1`) — headless,
FULL 16-category interactive checklist, run against the same already-built
`dist/cartogen_ai_v1.15.6.zip` (sha256 `90ad75c4d86969f9889765451e16a1a4eacdc2b540f2960fd80123784ae33439`)
used by the targeted 7-check run logged below.** This entry supersedes that one's "full run still
recommended" note — the full checklist has now been run. Same `python-qgis.bat` / fresh-extraction
/ `sys.path` technique as every other entry here; each category called the real tool function
directly against real `QgsVectorLayer`/`QgsRasterLayer`/`QgsProject` objects (buffer, hub-siting,
export, layout, etc. all go through real PyQGIS/GDAL/`processing.run()` calls, not mocks) — this
is a headless run, not a literal chat-UI keystroke session, so it exercises each category's real
tool-call path but not the chat widget itself (that half is already covered by the 2026-09-12
entry below). First pass caught 5 pure test-script bugs (wrong tool import path/module, a
positional/keyword argument collision, a wrong class name, a missing required `run()` wrapper for
`execute_pyqgis_script`) — all fixed in the script, not the product; re-run below is the corrected
one. **15/15 runnable categories passed, 1 explicitly skipped, 0 real product defects found:**

1. **Vector & Geoprocessing** — `buffer_analysis` on a real 3-feature point layer; buffered layer
   added to the project with 3 features.
2. **Raster** — `apply_raster_stretch(mode="color_ramp")` on a real GDAL-written GeoTIFF; renderer
   confirmed switched away from `singlebandgray`.
3. **Humanitarian Data (HDX/OSM/geoBoundaries)** — `fetch_osm_features` against the real Overpass
   API for a real bounding box (first attempt hit a transient `HTTP 504`; retried and succeeded —
   noted as ordinary third-party API flakiness, not a plugin defect).
4. **Humanitarian Logistics** — `optimal_hub_siting` against a real point layer; returned real
   ranked candidates.
5. **Data Analysis & Prediction** — `calculate_severity_index`'s `PREVIEW_REQUIRED` gate fired
   with `confirmed` omitted, then wrote a real `sev_idx` field once confirmed.
6. **Styling & Labeling** — `apply_categorized_style` on the point layer's `name` field; renderer
   confirmed switched to `categorizedSymbol`.
7. **AI Imagery Feature Extraction** — `extract_features_from_imagery` confirmed a clean degrade
   (a real, actionable error naming the missing `ultralytics`/`torch` dependency) since neither is
   installed in this environment — the "no crash, no hang, clear message" path, not the full
   extraction path.
8. **Satellite Imagery & Vision** — `search_stac_satellite_imagery` made a real STAC API call and
   returned real results.
9. **Monitoring & Scheduling** — `schedule_recurring_workflow` started a real `QTimer`-backed
   schedule, confirmed present in `list_scheduled_workflows`, then `stop_recurring_workflow`
   confirmed it was really cancelled (absent from the list afterward), not just removed from a
   in-memory dict independent of the timer.
10. **Database & Workflows** — **SKIPPED**, per this checklist's own stated allowance: no PostGIS
    test database available in this sandbox.
11. **Export & Reporting** — `export_to_csv` wrote a real file with correct headers and data
    (also exercises SEC-002's formula-injection sanitization path).
12. **Print Layouts** — `create_print_layout` added a real entry to
    `QgsProject.instance().layoutManager()`, confirmed present by name afterward.
13. **Reporting & Document Analysis** — real PDF extraction via a genuine `pypdf`-written PDF
    succeeded; a `.docx` path confirmed a clean, explicit `python-docx`-missing degrade (not
    installed in this environment) rather than a crash.
14. **Project Management** — `save_project`/`load_project` round-tripped a real `.qgz` file;
    `load_project`'s destructive-action `PREVIEW_REQUIRED` gate fired before `confirmed=True`,
    and the reloaded project still had the expected layers afterward.
15. **Task & Memory Management** — a real multi-step `CartogenAi.run()` call (fake multi-turn
    client, real tool dispatch, real live `AgentTaskManager` instance) completed without error.
    Note: this exercises the tool-calling loop and task-manager plumbing for real; it does not
    verify the Tasks/Activity tab's own live-updating UI rendering, which needs the actual dock
    widget (covered separately by the 2026-09-12 entry's UI-focused checks).
16. **System, Search & Scripting** — `search_web` confirmed a clean, explicit degrade (naming the
    missing `duckduckgo_search` dependency) rather than a crash; `execute_pyqgis_script` actually
    **blocked** a disallowed `os.system(...)` call at the sandbox's safety-validation layer, live,
    and actually **allowed** and correctly returned the result of a legitimate read-only script.

No product code changes resulted from this run — every category either passed cleanly against
real QGIS/GDAL/network calls, or hit a real, already-documented missing optional dependency and
degraded exactly as designed. Optional-dependency inventory for this environment, checked
separately: `psycopg2`/`pandas`/`openpyxl`/`matplotlib`/`pypdf` available; `docx`
(python-docx)/`ultralytics`/`torch`/`duckduckgo_search`/`folium`/`pdfplumber` MISSING.

---

**2026-09-14 — v1.15.6-rc1 (commit `86cc4f3`) — headless, targeted at the audit's own changes,
run against the actually-built `dist/cartogen_ai_v1.15.6.zip`.** Not the full 16-item interactive
checklist above (this was specifically the release-candidate gate for the 2026-09-13/14 audit
remediation, `docs/audits/`) -- built the real zip via `python plugin_upload.py`, extracted it
fresh (not the dev tree), added both `apps/qgis/python/plugins` (for `processing`) and the
extracted zip's own `cartogen-ai/src` to `sys.path` via `python-qgis.bat`, same technique as the
v1.12.0 run below. 7/7 checks passed, each exercising a real PyQGIS call, not a mock:

1. **Plugin imports cleanly from the packaged zip** (not the dev tree -- confirmed via
   `__file__` path) with all 169 tools registered in `TOOL_REGISTRY`.
2. **`buffer_analysis`** ran a real `native:buffer` `processing.run()` call against a real
   in-memory point layer and added the resulting buffered layer to the project.
3. **`apply_raster_stretch`** (QGIS-005's None-guard fix site) ran against a real GDAL-written
   GeoTIFF and returned success -- confirms the new explicit enum-resolution check didn't
   break the real, currently-resolving-fine path on this QGIS version. One benign
   `DeprecationWarning` surfaced (`QgsRasterInterface.bandStatistics()` -- `Qgis.RasterBandStatistic`
   preferred over a bare `int` going forward); noted as a low-priority future-compat item, not
   a failure -- the call still works correctly today.
4. **`calculate_severity_index`** (QGIS-008's confirmation gate) fired `PREVIEW_REQUIRED`
   against a real 3-feature layer with `confirmed` omitted, confirmed the field did NOT exist
   yet, then actually wrote the field for real once called again with `confirmed=True`.
5. **PERF-001's mitigation** -- confirmed live (not just via the test suite) that
   `fetch_nasa_active_fires`/`fetch_nasa_eonet_events`/`fetch_gdacs_disaster_alerts` are absent
   from `_ALLOWED_WORKFLOW_TOOLS` in the actually-packaged code.
6. **PERF-002's mitigation** -- confirmed `_MAX_HUB_SITING_PAIRS` and its guard function exist
   and reject an oversized pair count in the packaged code.
7. **Dock/Chat widget** construct cleanly from the packaged code (`QgsApplication` + real `QApplication`,
   offscreen platform) and API-007's `_attachment_disclosure_note()` is present and callable.

Package provenance recorded alongside this run: `dist/cartogen_ai_v1.15.6.zip`, sha256
`90ad75c4d86969f9889765451e16a1a4eacdc2b540f2960fd80123784ae33439`, built from commit `86cc4f3`
(tag `commercial-plugin-v1.15.6-rc1`). Not run: the full 16-category interactive checklist above
(this was a targeted regression gate for the audit's specific changes, not a general release
smoke test) -- a full run is still recommended before any final (non-rc) release.

**2026-09-12 — v1.11.0 + v1.12.0 — headless, not the full interactive checklist above, run
against the actually-released v1.12.0 zip.** Both releases are from the same real-session
user-feedback thread; v1.11.0 never got its own logged run before v1.12.0 shipped the same day,
so this one consolidated run covers everything from both, driven against a **fresh extraction of
the released `cartogen_ai_v1.12.0.zip`** (not the dev tree) via `python-qgis.bat` — this is
exactly what a real user installs. `apps/qgis/python/plugins` was added to `sys.path` and
`Processing.initialize()` called explicitly, since neither is on the default path/initialized in
this bare `QgsApplication([], True)` invocation (confirmed: `import processing` fails without
it) — needed to exercise `processing.run()`-based tools like `buffer_analysis` for real instead
of them degrading to "QGIS not available". All 11 checks passed:

- **Dock structure** — exactly 2 tabs (Chat, Activity), no Help tab (moved to the Plugins menu);
  the Activity tab's `QScrollArea` confirmed `ScrollBarAlwaysOff` horizontally; zero
  `chipButton`-named widgets left in the Chat tab and `_send_quick_prompt` confirmed removed; a
  fresh `TasksTabWidget` swept for any remaining `"X & Y"` (bare-ampersand-then-space)
  Qt-mnemonic-glitch widget label — none found.
- **Chat bubble, the actual v1.11.0→v1.12.0 regression** — rendered a real user message, grabbed
  **only** the `QTextBrowser` (not the whole `ChatTabWidget`, which has its own accent-colored
  QSS chrome — the exact trap that produced a false-positive "confirmation" during development),
  and scanned for a narrow (≤8px), vertically-repeated run of the exact accent RGB value at a
  stable x position: found, confirming the left-accent stripe genuinely renders this time, not
  just that the color exists somewhere in a screenshot. Also confirmed the outer bubble alignment
  table still carries `border="0"` (no double-border regression).
- **Help menu** — confirmed `version_action` no longer exists anywhere in `plugin_main.py`'s
  source; `show_help()` builds a real `QDialog` without raising; `_read_plugin_version()` reads
  `1.12.0` from the packaged `metadata.txt`.
- **Help auto-show / onboarding trigger** — exercised all 3 real states through
  `_maybe_show_first_use_dialogs()` with a mocked `iface`: first-ever run triggers both the
  onboarding dialog and Help; a repeat call at the same version with onboarding already marked
  completed triggers neither; a simulated version bump re-triggers Help only, not onboarding.
- **Onboarding profile, full round trip** — built a real `OnboardingDialog`, confirmed the
  Other-role free-text field enables/disables correctly, saved a profile (role="other" with free
  text, experience, style) to a real temp-dir `.md` file, confirmed the file's actual content,
  confirmed `get_formatted_onboarding_context()` reads it back, confirmed
  `build_system_prompt(user_profile_ctx=...)` actually includes it, and confirmed reopening the
  dialog (simulating Settings → Edit My Profile) pre-fills every field from the saved file.
- **Chat tool-call summary + Details toggle** — simulated a real 2-turn, 4-tool-call session
  through `_add_tool_step`/`_flush_tool_steps_summary`: confirmed "running" status updates
  `status_label` in place (not scrollback), the collapsed summary line and the always-visible
  failure detail both render, and — the one piece of real technical risk in this whole thread —
  clicking the first turn's Details toggle correctly **shifts** the second turn's stored
  `QTextCursor` block position, and the second block's own toggle still targets the right span
  and expands correctly afterward. This is exactly the class of Qt behavior that looks right in
  code and isn't (the same lesson the bubble-border fix itself already taught this session
  twice) — proving the shift-adjustment math is actually correct, not just plausible.
- **Representative general-tool regression sample** — `buffer_analysis` (via `processing.run()`,
  real `native:buffer` algorithm) produced a real, findable output layer from a real 3-feature
  point layer; `calculate_severity_index` computed real per-feature scores against 2 indicator
  fields. Confirms none of this session's UI-only changes touched the tool-calling path — no tool
  code was modified across either release.

No new bugs found this run. `dist/cartogen_ai_v1.12.0.zip` is confirmed to actually work as
packaged, not just as source.

**2026-09-12 — v1.10.0 — headless, not the full interactive checklist above.** Same environment
constraint as the runs below, so this reuses that run's script again, re-executed fresh against
v1.10.0's code, plus 5 new checks for this release's own headline feature (UI & Chat Redesign).
All 22 passed:

- The same 17 categories as the v1.9.0 run below, unchanged results — confirms this release
  introduced no regressions in the existing tool surface or the hazard-monitoring tools.
- **UI & Chat Redesign (theme detection + brand accent)** — `_detect_theme_mode()` correctly
  returned `"light"` for the sandbox's default palette; `_brand_accent()` confirmed to actually
  blend QGIS's real accent color (`#0067c0`) toward the brand teal (`#0b6ea3` — distinct from
  both the raw QGIS color and the full brand teal, confirming a blend, not a replacement).
- **UI & Chat Redesign (icon rendering)** — all 4 hand-authored SVG icons (attach/send/stop/
  settings) render as real, non-null `QIcon`s via `themed_icon()`.
- **UI & Chat Redesign (toolbar icon)** — the shipped `icon.svg` (the real brand mark, replacing
  the old flat PNG) loads as a real, non-null `QIcon`.
- **UI & Chat Redesign (chat tab wiring)** — constructed the real `ChatTabWidget` and confirmed
  the attach/send/stop buttons actually carry the new icons (not just that `icons.py` works in
  isolation), and that the Preview panel's bypass-send button reads "Send as typed instead",
  matching the Refinement panel exactly.
- **UI & Chat Redesign (dock header wiring)** — constructed the real `CartogenAiDockWidget` and
  confirmed the Settings button carries its new icon.

No new bugs found this run.

**2026-09-12 — v1.9.0 — headless, not the full interactive checklist above.** Same environment
constraint as the v1.8.3 run below (no interactive QGIS session or configured LLM provider), so
this reuses that run's script, re-executed fresh against v1.9.0's code, plus 3 new checks for
this release's own headline feature (Live Hazard Monitoring). All 17 passed:

- The same 14 categories as the v1.8.3 run below, unchanged results — confirms this release
  introduced no regressions in the existing tool surface.
- **Live Hazard Monitoring (fetch tools)** — `fetch_nasa_active_fires` degraded cleanly with the
  documented missing-API-key message (no real FIRMS key in this sandbox); `fetch_nasa_eonet_events`
  made a real network call, created a real layer, tagged it `OBSERVED` confidence, and stamped a
  real `cartogen_ai/fetched_at` timestamp; a second fetch confirmed replace-in-place (still
  exactly 1 layer, not a duplicate); `fetch_gdacs_disaster_alerts` made a real network call (99
  real alerts) and tagged `DERIVED` confidence.
- **Live Hazard Monitoring (scheduler diff cycle)** — a saved workflow running
  `fetch_gdacs_disaster_alerts` through `run_monitoring_workflow` twice confirmed
  `previous_run_at` populates correctly on the second run and `diffs_since_last_run` is reported
  — the real diff-since-last-run mechanism working end to end against live hazard data, not just
  unit-tested in isolation.
- **Live Hazard Monitoring (situation dashboard)** — `generate_situation_dashboard` degraded
  cleanly with the documented missing-`folium` message (known, pre-existing gap in this
  sandbox's QGIS Python env, not new to this release).

No new bugs found this run.

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
