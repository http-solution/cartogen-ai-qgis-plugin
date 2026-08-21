# Cartogen AI — Status Review (2026-08-20)

Full-codebase review requested directly by the user, current as of **v1.2.21**. This is a snapshot,
not a permanent record — treat it the way this project treats every other execution-unverified-live
claim: correct as of the date above, re-verify before relying on specifics after significant drift.

**Post-review update (same day, later pass):** both items §7 flagged as "not unilaterally actioned"
were subsequently actioned in a follow-up pass: the 4 redundant duplicate tools (§3/§7.1) were
removed, and the raster styling tool gap (§7.2) was closed with `apply_raster_stretch`. Tool count
is now 131 (135 momentarily, after the raster tool was added and before the 4 duplicates were
removed). The bare tool-count figures below (§1, §3, and the architecture diagram in §2) have been
updated to 131 to avoid stating a now-stale number; the narrative describing what this review found
and recommended is left as originally written -- see `CHANGELOG.md` for what actually changed and
when.

## 1. Executive summary

| | |
|---|---|
| Version | 1.2.21 |
| Registered tools | 131, across 16 categories (see post-review update note above) |
| Test suite | 639 tests — 1 failure + 6 errors, all pre-known sandbox artifacts (scratch-file permissions, a DNS lookup that fails in this sandbox), not real code defects |
| Trees | Root (`qgis_ai_assistant`) and `Cartogen AI/cartogen_ai/` (second QGIS plugin listing) — confirmed in sync |
| Editions | Only Community (free, GPL v2) is shipped. Professional/Enterprise are documented roadmap only, nothing tier-gated in code |
| Live QGIS verification | None of this has been run inside a real QGIS session in this environment — every claim below is "correct per the code and test suite," not "confirmed working in QGIS." This is the project's single largest standing gap, stated plainly rather than glossed over |

The codebase is in good, actively-maintained shape: no dead TODO/FIXME debt, a consistent
spec-before-build discipline (every new capability gets a dated doc with an honest shipped/
not-shipped header), and a real habit of catching its own mistakes on re-verification rather than
assuming success. The three most recent rounds of work (v1.2.19–v1.2.21) were explicitly
self-audits — asked to find what an earlier pass missed — and each one found real, fixable issues,
including one round finding a regression introduced by the round before it. That pattern is a
sign of a codebase getting more reliable over time, not one accumulating hidden debt.

## 2. Architecture

```
agent/
  agent.py            — QgisAiAgent, ToolDispatcher, the main tool-calling loop (MAX_ITERATIONS=20)
  tool_router.py       — keyword/alias scoring, filters 131 tools down to top_k=40 candidates per query
  prompts.py           — BASE_SYSTEM_PROMPT + 38 numbered behavioral rules
  scheduler.py         — WorkflowScheduler, recurring in-session monitoring (QTimer-based)
  task_manager.py      — multi-step plan/task tracking with PREVIEW_READY/CONFIRMED gating
  memory.py            — project/global persistent notes
  chat_persistence.py  — conversation history saved into the .qgz project file
  lineage.py           — tags generated layers with tool/params/source/timestamp
  prompt_refiner.py    — opt-in pre-processing step, refines vague requests before the main loop
  deps.py              — detects (does not install) missing optional Python packages
  auth.py              — QgsAuthManager-backed API key storage
  providers/           — 5 provider clients: OpenRouter, Gemini, OpenAI, Claude, Ollama
  tools/               — 20 tool modules, 131 @register_tool-decorated functions
```

This structure hasn't changed shape since the last architecture review — no new top-level modules,
no refactor in progress. The tool-calling loop's three special-handling sets
(`NETWORK_ONLY_TOOLS`, `TWO_PHASE_TOOLS`, `TASK_MANAGEMENT_TOOLS`) are unchanged and still
correctly separate background-thread-safe network calls from main-thread-only QGIS API calls —
this split is the load-bearing mechanism that keeps the UI responsive during long-running fetches,
and it's still intact.

**Request flow, end to end:** user message → `prompt_refiner` (optional) → `ToolRouter` narrows
131 tools to ≤40 candidates → model picks a tool call → `ToolDispatcher` routes it to a background
thread (network-only) or the main Qt thread (QGIS-touching) via `BlockingQueuedConnection` →
result returns to the loop → repeats until the model stops calling tools or `MAX_ITERATIONS` (20)
is hit.

## 3. Tool registry (131 tools, 16 categories -- was 134 at review time; see post-review update note above)

Categories, tool-count by area, current as of this review:

| Category | Notes |
|---|---|
| Vector & Geoprocessing | Largest category — buffers, clips, joins, dissolves, field calculator |
| Raster | NDVI/NDWI/NDRE, change detection, interpolation, weighted overlay, hillshade/slope/aspect |
| Humanitarian Data (HDX/OSM/geoBoundaries) | Admin boundaries, building footprints, population rasters |
| Humanitarian Logistics | Hub siting, service areas, travel-time matrices, VRP-lite routing, route risk scoring |
| Data Analysis & Prediction | Severity/needs indices, presence-gap, damage exposure, incident trend forecasting |
| Styling & Labeling | Categorized/graduated/heatmap renderers, humanitarian-cluster color palettes |
| AI Imagery Feature Extraction | FastSAM-based class-agnostic segmentation (label fixed this review — see §5) |
| Satellite Imagery & Vision | STAC search, raster change detection, canvas visual inspection |
| Monitoring & Scheduling | Recurring workflow presets, in-session scheduling (label fixed this review) |
| Database & Workflows | PostGIS/SQL queries, workflow preset save/load |
| Export & Reporting | CSV/shapefile/GeoPackage export, charts, HTML dashboards |
| Print Layouts | `create_print_layout` composition, avoids hand-written PyQGIS layout code by design |
| Reporting & Document Analysis | PDF/Word table extraction, 3W/4W aggregation |
| Project Management | Layer/project-level operations |
| Task & Memory Management | Plan tracking, persistent notes |
| System, Search & Scripting | `execute_pyqgis_script` (sandboxed), web search |

**Known redundancy, flagged in the last round, still unresolved (needs a decision, not a fix I
should make unilaterally):** 4 of the 134 registered tools are literal one-line pass-through
duplicates with no functional difference from another tool in the registry:

- `generate_csv` → `return export_to_csv(...)`
- `export_attribute_table` → `return export_to_csv(...)`
- `generate_map_image` → `return print_map(...)`
- `filter_features` → `return run_query(...)`

Each duplicate is a full extra entry in `ToolRouter`'s candidate pool and the model's tool-call
menu for zero added capability — pure token/decision-noise. Removing them is a bigger, more
consequential change than the description/alias fixes made elsewhere (a saved workflow preset or
external script could reference one of these names), so it's still sitting as an open item rather
than something already actioned. See §7 for the recommendation.

**Router health:** `ToolRouter` uses keyword/description matching plus a curated `_TOOL_ALIASES`
list for tools whose real-world phrasing doesn't share vocabulary with their own name/description.
17 realistic paraphrased queries are now covered by regression tests
(`tests/test_tool_router.py`), all passing. A structural test
(`TestToolAliasesNoDuplicateKeys`) now guards against the exact class of silent bug that shipped
and was caught in the v1.2.20 round (a duplicate dict key silently discarding aliases with no
error). This is the single highest-value process fix from the last two rounds — it converts a
category of bug that previously required a full test-suite run to notice into one that fails fast
and specifically.

## 4. Prompt engineering (`agent/prompts.py`)

38 numbered behavioral rules, covering: anti-fabrication/projection-labeling (rule 12, referenced
by name throughout the rest of the file), styling conventions and cartographic self-checks (19,
21, 22), natural-language-to-tool-name mapping for non-obvious intents (25, 35), Do No Harm
geoprivacy judgment calls (26), destructive-action/scheduling confirmation gating (29, 31, 33),
and — as of this review's predecessor round — correct styling-tool selection for the four
`output_field`-writing severity/needs tools, split by data type (numeric → graduated, categorical
→ categorized; rule 38).

No gaps found in this review beyond what the last two rounds already closed. The main remaining
soft spot is structural, not content: prompt rules are English prose asserting facts about tool
behavior (e.g. "score_route_incident_risk's buffer output is already auto-styled") with no
automated check that the prose still matches the code if the tool changes later. This already
caused one real bug (rule 38 initially wrong for `calculate_presence_gap`) and was only caught by
manually cross-referencing tool descriptions against the rule text, not by any test. There's no
low-risk automated fix for this — prose-to-code consistency isn't mechanically checkable the way
the alias-duplicate-key bug was — so it's listed as a process risk in §7 rather than a bug.

## 5. This review's own findings and fixes

Established the baseline (git status, full test run, tool count) before reviewing, per this
project's own verification discipline. Found and fixed 3 real issues:

1. **`docs/TOOLS_REFERENCE.md` category-label gap.** `docs/generate_tools_reference.py`'s
   `_group_key()` maps each tool's source module to a human-readable category name, falling back
   to the raw module name if a module isn't in its label dict. Two modules —
   `imagery_extraction` and `monitoring_tools` — were never added to that dict, so their sections
   displayed as `## imagery_extraction` and `## monitoring_tools` instead of a real category name,
   for as long as those modules have existed. Fixed: `"AI Imagery Feature Extraction"` and
   `"Monitoring & Scheduling"`. Regenerated in both trees, confirmed via direct grep of the output.
2. **`docs/PRODUCT_TIERS.md` stale tool count.** Said "all 125 tools" against the real, current
   134 — missed in the pass that fixed the same stale count in README.md. Fixed.
3. **`SECURITY.md` gap: unpinned model-weights download.** `extract_features_from_imagery` calls
   `FastSAM("FastSAM-s.pt")`, which delegates entirely to the `ultralytics` package's own
   first-use download logic — no hash pinning, no checksum verification, no control over the
   download source from this plugin's own code. This was never mentioned anywhere in the security
   doc despite the doc's own careful, itemized disclosure of every other network-touching
   capability (SSRF guard scope, prompt-refiner external calls, chat-history persistence). Added
   as a new "Known limitations" bullet, explicitly scoped the same way the existing SSRF-guard
   entry is scoped (URLs this plugin's own code fetches directly, not a dependency's internal
   download mechanism) — an honest disclosure, not a claim that it's been fixed.

All three propagated to both trees and verified via grep. Full test suite reconfirmed passing
(639 tests, same pre-known artifacts) after each change.

## 6. Documentation inventory

14 files under `docs/`, each with an honest status header where relevant:

| Doc | Status |
|---|---|
| `USER_GUIDE.md` | Shipped, describes current UX |
| `TOOLS_REFERENCE.md` | Auto-generated, always current after a regenerate |
| `PRODUCT_TIERS.md` | Shipped (Community) vs. roadmap (Pro/Enterprise), now tool-count-accurate |
| `PROMPT_REFINEMENT_LAYER_SPEC.md` | Shipped |
| `SAM_IMAGERY_EXTRACTION_SPEC.md` | Shipped |
| `ROUTE_OPTIMIZATION_STRATEGY.md` | Strategy doc — flat-speed routing limitation still not applied, `route_optimization_prototype.py` still an unexecuted standalone script |
| `ROUTE_RISK_AND_NOGO_ZONES_SPEC.md` | §3.1/3.2 shipped (`analyze_incident_trend`, `score_route_incident_risk`); §3.3 no-go zones is prompt-guidance-only by design, not a new tool |
| `AUTO_REPORTING_RECIPE.md` / `CVA_MARKET_ACCESS_RECIPE.md` | Zero-new-code compositions of existing tools |
| `JIAF_MULTISECTOR_COMPOSITE_SPEC.md` | Spec-only, deliberately not built (real JIAF Mosaic Method needs a human validation workshop step a formula can't substitute for) |
| `SECURITY_AND_COMPETITIVE_REVIEW_2026-08.md` | MCP server exposure explicitly declined by the user; repo-rename item still open (external GitHub action, not verifiable from this sandbox) |
| `API_COST_OPTIMIZATION_REVIEW.md` | Origin of the `ToolRouter` alias mechanism and its regression-test discipline |

No new staleness found beyond the 3 items in §5. The historical/frozen planning docs
(`QGIS_AI_Agent_Feature_List.md`, `QGIS_AI_Agent_PRD.md`, `IMPLEMENTATION_TASK_LIST.md`) are
deliberately left untranslated and unedited per `build_cartogen_ai.py`'s own documented design —
correctly left alone in this review, not stale by omission.

## 7. Open items requiring a decision (not unilaterally actioned)

1. **Remove or keep the 4 redundant tool aliases?** (§3) Recommendation: remove
   `generate_csv`/`export_attribute_table`/`generate_map_image`/`filter_features` and keep
   `export_to_csv`/`print_map`/`run_query` as the canonical names, since the canonical names are
   the ones with real logic attached. Low risk if no saved workflow preset references the
   duplicate names — worth a quick grep of any real user project files before removing, which this
   sandbox has no access to.
2. **No dedicated raster styling tool exists anywhere in the plugin.** Every raster-producing tool
   (NDVI/NDWI/NDRE, change detection, interpolation, hillshade, density surfaces) lands on the
   canvas with QGIS's raw unstretched single-band default rendering — there's a rich vector
   styling toolkit (`apply_graduated_style`, `apply_categorized_style`, `apply_heatmap_style`,
   `apply_graduated_symbol_style`) but nothing raster-side. This is a real capability gap, not a
   bug — flagged in the v1.2.20 round, not yet built. Would need a new tool (e.g.
   `apply_raster_stretch`/`apply_raster_color_ramp` using `QgsSingleBandPseudoColorRenderer`) —
   scoped as a real, buildable feature if wanted.
3. **`docs/route_optimization_prototype.py` remains unexecuted.** The OSMnx/NetworkX/GeoPandas
   prototype script for constrained multi-vehicle-profile routing has never been run in this
   sandbox (no dependencies installed, no test data). It's explicitly a standalone research
   artifact, not integrated into the plugin's own tool registry — still true as of this review.
4. **`generate_html_dashboard` connectivity requirement** and **repo-rename/GitHub-collaborator
   items** from earlier reviews remain exactly where they were — no new information available
   from this sandbox.

## 8. Recommended next steps, prioritized

1. **Live-QGIS verification pass** (highest value, not something this sandbox can do). Every tool
   in this registry is "correct per the code" but a large fraction is explicitly marked
   execution-unverified-live throughout the docs (network-analysis tools, the newest v1.2.17-19
   tools, the styling changes from the last two rounds). A single real QGIS session running a
   representative query against each category would close more risk than any further code review
   from this environment can.
2. **Decide on the 4 redundant tool names** (§7.1) — quick to act on once decided.
3. **Decide whether a raster styling tool is worth building** (§7.2) — real gap, clear scope, not
   started.
4. If neither of those, the codebase doesn't have an urgent item outstanding — the last three
   rounds closed real, verified gaps each time, and this round found comparatively minor,
   documentation-only issues, which is itself a signal the higher-value fixes are running out in
   the areas already covered (rendering, routing, prompts, tests, docs). The next round of
   meaningful findings likely requires either live QGIS access or a new angle not yet reviewed
   (e.g. the provider-client layer in `agent/providers/`, or the UI layer in `ui/`, neither of
   which has had a dedicated deep pass in this conversation).
