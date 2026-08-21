# QGIS AI Agent — PRD Implementation Task List

**Target PRD Document:** [QGIS_AI_Agent_PRD.md](file:///c:/qgis_ai_assistant/QGIS_AI_Agent_PRD.md)
**Status:** Verified against actual code on 2026-08-09, re-verified and extended 2026-08-10 to cover
the Task Manager revamp and related fixes built since. Checkboxes below reflect what's actually
implemented, not what was originally planned — several items that were previously checked `[x]`
turned out to be stale, overstated, or describing functionality that was deliberately replaced.

---

## Work Package 1: Architecture & Foundation Hardening (Phase 1 Refinements)

- [x] **1.1 Credential Security Migration**
  - [x] Replace plaintext `QgsSettings` API key storage with QGIS `QgsAuthManager` (encrypted keyring storage), with a `QgsSettings` fallback if the auth manager is disabled/unavailable.
  - [x] Provider clients read credentials via `CredentialManager.get_credential()` — single canonical provider→settings-key mapping shared by save/load (an earlier version had two mismatched mappings that caused saved keys to silently vanish).
- [x] **1.2 Native Async Task Pipeline (`QgsTask`)**
  - [x] Agent execution (`agent.run()`) runs inside `AgentQgsTask` (`agent/task_runner.py`), a real `QgsTask` on a background thread — not `threading.Thread`.
  - [x] Cross-thread PyQGIS access uses a `ToolDispatcher` (`Qt.BlockingQueuedConnection`) so tool calls that touch `QgsProject`/layers/canvas run safely on the main thread while the LLM loop itself stays off it. Pure-network tools bypass this dispatch entirely (`NETWORK_ONLY_TOOLS`); tools that mix a fast QGIS-state read with a slow network call split the two (`TWO_PHASE_TOOLS`) so neither blocks the GUI.
- [ ] **1.3 Automated Test Harness Setup**
  - [ ] ~~Configure `pytest-qgis`~~ — **not done**. No `pytest_qgis` plugin anywhere in the repo; `pytest.ini` is a plain pytest config, not the pytest-qgis harness that provides a real (mocked) QGIS runtime for tests.
  - [x] Unit test suite exists and passes (95 tests, `python -m unittest discover -s tests`), but every QGIS-touching module tests via its own `QGIS_AVAILABLE = False` fallback branch rather than a real QGIS test environment — meaning tests verify graceful degradation and pure logic, not actual PyQGIS behavior (geometry creation, rendering, layer validity, etc.). **Needed:** adopt `pytest-qgis` (or an equivalent QGIS test runner) if actual PyQGIS execution needs to be covered by automated tests rather than manual smoke-testing.
- [x] **1.4 Dependency Handling** *(scope changed from "vendor management" — see rationale)*
  - [x] ~~Automated OSGeo4W Shell installer helper~~ — **deliberately removed**. Running `pip`/`subprocess` from inside a plugin is a known QGIS-community anti-pattern (can break global libraries, need admin rights the user doesn't have, or downgrade another plugin's dependency).
  - [x] Replaced with `plugin_dependencies=qpip` in `metadata.txt` + `requirements.txt`, so QGIS offers a proper install dialog via the qpip dependency-manager plugin.
  - [x] Graceful in-chat fallback (`agent/deps.py`: `verify_dependencies()`, `get_dependency_warning_message()`) when qpip isn't installed — clear manual `pip install` instructions, no crash, no silent failure.
  - [x] All optional packages (`pypdf`, `python-docx`, `openpyxl`, `pandas`, `duckduckgo-search`) are imported lazily inside `try/except` at point of use, never at module/`__init__.py` load time, so a missing package can never crash plugin load.
- [~] **1.5 Plugin Packaging & Release Engineering**
  - [ ] ~~`resources.qrc` + automated `pyrcc5` compilation pipeline~~ — **not real**. `resources.qrc` and the `resources/` directory (duplicate icon files) exist but are dead weight: nothing in the codebase imports or compiles them. `metadata.txt`'s `icon=icon.png` points at the root icon instead. Both are now excluded from the packaged zip.
  - [~] `plugin_upload.py` — **local packaging only, not "automated publishing"**. It zips the plugin (excluding dev files/dirs) into `dist/qgis_ai_assistant_v{version}.zip`. It does **not** upload anywhere — there's no HTTP call, no QGIS Plugin Repository API integration, no credentials. Uploading to the repository still requires a manual step via the repository's website. **Needed if true automation is wanted:** the QGIS Plugin Repository has no official upload API for this — manual upload via https://plugins.qgis.org is the standard path even for most published plugins, so this may not be worth automating further.
  - [x] GPL-v2 license compliance audit performed (`LICENSE_AUDIT.md`) — covers the optional Python packages (`pypdf`, `python-docx`, `openpyxl`, `pandas`, `duckduckgo-search`, `requests`) and external REST APIs used. Note: doesn't need updating for the newer AI providers (Groq/Cerebras/DeepSeek/OpenAI/Claude) since those are HTTP endpoints, not vendored Python packages.

---

## Work Package 2: Safety, Transparency & Lineage Controls

- [~] **2.1 Destructive Action Safety (`PREVIEW → CONFIRM → APPLY`)**
  - [x] `AgentTaskManager` supports a `PREVIEW_READY`/`PREVIEW_REQUIRED` state — destructive tools (`remove_layer`, `field_calculator`) return this instead of executing.
  - [~] **Affected-layer preview added (2026-08-10), still not a full diff.** Selecting a `PREVIEW_READY` task now flashes the target layer's extent on canvas (`ui/dock_widget.py`'s `_flash_preview_layer`, reusing `ui/canvas_highlight.py`'s `flash_layer_extent`) so the user can see *which* layer is about to change. This is honestly scoped as an affected-layer highlight, not a before/after geometry diff — a true diff would need running the edit read-only first and rendering two geometries, a materially larger change not attempted here.
  - [x] Explicit confirmation button in the UI task panel ("✅ Confirm & Apply Edit") — real user click required; the LLM cannot self-approve (dispatcher strips any `confirmed`/`user_confirmed` argument the model tries to inject, verified by `test_dispatcher_schema_filtering_prevents_bypass`).
- [x] **2.2 Execution Transparency & Inspector**
  - [x] System prompt requires exposing the actual QGIS expression / PyQGIS code used for a step.
  - [x] "🔍 Task Inspector & Preview Safety" panel in the dock (`ui/dock_widget.py`) shows the code snippet and rationale for the selected task, plus a "📋 Copy Snippet" button (clipboard copy of the raw code) added in the 2026-08-10 Task Manager revamp.
  - [x] Task list rows are now color-coded cards (status-tinted background, tool-name badge, relative timestamp) instead of plain text, and a progress bar shows `X/N steps complete` for the active plan — also from the 2026-08-10 revamp.
- [x] **2.3 Metadata & Lineage Tracking Engine**
  - [x] `tag_layer_lineage(layer, tool_name, params, source_layers)` (`agent/lineage.py`).
  - [x] Lineage written to `customProperty("qgis_ai_agent/lineage")` on the created/modified layer, called automatically from `_real_execute_tool`'s success path (and mirrored for the two-phase tools via `_log_tool_success`).
- [x] **2.4 Action Rationale & Explainability**
  - [x] `rationale` field attached to preview tasks during planning.
  - [x] Rendered in the dock's rationale label / Task Inspector panel.
  - [x] **Bug fix (2026-08-10):** a real, user-reported failure mode where the model would call `create_plan` once and then do the actual work via other tools without ever calling `update_task`, leaving the plan frozen on TODO forever even though the work genuinely completed. Fixed at the code level (not just a prompt request) via `AgentTaskManager.auto_advance_if_unambiguous()`: after any successful tool call, if exactly one task is still open, it's automatically marked DONE — conservative by design, only fires when there's no ambiguity about which task the work belongs to.
  - [x] **Diagnostic logging (2026-08-10):** every tool call the agent makes is now printed to the QGIS Python Console (`agent.py`'s `run()` loop) with its name, arguments, and success/failure — added to debug a separate, still-unconfirmed reported bug where the model's final text claimed a "backend issue" despite the underlying tool call actually succeeding (see project memory `pending-tool-result-narrative-mismatch`).

---

## Work Package 3: Tier 1 & Tier 2 Recommended Features (Phase 2 Core)

- [x] **3.1 Geometry & Topology Diagnosis Engine** — `diagnose_topology(layer_name)`, structured counts, `fix_geometries` available separately.
- [x] **3.2 Proactive CRS Mismatch Detection** — `verify_crs_compatibility`, called before `clip_layer`/`intersect_layers`/`union_layers`/`spatial_join`.
- [x] **3.3 Conversational Map Interrogation** — zonal statistics tools (`raster_tools.py`) + natural-language summarization via the agent loop.
- [x] **3.4 Humanitarian Data Fetch Assistant** — HDX search (`search_hdx_datasets`), OSM Overpass (`fetch_osm_features`), geoBoundaries (`fetch_geoboundaries`, now split into a background network phase + main-thread layer-creation phase to avoid blocking the GUI).
- [x] **3.5 Smart Symbology & Colorblind-Safe Classification** — `apply_graduated_style` analyzes field distribution for classification method; `apply_categorized_style`/`apply_heatmap_style` also present.
- [x] **3.6 Natural Language Print Layout Generator** — `create_print_layout` (`layout_tools.py`) builds a real `QgsPrintLayout` with legend/scalebar/north arrow and exports.

---

## Work Package 4: Database Security & Workflow Persistence (Phase 2/3)

- [x] **4.1 Secure PostGIS & SpatiaLite Integration**
  - [x] `execute_read_only_sql` — rejects destructive SQL keywords (`DROP`, etc.) before executing (verified by `test_sql_read_only_guard`).
  - [x] **Database-level enforcement added (2026-08-10):** `_enforce_db_read_only()` opens a real connection via `QgsProviderRegistry.instance().providerMetadata("postgres").createConnection(...)`, best-effort issues `SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY`, then executes the query on that same connection before the existing `QgsVectorLayer` path runs — so an obfuscated statement that dodges the keyword blocklist is now rejected by Postgres itself. Degrades to a no-op (keyword-blocklist-only, as before) if the connection API isn't available. **Caveat:** not verified against a live PostGIS server in this environment — only the graceful-degradation path is covered by an automated test.
- [~] **4.2 Re-editable Saved Workflow Schema**
  - [x] `save_workflow_preset(preset_name, workflow_json)` / `load_workflow_preset(preset_name)` exist (`db_and_workflow_tools.py`) — persist/restore a JSON blob via `QgsSettings`.
  - [x] **Step-level editing added (2026-08-10):** a "✏️ Edit & Resend" button (any task status, not just `FAILED`) pre-fills the chat box with an editable prompt for that task without auto-sending — the pragmatic version of re-editability rather than dynamic per-tool-schema parameter forms. Combined with the existing "🔁 Retry" button (`FAILED` tasks, auto-sends "retry as-is"), this now covers both "redo with changes" and "just try again."
  - [x] **Plan history (2026-08-10):** starting a new plan (or clicking the new "✕ Clear Plan" button) archives the previous plan into a capped, rolling history (last 5) instead of discarding it — browsable via a dropdown in the Tasks & Memory tab (`AgentTaskManager.plan_history` / `get_plan_history()`).
- [ ] **4.3 Scoped Scheduled / Recurring Workflows** — **not implemented at all**. No `schedule_workflow_execution` tool, no `qgis_process` headless adapter, nothing matching this anywhere in the codebase. This was pulled forward into "Phase 2 (Near-Term)" in the PRD but never built. **Needed** if recurring/scheduled execution (e.g. a weekly sitrep auto-update) is still a priority — would need a `QgsTask`-based timer or an external scheduler trigger via `qgis_process`.

---

## Work Package 5: Multimodal & Remote Sensing (Phase 3 Mid-Term)

- [x] **5.1 STAC Satellite Imagery Fetcher** — `search_stac_satellite_imagery` (Earth Search/Sentinel-2). **Caching + quota guard added (2026-08-10):** identical queries within a 10-minute TTL are served from an in-memory cache (`_STAC_CACHE`), and a hard cap of 20 requests per plugin session (`_STAC_MAX_REQUESTS`) returns a clear error instead of calling the API once exceeded.
- [x] **5.2 Multimodal Visual Canvas Inspection** — `inspect_canvas_visually` captures the canvas for vision-capable models.
- [ ] **5.3 Automated Feature Extraction from Imagery** — **not implemented**. No building-footprint/road-extraction tool exists.
- [x] **5.4 Time-Stamped Layer Change Detection** — `calculate_raster_change_detection` (pixel-wise differential between two temporal rasters).

---

## Work Package 6: Scaling & Memory Optimization (Phase 4 Vision)

- [x] **6.1 Sidecar SQLite Spatial Memory** — `agent/memory.py` genuinely uses `sqlite3` against a `.sqlite` file next to the project (not just `QgsProject` custom properties). Verified via direct code read, not just trusting the doc.
- [ ] **6.2 Feedback Loop & Correction Memory** — **not implemented**. No code captures user overrides/corrections on agent-generated layers, and nothing stores "correction patterns" back into memory.
- [x] **6.3 Multi-Layer Join Assistant** — **implemented (2026-08-10)** as a new tool, `join_by_attribute` (`vector_tools.py`), distinct from the location-based `spatial_join`. Suggests candidate field pairs via `difflib.get_close_matches` when `target_field`/`join_field` aren't specified, and warns (`cardinality_warning`) when the join field isn't unique on the join-layer side before running `native:joinattributestable`.
- [x] **6.4 Tool Retrieval / Semantic Search Router** — `ToolRouter` (`agent/tool_router.py`) keyword/intent-scores tool schemas and filters to `top_k` before every request, so the 78-tool registry doesn't blow out every prompt's context.

---

## Additional work completed beyond this task list's original scope

Substantial functionality was built after this list was last accurate that isn't reflected in the
work packages above:

- **5 additional AI providers** (Groq, Cerebras, DeepSeek, OpenAI, Claude/Anthropic) beyond the original OpenRouter/Gemini/Ollama trio — including a full request/response translation layer for Claude's native Messages API format, since it differs from the OpenAI-compatible shape the others share.
- **Gemini Pro model support**, live model-list fetching per provider, and deterministic complexity-based auto-model-routing.
- **Gemini automatic model fallback** — a dead/deprecated model ID (e.g. `gemini-2.5-pro` returning 404 "no longer available to new users") no longer permanently breaks the provider; it now falls through a verified chain (`gemini-flash-latest` → `gemini-3.6-flash` → `gemini-2.5-flash`).
- **Native Gemini Google Search grounding** (`gemini_grounded_search`) for source-cited, real-time facts, gated to only work on the Gemini provider.
- **AST-based safety validator** on `execute_pyqgis_script` — blocks `os`/`subprocess`/`shutil`/`eval`/`exec`/etc. before the script runs, closing a real arbitrary-code-execution gap that existed alongside the destructive-action confirmation gates.
- **Proactive map-context injection** into the system prompt every turn (active layer, CRS, loaded layers/fields/counts) — the agent no longer needs a round-trip `get_layers()` call just to know what's loaded.
- **Persistent, project-bound chat history** (`agent/chat_persistence.py`), including correct reload when the user switches QGIS projects mid-session (`QgsProject.instance().readProject`/`.cleared` signal handling).
- **Canvas highlighting** when a reply mentions a loaded layer by name; **quick suggestion chips** under the chat input.
- **`add_point_layer`** — bulk point-feature creation (e.g. "map the foreign embassies in Jordan") in a single tool call, added after a real bug where one-tool-call-per-point exhausted the agent's step limit before finishing.
- **`add_incident_point`** — single-point incident/event plotting with hardcoded professional cartography (red marker, white-background/red-text label) so styling can't drift per request.
- **`MAX_ITERATIONS` raised 10 → 20**, and iteration-limit exhaustion is now saved to conversation history (previously lost, causing a retry to blindly repeat the same failing approach) with an actionable message instead of a bare "[Agent stopped]".
- **Packaging cleanup** — the release zip no longer ships internal dev docs, `pytest.ini`, `plugin_upload.py` itself, or the dead `resources.qrc`/`resources/` scaffolding (57 files → 45).
- **Task Manager UI revamp (2026-08-10)** — full redesign of the "Tasks & Memory" tab: progress bar (`X/N steps complete`), color-coded task cards with tool-name badges and relative timestamps, plan history dropdown (browse past plans, read-only), manual "✕ Clear Plan" button, "🔁 Retry" for failed tasks, "📋 Copy Snippet" in the Task Inspector, and a Spatial Memory panel that actually resizes with the dock plus a search/filter box and "🗑 Clear Project Memory" button. Backed by real data-model additions in `agent/task_manager.py` (`created_at`/`updated_at`/`tool_name` per task, capped `plan_history`) and `agent/memory.py` (`clear_project_notes()`).
- **Auto-advance safety net** — `AgentTaskManager.auto_advance_if_unambiguous()` fixes a real bug where a plan could stay frozen on TODO forever even though the underlying work genuinely completed, because the model called `create_plan` but never followed up with `update_task`.
- **Tool-call diagnostic logging** — every tool call is now printed to the QGIS Python Console (name, arguments, success/failure), to help diagnose a still-open, user-reported bug (see `IMPLEMENTATION_TASK_LIST.md` item 11 below).

---

## Summary of what still needs implementation (if pursued)

**Resolved 2026-08-10** (were pending, now done): STAC caching + quota guard, database-level read-only
enforcement for `execute_read_only_sql`, user-facing help panel, multi-layer join assistant
(`join_by_attribute`), affected-layer canvas preview on destructive-edit confirmation, and step-level
parameter editing (Edit & Resend). Deliberately deferred by the user rather than attempted: scheduled
workflows, feedback/correction memory, imagery feature extraction, and the `pytest-qgis` harness (all
genuinely large/roadmap-scale) — see the 2026-08-10 `AskUserQuestion` scoping decision.

Still open:

1. Real `pytest-qgis` (or equivalent) test harness for actual PyQGIS execution coverage, not just fallback-path logic. Deferred.
2. Scheduled/recurring workflow execution (`schedule_workflow_execution` / `qgis_process` headless adapter). Deferred.
3. Feedback loop / correction memory. Deferred.
4. Building-footprint/road feature extraction from imagery. Deferred.
5. Full geometry before/after diff preview on canvas (only an affected-layer highlight exists now, see WP2.1).
6. **Open bug, not yet reproduced with a trace:** the model's final chat response has been observed (once, by the user) claiming a "backend/tool issue" and offering a manual script even though the relevant tool call had actually succeeded. Mitigations are in place (system prompt rule 15, tool-result `message` fields, and permanent `[Agent]` tool-call console logging), but the root cause isn't confirmed. See project memory `pending-tool-result-narrative-mismatch` for full detail and what to check next time it happens.
7. **GitHub repository visibility.** `metadata.txt`'s `repository=`/`homepage=`/`tracker=` fields are correct (`https://github.com/baron-dev07/qgis_ai_assistant`), and git is now set up locally (via GitHub Desktop) and pushed to `origin/main`. The one remaining blocker: that repo is **private**, which conflicts with the QGIS Plugin Repository submission checklist's requirement that metadata links be publicly accessible. Needs the repo made public (or metadata pointed at a public mirror) before submission.
