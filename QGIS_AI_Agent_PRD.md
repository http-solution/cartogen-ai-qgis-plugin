# QGIS AI Agent — Product Requirements Document (v2)

**Status:** Draft for review. §3, §6 (Phase 1/2), and §7 annotated 2026-08-09 with actual
implementation status, verified against code rather than re-stamped — see `IMPLEMENTATION_TASK_LIST.md`
and `QGIS_AI_Agent_Feature_List.md` for full detail per item.
**Owner:** Alaa Al-Shoubaki
**Last updated:** 2026-08-08 (content), 2026-08-09 (status annotations), 2026-08-15 (§8 added,
cross-referencing `PRODUCT_TIERS.md`'s business-model breakdown against this roadmap)
**Supersedes:** `PRD_and_Roadmap.md` (v1)

---

## 1. Overview

The QGIS AI Agent is a QGIS plugin that lets users perform spatial analysis, data management, and cartographic output through natural-language conversation, backed by real PyQGIS and Processing calls — not a black box. It targets both GIS specialists (who need transparency and control) and non-specialist stakeholders (who need to ask questions of a map without learning QGIS).

This version consolidates the original architecture and roadmap with two rounds of feature research: a first-principles review of what users expect from an AI GIS assistant, and a competitive review of Atlas (atlas.co), a browser-based AI-native GIS product.

---

## 2. Plugin Architecture

### 2.1 Package structure & lifecycle

| Component | Responsibility |
|---|---|
| `__init__.py` | Exposes `classFactory(iface)`, returning the `QgisAiAgent` plugin instance when loaded by QGIS. |
| `metadata.txt` | Mandatory plugin metadata: `qgisMinimumVersion=3.0`, `qgisMaximumVersion=4.99`, `name`, `version`, `author`, `experimental`. |
| `qgis_ai_agent.py` | Core lifecycle: `initGui()` adds toolbar icons and menu entries via `iface.addToolBarIcon()` / `iface.addPluginToMenu()`; `unload()` removes action listeners and tears down the dock widget on unload. |

### 2.2 PyQGIS & Processing integration

- **`qgis.core`** — `QgsProject`, `QgsVectorLayer`, `QgsRasterLayer`, `QgsFeature`, `QgsGeometry`, `QgsSettings`.
- **`processing`** — invokes native QGIS algorithms, SAGA, and GDAL tools via `processing.run()`.
- **`iface`** — controls `mapCanvas()`, feature zoom extents, and attribute table dialogs.

### 2.3 Architecture gaps identified in review (v1 → v2 changes)

These were missing from the original architecture and are now formal requirements (see §4). Status
as actually resolved (2026-08-09) — two of these were resolved differently than originally envisioned
here:

- **Threading model**: LLM calls must not run on the main thread. Use `QgsTask` / `QThread` from Phase 1, not retrofitted later — synchronous calls will freeze the QGIS UI on every agent invocation. — **Done**, as originally envisioned.
- **Credential storage**: API keys (OpenRouter, Gemini) must use `QgsAuthManager`, not plaintext `QgsSettings`. — **Done**, as originally envisioned.
- **Dependency bundling**: QGIS ships its own Python environment. Any pip dependencies not present in the OSGeo4W/QGIS bundled Python need a vendored-deps folder or a first-run installer check. — **Resolved differently.** A first-run installer that ran `pip`/`subprocess` from inside the plugin was actually built at one point, then deliberately removed — it's a known QGIS-community anti-pattern (can break global libraries, needs admin rights, can downgrade another plugin's dependency). Replaced with `plugin_dependencies=qpip` + `requirements.txt` (QGIS offers a proper install dialog) plus graceful in-chat fallback instructions if qpip isn't present. No vendored-deps folder either — not needed given the qpip approach.
- **Packaging & submission**: `resources.qrc` compilation step, `plugin_upload.py` for the QGIS Plugin Repository, and a GPL-compatible licensing decision (affects what SDK code can be vendored). — **Partially resolved.** `resources.qrc`/`resources/` turned out to be unused dead weight (nothing imports or compiles them) and were removed from packaging rather than wired up. `plugin_upload.py` exists but only zips the plugin locally — it does not upload to the QGIS Plugin Repository (no such automation exists; manual upload via the repository website is still required). GPL-v2 licensing decision is done (`LICENSE` + `LICENSE_AUDIT.md`).
- **Testing**: `pytest-qgis` as the standard harness, established from Phase 1 so code is written testably rather than retrofitted. — **Not done.** Tests use plain `unittest`/pytest against per-module `QGIS_AVAILABLE = False` fallback paths, not a real (mocked) QGIS runtime via `pytest-qgis`.

---

## 3. Product Requirements Summary

| Category | Requirement Specification | Status (2026-08-09) |
|---|---|---|
| **Multi-Model Support** | OpenRouter (Cloud), Google Gemini (Vision), Ollama (Local REST) | **Exceeded** — 8 providers now (added Groq, Cerebras, DeepSeek, OpenAI, Claude/Anthropic), plus auto model routing and Gemini fallback-on-404 |
| **Agentic Planning** | Multi-step task decomposition with interactive progress states (`TODO`, `IN_PROGRESS`, `DONE`, `FAILED`) | **Met** (plus `PREVIEW_READY`/`PREVIEW_REQUIRED`/`CONFIRMED`) |
| **Spatial Memory** | Dual-layer: project memory (`QgsProject` custom properties) and global user preferences (`QgsSettings`) | **Met**, and exceeded — spatial action log also persists to a sidecar SQLite `.sqlite` file, not just project properties |
| **Tool Suite** | 61 spatial tools: vector, raster, spectral indices (NDVI/NDWI/NDRE), styling, exports, web search, geocoding, PyQGIS execution | **Met** — 78 tools currently registered; count will keep drifting, treat as approximate |
| **Credential Security** | API keys stored via `QgsAuthManager` (encrypted, OS-keyring-backed), not plaintext settings | **Met** |
| **Destructive-Action Safety** | Any tool that edits, deletes, or overwrites layer data requires a preview/diff and explicit user confirmation before applying | **Partially met** — confirmation gate is real and enforced (LLM cannot self-approve), but the "preview" is a text code snippet + rationale, not a rendered visual diff layer on canvas |
| **Explainability** | Every agent action (buffer distance, classification breaks, join logic) must be answerable with "why" from the original planning step, not reconstructed after the fact | **Met** |
| **Metadata & Lineage** | Every layer created or modified by the agent is tagged with the tool used, parameters, source data, and timestamp | **Met** |

---

## 4. Most-Wanted Features (Research Findings)

Feature research organized by priority tier, based on common friction points in AI-assisted GIS work and direct relevance to ECHO/humanitarian mapping use cases (ICRC in-limit digitization, IOM DTM work, sitrep production).

### Tier 1 — Table stakes (precede all other feature work)

1. **Natural language → QGIS Expression / Processing chain.** Generates and runs the actual expression or algorithm, and always shows the generated expression for the user to inspect and edit — never just the result. This is the single most-requested capability in AI-QGIS tooling generally.
2. **Geometry & topology repair with diagnosis.** Explains *what* is wrong ("14 self-intersecting polygons, 3 zero-area slivers") before fixing, and previews the fix on canvas before committing. Directly relevant to the existing ICRC Damascus digitization QA workflow.
3. **CRS mismatch auto-detection.** Proactively flags CRS mismatches on layer load or tool execution — the leading cause of silently-wrong spatial analysis in QGIS.
4. **Preview-before-apply for destructive operations.** Extends the existing TODO/IN_PROGRESS/DONE/FAILED state machine to a PREVIEW → CONFIRM → APPLY pattern for any write operation.

### Tier 2 — Differentiators that drive adoption

5. **Smart symbology / classification suggestions.** Recommends Jenks vs. equal interval vs. quantile based on the actual distribution of the field (skew, outliers), plus colorblind-safe palette defaults.
6. **Conversational map interrogation.** E.g. "How many people live within the flood buffer?" runs zonal stats against a loaded raster and returns a natural-language answer, not just a table. Highest-value feature specifically for sitrep/situation-assessment work.
7. **Humanitarian data discovery & fetch assistant.** Natural-language search across HDX, OSM Overpass, geoBoundaries, and other humanitarian catalogs, with preview before import — directly differentiates from generic AI-GIS tools, which largely ignore these sources. Maps to existing HDX Syria admin4 workflow.
8. **Auto-generated metadata & lineage.** (See §3 — promoted to a formal requirement.)
9. **Print layout generation from natural language.** "Make an A3 situation map with legend, north arrow, scale bar, and country inset" generates a `QgsPrintLayout` programmatically. Direct time-saver for ECHO mission reports and sitreps.
10. **Explainability on every agent action.** (See §3 — promoted to a formal requirement.)

### Tier 3 — Roadmap-stage differentiators

11. **Semi-automated feature extraction from imagery.** Building footprint / road extraction from satellite or aerial imagery via vision models — relevant to damage assessment and in-limit digitization currently done manually.
12. **Change detection between time-stamped layers/images.** Core humanitarian-GIS demand for damage assessment and displacement tracking.
13. **Accessibility/routing in plain language.** E.g. "Which health facilities are unreachable given the damaged bridge" — network analysis wrapped in conversation.
14. **Feedback loop / correction memory.** User corrections to agent output (fixed geometry, reclassified feature) feed back into project memory so the same mistake isn't repeated within the project — this is what makes the dual-layer spatial memory requirement earn its value rather than just storing chat history.
15. **Multi-layer join assistant.** Suggests join fields via fuzzy column-name matching and value-overlap sampling; flags 1-to-many cardinality issues before a join silently duplicates features.

**Recommended priority for next release (pick 5):** #1, #2, #6, #7, #9 — these map directly to real friction in current ICRC/IOM digitization and ECHO sitrep workflows, rather than generic AI-assistant features.

---

## 5. Competitive Analysis — Atlas (atlas.co)

Atlas is a browser-based, multi-tenant "AI-native GIS" (agent name: **Navi**) built around live, shared, data-connected maps — architecturally distinct from a desktop QGIS plugin, but several product ideas are directly portable.

### 5.1 Ideas adopted into this PRD

| Atlas concept | Adaptation for QGIS AI Agent |
|---|---|
| Agentic workflows on an editable, inspectable canvas — Navi "chains analysis, scheduling, and alerts across your data, then hands you the canvas to inspect and edit every step." | Extend the TODO/IN_PROGRESS/DONE/FAILED state machine so completed steps are clickable, revealing the actual PyQGIS/Processing call, with parameters editable and the step individually re-runnable. |
| Live, synced data connections (PostgreSQL, Google Sheets, CSV) rather than one-time imports. | For Phase 2 PostGIS/SpatiaLite querying: saved workflows against a PostGIS view or synced source should re-pull fresh data automatically on re-run, not require manual layer reload. |
| Scheduled workflows — "daily site screenings, weekly status reports, and live alerts — without writing a cron job or owning a server," including an AI-authored weekly status update that flags changes and emails the team. | Pull forward from Phase 4 vision into Phase 2/3 scope: a scheduled/recurring workflow object (saved workflow JSON + `QgsTask` or external scheduler / `qgis_process` headless trigger) for e.g. a weekly Damascus ICT infrastructure status or auto-drafted sitrep when new IOM DTM data lands. |
| Domain-specific analysis presets (wind power estimation, aspect-slope, sunlight-hours) rather than raw tool assembly. | Package named humanitarian presets — "population-weighted health-facility accessibility," "flood-affected building count," "in-limit boundary QA" — as one-shot workflows the agent recognizes by name. |
| Positioning: "GIS-grade underneath, conversational on top" — "Navi is an accelerator, not a black box." | Adopt as an explicit design principle and messaging line in plugin docs, to preempt GIS-specialist skepticism that this is "just a chatbot." |

### 5.2 Explicitly out of scope

Atlas's multi-tenant SaaS features — team sharing via public map links, billing, browser-hosted rendering — do not transfer to a single-user desktop plugin and should not be replicated. If multi-user collaboration becomes a real need, it is better solved via GeoPackage sync to a shared location (see Phase 4 "team GeoPackage memory synchronization") than by rebuilding Atlas's cloud architecture inside QGIS.

### 5.3 Gap this exposed in the existing roadmap

**Scheduled/recurring workflows** and **step-level re-editability** were absent from Phase 1–2 scope entirely. Both are low-cost to add now (primarily a saved-workflow JSON schema plus UI, not new PyQGIS capability) and expensive to retrofit once the task-planning subagent architecture is locked in — recommend moving a scoped version into Phase 2.

---

## 6. Product Roadmap & Feature Forecast (Revised)

### Phase 1 (v0.1 – v0.2, Current) — ✅ done, and exceeded
- Modular tool registry — 78 tools (started at 61)
- Dual-layer spatial memory (project + global settings + sidecar SQLite, done — see §3)
- Task-planning subagents with TODO/IN_PROGRESS/PREVIEW_READY/CONFIRMED/DONE/FAILED states
- Multi-provider model support — 8 providers (started at OpenRouter/Gemini/Ollama), plus auto-routing and Gemini fallback-on-404
- `QgsTask` async execution model — done, and hardened further: pure-network tools bypass main-thread dispatch entirely, mixed network+QGIS tools split into a background network phase + main-thread QGIS phase
- `QgsAuthManager` credential storage — done
- **`pytest-qgis` test harness — NOT done.** Tests run via plain `unittest`/pytest against each module's own `QGIS_AVAILABLE = False` fallback path, not a real (mocked) QGIS runtime. Still a gap if actual PyQGIS execution needs automated coverage.
- **Not originally scoped, but built:** AST-based safety validator on `execute_pyqgis_script`; proactive map-context injection; persistent project-bound chat history with correct reload on project switch; canvas highlighting; quick suggestion chips; qpip-based dependency management (replacing an earlier subprocess-based auto-installer that was removed as a known anti-pattern); native Gemini Google Search grounding; bulk point-layer creation (`add_point_layer`).

### Phase 2 (v0.3, Near-Term) — partially done
- ✅ PostGIS/SpatiaLite spatial SQL querying — done via `execute_read_only_sql`, but enforcement is a **keyword blocklist** (rejects `DROP`/etc.), not a database-level read-only role. The stronger guarantee this line originally called for is still open if it's a hard requirement.
- ✅ Automated print layout compositions (PDF) — done
- ✅ Canvas selection interactions — done (`select_by_attribute`, `highlight_features`, canvas layer highlighting on mention)
- ✅ Geometry/topology diagnosis + CRS mismatch detection (Tier 1 features, §4) — done
- ✅ Preview-before-apply for destructive operations — done (text preview + explicit confirmation; not a visual diff layer)
- ✅ **Scoped scheduled/recurring workflow object — shipped (2026-08-16), in-session scope.** `schedule_recurring_workflow`/`run_monitoring_workflow` (`agent/tools/monitoring_tools.py`) re-run a saved read-only analysis workflow on a `QTimer` for as long as QGIS stays open, diffing per-unit results each tick. Deliberately does NOT include a `qgis_process` headless adapter or OS-scheduler registration -- decided via an explicit design check-in rather than assumed, since registering a cron/Task Scheduler entry is a system-settings change out of scope for this plugin to make unilaterally. See `CHANGELOG.md`.
- ⚠️ **Saved-workflow re-editability on canvas — partially done.** `save_workflow_preset`/`load_workflow_preset` persist/restore a JSON blob, but there's no UI for editing a *completed* step's parameters and re-running it — only confirming a still-pending preview.

### Phase 3 (v0.4, Mid-Term) — partially done
- ✅ STAC satellite imagery fetchers (Sentinel-2/Landsat API) — done, but **without** caching or a request-quota guard; nothing currently prevents repeated STAC queries from burning API quota within a session beyond the general `MAX_ITERATIONS` cap
- ✅ Multimodal visual canvas inspection via vision LLMs — done (`inspect_canvas_visually`)
- ❌ Voice-to-spatial commands — not started
- ❌ Semi-automated feature extraction from imagery (Tier 3, §4) — not started
- ✅ Change detection between time-stamped layers/imagery (Tier 3, §4) — done

### Phase 4 (v1.0, Vision)
- Multi-agent spatial swarms
- Team GeoPackage memory synchronization — **requires a concurrency/conflict-resolution model defined before implementation**, given the data-corruption risk of concurrent GeoPackage edits
- Headless QGIS Server AI agent integration
- Feedback loop / correction memory (Tier 3, §4)
- Multi-layer join assistant (Tier 3, §4)

---

## 7. Open Risks & Decisions Needed

| Risk | Mitigation direction | Status (2026-08-09) |
|---|---|---|
| LLM-generated SQL against PostGIS could execute destructive statements | Enforce read-only DB role; do not rely on prompt instructions alone | **Partially mitigated** — `execute_read_only_sql` blocklists destructive keywords (`DROP`, etc.), which is not the same guarantee as a DB-enforced read-only role. Still open if the stronger guarantee is required. |
| Plaintext API key storage | Migrate to `QgsAuthManager` before first public release, not after | **Mitigated** |
| Synchronous LLM calls freezing QGIS UI | Establish `QgsTask` pattern in Phase 1 architecture, not retrofitted | **Mitigated, and hardened further** — two real freeze bugs were found and fixed after the initial `QgsTask` migration: pure-network tools were still bouncing through the main-thread dispatch, and two tools mixed network I/O with QGIS layer creation in one blocking call. |
| Tool-selection accuracy degrading as registry grows past 61 tools | Add a routing/retrieval layer (embed tool descriptions, retrieve top-k per request) rather than passing all schemas into every planning call | **Mitigated** — `ToolRouter` filters to top-k per request. Uses keyword/substring scoring, not embeddings — reasonable for the current registry size, but worth revisiting if tool count grows much further and keyword matching starts missing relevant tools. |
| `QgsProject` custom properties size limits for spatial memory at scale | Use a sidecar SQLite or GeoPackage attribute table alongside the `.qgz` for history/memory, not project properties alone | **Mitigated** — spatial memory log uses a sidecar `.sqlite` file. Note: chat history persistence (a separate, later feature) does still use `QgsProject` custom properties, not SQLite — worth revisiting if conversation history grows large enough to matter. |
| Concurrent multi-agent GeoPackage edits (Phase 4) | Define conflict-resolution model before implementation begins | **Not started** — Phase 4 vision item, not yet relevant since multi-agent/team-sync features don't exist yet |
| QGIS Plugin Repository submission requirements | Confirm GPL-compatible licensing decision; prepare user-facing docs/help panel before submission | **Partially done** — license decision confirmed (GPL v2; `LICENSE` + `LICENSE_AUDIT.md` in place). **Help panel still not built** — blocking item for submission readiness. |

---

## 8. Business Model & Editions

Full breakdown (target clients, verticals, and an honest shipped-vs-roadmap accounting per tier) lives
in `PRODUCT_TIERS.md`, kept separate from this engineering PRD since it needs to be revisited on a
business cadence, not an engineering one. Summary for roadmap-planning purposes:

- **Community** (free, GPL v2): the product as it exists today, in full — everything in §3/§4 above,
  no tier gating anywhere in the code.
- **Professional** (target ~$20/month, "Cloud Connect Gateway"): a hosted proxy/billing layer so a user
  doesn't manage their own LLM API key. Not started. This is a genuinely different piece of
  infrastructure than anything currently planned — every other Phase 1-3 item in §6 is a *desktop
  plugin* capability; this is the first item that requires operating a backend service at all (auth,
  per-user usage metering, a provider-facing proxy, billing). §5.1's "live, synced data connections"
  idea (adopted from the Atlas competitive review) is related in spirit but is about data access, not
  model access — the two shouldn't be conflated when scoping this.
- **Enterprise** (custom SLA): RBAC, SSO/SAML, private data enclaves/zero-retention, and Microsoft
  365 (SharePoint/Power BI) push integration. None started. Phase 4's "Team GeoPackage memory
  synchronization" and "Headless QGIS Server AI agent integration" (§6) are the closest existing
  roadmap items in spirit — both are multi-user/server-side, which is the same architectural shift
  Enterprise-tier features require — but neither was previously scoped against RBAC/SSO/M365
  requirements specifically. If Enterprise work is prioritized, scope it as an extension of those two
  items rather than a separate effort, since they'd share the same underlying multi-user
  server/concurrency-model work.

Two capabilities already shipped in Community turn out to be exactly what the Enterprise vertical
pitch (defense/intelligence, large institutional buyers) leads with: fail-closed read-only SQL
enforcement and fully offline (Ollama) execution — see `SECURITY.md`. There's currently no product
mechanism to reserve these for a paid tier, since they're core to the plugin's general security
posture, not add-ons. Worth a deliberate decision (not a default assumption) on whether that's the
intended packaging before Enterprise sales conversations lean on them as tier differentiators.

---

*End of document.*
