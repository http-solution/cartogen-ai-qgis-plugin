# rc8 audit, researched solutions and long-term recommendations (2026-09-30)

Dated snapshot; supersedes the status wording in `RC8_ISSUE_REVIEW_2026-09-30.md` where they differ.
Rules I held myself to: every claim says how it was established; "verified" means a test or the source code,
not memory; where I could not reach a source or a real QGIS, it says so. **This sandbox has no QGIS and its
network proxy blocks several hosts** (data.worldpop.org returned 403; docs.qgis.org, doc.qt.io and arxiv.org
were refused by the fetch tool), so some research rests on search-result text and is marked
*(search snippet)* rather than a page I read in full.

## 0. Three corrections to things I told you earlier

1. **F08's mechanism was wrong.** I wrote (code comments, tool descriptions, tracker, PR text) that
   `travel_time_matrix` "runs a shortest-path search per destination". I read the QGIS source for
   `native:shortestpathpointtolayer`: `QgsGraphAnalyzer::dijkstra` is called **once per origin**, before the loop over
   end points; the loop only walks the precomputed tree. The likely real cost is earlier: in
   `QgsVectorLayerDirector::makeGraph` every road segment is compared with every tied destination (a nested loop, no
   spatial index for the tie points), so cost grows with *segments × destinations*. That is consistent with the
   5 min 50 s graph build for 3,369 points against ~4 s for one point, but **it was not profiled**. I have corrected
   the wording in `logistics_tools.py`, `TOOLS_REFERENCE.md` and the tracker (this commit). The fix itself still
   stands on evidence: the same question answered from one service area took 5.8 s in the operator's log.
2. **F22: "Qt gives no reliable metered-connection signal" was wrong.** `QNetworkInformation::isMetered()` exists since
   Qt 6.3 and the Windows backend is the `networklistmanager` plugin *(search snippet of the Qt docs)*. QGIS 4 is
   built on Qt 6. It returns false when the platform backend cannot tell, so it can only add a question, never remove one.
3. **F12: the default dashboard basemap may not load.** The code comment says the `positron` default is a "free,
   no-API-key" service. Two sources say otherwise: Carto now requires an API key for Positron and Dark Matter
   ([mapview #520](https://github.com/r-spatial/mapview/issues/520), opened 2026-08-26), and Carto blocks requests that
   carry no Referer ([folium #2285](https://github.com/python-visualization/folium/issues/2285), open, no maintainer
   answer). An exported dashboard opened from disk (`file://`) sends no Referer, which is exactly our case. folium 0.20
   warns "CartoDB tiles now require an API key" on every build. **Not tested here (no tile access); test on your machine.**

## 1. Audit of items reported solved or fixed offline

Method: (a) read each fix against the failure it targets; (b) **mutation check** — I rebuilt the rc8 commit with the
pre-fix `src/` from `844a050` and ran its tests: 16 failures and 31 errors, i.e. the new tests do fail without the fixes
(F01 snapshot rename, F02 pending task, F03 guard and note, F04 `crs` argument, F05 guards, F10 nudge, F13 BOM/XY,
F23 memory guard, F12 notice helpers); (c) for items with a live CI test, confirmed it runs in `_ci_run_live_tests.py`.

| Item | Verdict | What the audit found |
|---|---|---|
| F01 | Fix correct by reading; **no live test** | `live.write(path)` re-points the project; `setFileName` + `setDirty` in a `finally` undo it, and unsaved projects (empty name) are covered by a test. **Unverified risk:** `QgsProject.write` also handles the auxiliary-storage database (manual label positions). I could not establish from memory whether a write to another path leaves the live project's auxiliary storage attached to the original; test it: project with a manually moved label, run an isolated script, confirm the label is still there and the `.qgd` was not replaced. |
| F02 | Fix correct, mutation-checked; **no live widget test** of the Confirm/Cancel card | Needs one live test that stages the egress preview and clicks Confirm and Cancel. |
| F03 | **Partial by design** | The guard (`response_guard.py`) fires only when a call was left pending or failed **and** the reply holds a pipe-table with ≥3 rows (`MIN_TABLE_ROWS_TO_FLAG`). It does not catch invented data given as bullets or prose, nor a reply where the model never called any tool. It is a safety net, not a guarantee. |
| F04 | **Solved, verified in real QGIS (CI)** | Live test compares with `QgsCoordinateTransform`. |
| F05 | Fix mutation-checked; cause never reproduced | Guards (sparse `speed_field` ignored, zero-length result never replaces a good layer) are right regardless of cause. **No live test** with real QGIS layers. |
| F07 | **Solved for new layers, verified (2 CI tests)** | Unfixed: old projects' bad nodes; no healing pass. |
| F11 | Fix reads correctly; **no live test** | Minor: `_discard_highlight` calls `highlight.deleteLater()`; a `QgsHighlight` is a `QGraphicsItem`, not a `QObject`, so this line is very likely a no-op swallowed by the `except`. Harmless (removal from the scene is what matters; Python then frees it) but it is dead code and hides a real leak if the scene call ever failed. Unverified in a live session. |
| F13 | BOM/XY/name fix mutation-checked | Not opened in Excel. A BOM is the documented fix for garbled Arabic on double-click; Excel's Data > From Text/CSV with UTF-8 is the fallback ([Microsoft Q&A](https://learn.microsoft.com/en-us/answers/questions/5234248/arabic-characters-are-displayed-as-in-excel)). |
| F14 | **Prompt rule only** | Not enforceable; see §3. |
| F16 | Offline vocabulary tests + a live widget test exist | Good. The 10-minute expiry is a judgement, not derived from anything. |
| F20, F23 | Offline-tested guards | F23 also depends on your "persist project memory" setting (still unconfirmed by you). |
| F24 | Empty-state text added | The original cause was never found; the empty-state makes it visible, it does not fix it. |
| F25 | **Solved, verified** | Real `.qgz` write/reopen test in CI. |
| F12 | Clustering/slider verified in headless Chromium, not CI | See corrections above (basemap, CDN version). |

Audit conclusion: the fixes are genuine and their tests bite, **but five of them (F01, F02, F05, F11, F16's
expiry) have no real-QGIS test, and two assumptions in the code comments were wrong (F08 mechanism, basemap
licence).** Those are the ones to close before a stable tag.

## 2. Partial items: researched solutions

### F08 — true many-destination matrices (the tool that remains slow)
*Established:* one Dijkstra per origin (QGIS source); tie-in is brute force (QGIS source). *Not established:* the
37-minute split, which needs a profile (run the original request once with Python `cProfile`, or time
`makeGraph` alone with 1 vs 3,369 tie points).
**Solution:** build the graph with **one** tie point (the origin) via `QgsVectorLayerDirector.makeGraph`, run
`QgsGraphAnalyzer.dijkstra` once to get the cost of every vertex, and read each destination's cost from its nearest
graph vertex, found with a `QgsSpatialIndex` over the vertices (plus the straight-line leg, reported separately, as
`classify_facilities_by_access` already does). That is O(graph) + O(destinations · log vertices) instead of
segments × destinations. It answers the same "cost from A to each facility" question exactly for one origin and
scales to tens of thousands of facilities. Prove it with a CI test that compares it with `native:shortestpathpointtolayer`
on a small network (the existing live equivalence test is the template). I have **not** implemented it: it needs QGIS
to develop against, and a wrong graph API use would be worse than the current guard.

### F09 — exposure geometry (what the literature actually does)
The 2026 global hospital-access study (arXiv 2609.12696) converts reached vertices to a polygon with a **GEOS
concave hull at ratio 0.85** and weights by GHS-POP *(search snippet)*; a hull-diagnostic in the same material
reports the share of hull population beyond 1.5 km of a reached vertex: 1.9 % (high-income) vs 6.5 % (low-income)
*(search snippet, not read in full)*. So: no published source gives one "correct" buffer width. The 500 m I chose is
not from data, and neither is any other single number I could offer.
**Solution (no guessing):** stop presenting one figure. Report **three nested figures** — reached-road buffer (tight),
concave hull ratio 0.85 (the published method), convex hull (upper bound) — each labelled, and make the buffer width
an explicit parameter the answer states. The spread between the three is itself the honest uncertainty, and in a sparse
network it is large. Additionally check which WorldPop product `fetch_worldpop_population` downloads: it lists
`hub.worldpop.org/rest/data/pop/wpgp` (the unconstrained global 100 m product, which spreads people over all cells).
WorldPop also publishes *constrained* products restricted to settled cells (search snippet); summing the
constrained product makes every geometry less inflated. **Verify the constrained dataset's REST alias before changing.**

### F10 — tokens and cost
Secondary sources (a GitHub measurement project, not peer reviewed) report that pruning old context mid-loop can
*raise* cost because it breaks the prompt-cache prefix, and that newest-first retention is cheaper than oldest-first.
**Solution:** do not prune inside a turn; instead (1) hard-cap tool iterations per turn, (2) show tokens per turn,
(3) keep the existing end-of-turn digest. Measure first: the export already has per-call usage.

### F12 leftovers
- **Basemap:** replace the assumption with a runtime check. At export time, probe each candidate tile URL with no
  Referer (as `file://` pages behave) and pick the first that answers HTTP 200; fall back to a "no basemap" page that
  says why. Offer a Settings field for a Carto key (append `?key=`, per Carto's documented form). This is robust to
  the next provider policy change, which a hard-coded default is not.
- **markercluster version:** cdnjs currently lists 1.5.3 with `leaflet.markercluster.js`, `MarkerCluster.css` and
  `MarkerCluster.Default.css`; it requires Leaflet ≥1.0 ([cdnjs](https://cdnjs.com/libraries/leaflet.markercluster)).
  The generated pages ask for 1.1.0, which I never tested. Pin **1.5.3**, the version I tested in Chromium.
- **Slider last date:** clamp the final step to the last date (code change, unit-testable; not yet done).
  Should be fixed together with the above.

### F17 — missing live tests (concrete assertions)
F01: `fileName()`/`isDirty()` unchanged after `run_isolated_script`, and a moved label survives. F02: stage the egress
preview, click Confirm then Cancel. F05: network with a 99 %-zero speed field leaves the old layers intact.
F11: no `QgsHighlight` in `canvas.scene()` after the timer fires (needs a canvas; the CI image has one via the widget tests).
F16: the widget-level stale-yes test exists; add the 10-minute expiry. Each is a small file in the existing live runner.

### F19 — windowed WorldPop reads
GDAL's `/vsicurl/` uses HTTP range requests, and a tiled/COG layout makes windowed reads cheap ([cogeo.org](https://cogeo.org/));
I found **no source stating WorldPop's country files are COGs**, and could not open the file (403 from this sandbox).
Reasoning that does not depend on the answer: even if the file is **strip**-organised, a window costs the full-width
rows it spans, not the whole file. Yemen: 12.11–19.00 °N is 6.89°, about 8,270 rows at 3 arc-seconds; the 71 km
catchment plus 2 km margins spans ≈ 810 rows ≈ **10 % of the raster** versus 100 % now. Worst case is still a ~10×
saving, provided the server honours range requests. **Measure on your machine:**
`gdalinfo /vsicurl/https://data.worldpop.org/<path>.tif` and read `Block=` (tile size → efficient; `Nx1` → strips) and
`Overviews`; then time one clip. Keep the existing refusal of whole-country downloads either way.

### F22 leftovers
Implement the **metered** check (`QNetworkInformation`, see §0), a shared "known size over threshold → ask" helper for
every fetch tool, and a Settings field for the threshold. Because `isMetered()` can be false when unknown, treat it as
"ask more", never "ask less".

### F07 leftover — heal old projects
On project load, remove layer-tree nodes whose `layer()` is `None` and keep only the first node of a duplicated layer.
This is ordinary layer-tree API use (`findLayers`, `removeChildNode`); prove it with a live test that builds the rc7
corruption (two nodes for one layer, one orphan) and asserts `len(findLayers()) == len(mapLayers())`. Note the earlier
clone-and-move approach broke live tests for a reason I never found, so the healing pass must only *remove* nodes.

## 3. Decisions: long-term recommendations

### F06 — analysis outputs lost on save
*Facts:* a QGIS memory layer is lost when the project closes; "Make permanent" to GeoPackage is the standard route
([QGIS docs](https://docs.qgis.org/3.44/en/docs/user_manual/managing_data_source/create_layers.html)); permanent conversion
can lose layer metadata ([QGIS #39226](https://github.com/qgis/QGIS/issues/39226)).
**Recommendation — a project "results store":** one GeoPackage per project, `data/20_processed/cartogen_results.gpkg`
(OGC standard, single file, many layers), each analysis output written as a named table and the project layer re-pointed
to it; provenance (tool, arguments hash, time, source layers) stored in the layer's own `QgsLayerMetadata` so it is
explicit rather than lost as in #39226. Unsaved project → write to the QGIS profile scratch folder and ask the user to
save the project, which then moves the store. Writing uses `QgsVectorFileWriter` with overwrite-layer semantics, which I
believe is correct but **cannot confirm the exact API from here — the live test is the confirmation.**
*Risks to test, not assume:* (1) overwriting a table whose layer is currently loaded can lock the file on Windows, so
write a new table, re-point the layer, then drop the old one; (2) GeoPackage WAL side-files (`-wal`, `-shm`) appear
next to the store; (3) disk growth — cap and offer clean-up. Why not warn-only: it leaves 44 minutes of work at the
mercy of a forgotten Save; why not "make permanent" on demand: it relies on the user knowing.

### F09 — see §2: three nested figures, explicit buffer width, constrained population product. Do not pick one
number on the user's behalf; the decision for you is only the default *headline*. My recommendation: headline = concave
hull 0.85 (published method), with the buffer and convex figures printed beside it.

### F21 — schema visible to a cloud model
OWASP LLM02 (sensitive information disclosure) calls for least privilege on what the model can reach and masking
sensitive content before it enters the context ([OWASP](https://genai.owasp.org/llmrisk/llm02-insecure-output-handling/)).
**Recommendation — one "model view" choke point:** every tool that shows the model layer information goes through a
single function that applies the layer's sensitivity tier: PUBLIC full; INTERNAL field names and counts; SENSITIVE
an opaque alias (`layer_3`), counts only, no field names, mapped back to real names in the UI. Local models
(Ollama) skip the masking, since nothing leaves the machine. Today only row reads are gated; a single choke point
closes `get_layers` and every future tool at once instead of patching tool by tool. Document the tiers in
SECURITY.md. It changes what the model can say about a sensitive layer, which is the point.

### F25 — transcript storage (keeps your decision B, improves where it lives)
Your decision stands (full transcript, default on, toggle). The remaining weakness is **where**: the `.qgz` is the
file people email, and GDPR Art. 25(2) extends data protection by default to the *accessibility* and *period* of
storage ([EDPB guidelines 4/2019](https://www.edpb.europa.eu/sites/default/files/files/file1/edpb_guidelines_201904_dataprotection_by_design_and_by_default_v2.0_en.pdf)).
**Recommendation:** store the transcript in the user's QGIS profile (a SQLite file keyed by a random project id that
is the only thing written into the project), not in the `.qgz`. Result: sharing a project never shares the
conversation; "delete" is one file; the project is not dirtied on each message; the same data still exports. Add a
retention setting (default: keep for the life of the project, i.e. until the project's id is gone from recent
projects for N days) for storage limitation (Art. 5(1)(e)). Migration: read the existing `.qgz` entry once and move it.
The project-memory sidecar next to the `.qgz` is *not* a good model, because copying the project folder copies it too.

### F18 — plan-validation flag
Show the gate's state in Settings with a reset-to-default, log it once at startup, and create the plan automatically
(orchestrator-side) when the gate is on. A hidden persisted flag caused wasted calls and confusing results in rc7.
Your action for the next smoke round: set `cartogen_ai/plan_validation_gate_enabled` to OFF.

### F03/F14 — the enforceable version
Because a prompt rule cannot be enforced (see §1), render data tables and confirmation prompts **only from
structured tool results and gate state in the UI**, and strip model-authored look-alikes. That removes the failure
class instead of detecting instances of it (defence in depth is the published pattern — see
[guardrails](https://dev.to/aws/ai-agent-guardrails-rules-that-llms-cannot-bypass-596d); the source is a blog, so treat as practice, not standard).

## 4. Proposed order

1. Your side: set plan-validation OFF; run the smoke round; open the CSV in Excel; open a dashboard from disk with
   the default basemap; run `gdalinfo /vsicurl/…` for WorldPop and send me the `Block=` line.
2. Small, safe code: pin markercluster 1.5.3; slider last-date clamp; drop dead `deleteLater`; layer-tree healing pass; metered check.
3. Live tests in §2/F17 (they are what let me change F01/F02/F05/F11 with confidence).
4. Profile the F08 request, then implement the one-tie-point matrix.
5. After your decisions: results store (F06), model-view choke point (F21), transcript in profile store (F25).

## Sources
[cogeo.org](https://cogeo.org/) · [cdnjs markercluster](https://cdnjs.com/libraries/leaflet.markercluster) ·
[folium #2285](https://github.com/python-visualization/folium/issues/2285) · [mapview #520](https://github.com/r-spatial/mapview/issues/520) ·
[QGIS create-layers docs](https://docs.qgis.org/3.44/en/docs/user_manual/managing_data_source/create_layers.html) ·
[QGIS #39226](https://github.com/qgis/QGIS/issues/39226) · [OWASP LLM02](https://genai.owasp.org/llmrisk/llm02-insecure-output-handling/) ·
[EDPB Art. 25](https://www.edpb.europa.eu/sites/default/files/files/file1/edpb_guidelines_201904_dataprotection_by_design_and_by_default_v2.0_en.pdf) ·
[AccessMod 3.0](https://pmc.ncbi.nlm.nih.gov/articles/PMC2651127/) · [arXiv 2609.12696](https://arxiv.org/abs/2609.12696) (search snippet) ·
QGIS source read through GitHub web pages: `qgsalgorithmshortestpathpointtolayer.cpp`, `qgsvectorlayerdirector.cpp` ·
Qt `QNetworkInformation` (search snippet).
