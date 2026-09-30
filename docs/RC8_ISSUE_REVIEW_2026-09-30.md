# rc8 issue review: F01-F25 + umbrella #72 (2026-09-30)

Dated snapshot (not edited later). Basis: `main` at `c0de3f5`, the rc8 zip built from it, CI green on that head
(offline 2,537 tests; live-QGIS job 97 tests on QGIS 4.2.2). "Verified" below means a CI test or a measurement,
not "I believe it works". **Nothing has yet been re-run by a human in a real QGIS session with the rc8 zip**; that
smoke round is the gate for every "unverified" row.

Status vocabulary: **SOLVED (verified)** = fix + test that would fail without it, in CI against real QGIS or
real data. **FIXED, unverified live** = fix + offline tests only; the real-QGIS behaviour is untested.
**PARTIAL** = part built, part open. **OPEN / DECISION** = nothing changed, or the owner must choose.

## 1. Scoreboard

| # | Finding | Status | Who acts |
|---|---|---|---|
| F01 | Isolated script renames live project | FIXED, unverified live | you: smoke check |
| F02 | Gate preview never registered | FIXED, unverified live | you: smoke check |
| F03 | Fabricated tool output | MITIGATED, unverified live | you: smoke check |
| F04 | Origin 1.3 km off | SOLVED (verified) | - |
| F05 | Re-run destroyed good result | FIXED (cause a hypothesis), unverified live | you: rerun Yemen request |
| F06 | Memory layers claimed "saved" | PARTIAL (wording only) | **decision** |
| F07 | Layer-tree duplicates | SOLVED for new layers (verified); old projects and basemap order OPEN | small follow-up |
| F08 | 43-minute routing | PARTIAL (new tool verified vs routing; model use unverified) | you + follow-up |
| F09 | Convex-hull exposure | PARTIAL (geometry verified; 500 m default not data-derived) | **decision** |
| F10 | Router / tokens / nudge | PARTIAL (nudge + threshold fixed; token cost not) | follow-up |
| F11 | Highlight overlays | FIXED, unverified live | you: smoke check |
| F12 | Dashboard | SOLVED in a real browser (not CI); CDN version + basemap key OPEN | small follow-up |
| F13 | CSV | FIXED, unverified in Excel | you: open in Excel |
| F14 | Double confirmations | MITIGATED (prompt rule only) | you: smoke check |
| F15 | UX polish | FIXED (partly), unverified live | you |
| F16 | Stale "yes" | FIXED, offline-tested | - |
| F17 | Live-test gap | PARTIAL | follow-up |
| F18 | Plan gate ON in profile | OPEN (operator action) | **you: set OFF** |
| F19 | Whole-country WorldPop | FIXED on synthetic data; real server UNTESTED | you: smoke check |
| F20 | CRS assumption | FIXED (range check), offline | - |
| F21 | Schema exposure | OPEN / DECISION | **decision** |
| F22 | Silent download | PARTIAL (50 MB default decided) | small follow-up |
| F23 | Coordinates in memory | FIXED, offline | - |
| F24 | Memory dialog empty | FIXED (empty-state), cause unproven | you: smoke check |
| F25 | Chat export incomplete | SOLVED (verified in a real .qgz round-trip); UI restore OPEN | small follow-up |
| #72 | Umbrella | OPEN until the smoke round | - |


## 2. Per-issue review

### F01 project renamed by isolation
- **Did:** snapshot write now saves and restores file name and dirty flag in a `finally`; 5 offline tests (4 fail without the restore).
- **Honest gap:** the defect only exists inside a real `QgsProject`; no live test covers it (F17 listed it, not built).
- **Expected:** after any `execute_pyqgis_script`, title bar and `QgsProject.instance().fileName()` unchanged; exports land in the project folder.
- **Recommend:** add a live test (run isolated script, assert `fileName()`/`isDirty()` unchanged); do it before the stable tag. It is data-loss class and cheap.

### F02 gate preview never registered
- **Did:** shared helper registers the egress preview task; it survives a model `create_plan`; `confirmed` no longer injected into tools that do not accept it.
- **Gap:** offline only; the ✅/❌ card on a SENSITIVE read has not been seen live.
- **Expected:** with a SENSITIVE layer and Block, the read is stopped, a real Confirm/Cancel card appears, Confirm runs it, Cancel does not.
- **Recommend:** smoke-test both Confirm and Cancel, with plan-validation OFF and then ON (the two gates interact, see F18).

### F03 fabricated output
- **Did:** system note on blocked/failed calls, post-turn "No data was retrieved" guard, prompt rules.
- **Honest view:** this is a mitigation, not a cure. Guard is a heuristic (table-shaped reply with no successful data tool). Research on agent hallucination points the same way: the reliable controls are deterministic ones around the model (validate tool results, block or correct before display), not prompt wording alone ([AI agent guardrails](https://dev.to/aws/ai-agent-guardrails-rules-that-llms-cannot-bypass-596d), [agent hallucination mitigation in production](https://dev.to/omnithium/agent-hallucination-detection-and-mitigation-in-production-5ap0)).
- **Expected:** repeating the R8 prompt with the gate on never shows rows unless a tool returned them.
- **Recommend:** keep; later make the guard stronger by rendering data tables only from tool results (the UI, not the model, draws the table). That removes the failure class instead of detecting it.

### F04 origin 1.3 km off - SOLVED (verified)
- `add_point_layer(crs=...)` transforms in code; a live CI test compares against `QgsCoordinateTransform`; values outside ±180/±90 without a CRS are refused.
- **Residual:** the model can still call `add_point_layer` with lon/lat it computed itself; the prompt rule and range guard reduce, not remove, that. Acceptable.

### F05 re-run destroyed a good result
- **Did:** a `speed_field` that is mostly empty is ignored, a 1 m "1 hour" cost is flagged, a zero-length result never replaces a good layer.
- **Honest view:** the cause was a strongly-indicated hypothesis and was never reproduced. The protection (validate before replace) is right whatever the cause, but the exact rerun on the Yemen extract has not been done.
- **Recommend:** rerun the request from the smoke test with `speed_field='maxspeed'` and confirm the old layers survive; add a live test with a network whose speed field is 99% zero.

### F06 outputs are memory layers
- **Did:** only wording (results say layers are temporary).
- **Why still open:** a QGIS memory layer keeps its definition but not its features; the docs state temporary layers are lost when the project closes ([QGIS docs: creating layers](https://docs.qgis.org/3.44/en/docs/user_manual/managing_data_source/create_layers.html)), and "Make permanent" to GeoPackage is the standard route. The only thing that loses 44 minutes of compute is silence about it.
- **Options:** (a) keep memory layers, warn on save (cheap, weak); (b) when the project has a file, write outputs to `data/20_processed/*.gpkg` and re-point the layer (what professional workflows do; changes where files live); (c) a "Keep results" button that does (b) on demand.
- **Recommendation: (b) for analysis outputs that took more than a few seconds, (a) otherwise.** GeoPackage is the right container (one file, many layers). Needs your decision because it writes files you did not ask for. Note the known issue that making memory layers permanent can lose layer metadata ([QGIS #39226](https://github.com/qgis/QGIS/issues/39226)); write metadata explicitly.

### F07 layer tree - SOLVED for new layers (verified)
- **Cause found:** `insert_layer_semantically` added a second node for layers already in the tree. **Fix:** leave an existing node alone. Two real-QGIS CI tests.
- **Note on method:** the clone + insert + remove move pattern is the documented one ([PyQGIS cookbook](https://docs.qgis.org/testing/en/docs/pyqgis_developer_cookbook/legend.html)) yet it broke two live tests here; the cause was never established, which is why I avoided moving nodes.
- **Open:** projects saved under rc7 keep duplicate/orphan nodes (no healing pass); the basemap-burying order was not reproduced; side effect: semantic placement now applies only to layers without a node.
- **Recommend:** add a small repair-on-load pass (remove nodes whose `layer()` is None; drop duplicate nodes) with a live test.

### F08 43-minute routing
- **Did:** `classify_facilities_by_access` answers "within/beyond N" from one service area; `travel_time_matrix` refuses >200 destinations unless `allow_large=true`. A live test compares against routed cost.
- **Honest view:** the approach is sound; one-to-many cost from a single Dijkstra tree is how network-analysis tools answer this, versus a path per destination ([QNEAT3](https://plugins.qgis.org/plugins/QNEAT3/) runs Dijkstra in C++ but still pays per pair for OD matrices). Unverified: whether the model picks the new tool; the ~6 min graph build; no time estimate before long jobs.
- **Expected:** Yemen request finishes in well under a minute with the same 110 facilities.
- **Recommend:** run it in the smoke round; if the model still routes per facility, route the question in code (detect "beyond/within N" and call the classifier). Add a pre-run estimate for any tool known to be slow.

### F09 convex-hull exposure
- **Did:** default exposure is the reached roads buffered 500 m in UTM metres; hull kept and labelled upper bound.
- **Honest view:** direction is right and supported by the literature: convex hulls overstate access, a buffer of the reached network is more faithful ([isochrone hull comparison](https://www.researchgate.net/figure/ariable-Distance-Buffer-versus-Concave-Hull-Approach_fig2_321707440)). But 500 m is my choice, not derived from data, and on dense networks the buffer can exceed the hull (found in CI).
- **Decision needed:** the default distance. **Recommend 250 m default** for road-based access (population within walking distance of a reached road), configurable, and always report the hull figure alongside as the upper bound so the reader sees the range. Keep the figure labelled as an estimate.

### F10 router, tokens
- **Did:** low-confidence matches send the raw message; nudges only for explicitly requested outputs.
- **Open:** ~1.9M tokens / 102 calls per session; per-turn token display and tool-loop caps were not built.
- **Recommend:** add a per-turn token line and a hard cap on tool iterations; prune old tool results from context. It is cost and trust, not correctness.

### F11 highlight overlays
- **Did:** highlight removed from the scene and deleted on expiry. No live test (F17 listed it).
- **Expected:** no `QgsHighlight` left after 2.5 s. **Recommend:** one live test.

### F12 dashboards
- **Did:** timestamped file under `data/20_processed/dashboards`, sampling notice inside the HTML, fit-to-data, marker clustering for ≥100 points (both dashboards), temporal slider fixed for folium 0.20.
- **Verified** in headless Chromium, not in CI. **Open:** generated pages ask for markercluster 1.1.0 from a CDN; I tested 1.5.3. Slider cannot reach the last date when the span is not a multiple of the step. CartoDB basemap "requires an API key" warning uninvestigated.
- **Recommend:** pin the markercluster version to one I test (1.5.3) and fix the last-date step (clamp the final step to the last date). The basemap warning matters: a basemap that silently stops loading breaks the page offline-first users rely on; test with real tiles.

### F13 CSV
- **Did:** UTF-8 BOM, X/Y columns for points, clean names. The BOM route is the standard fix for Arabic showing garbled when a CSV is double-clicked in Excel ([Microsoft Q&A](https://learn.microsoft.com/en-us/answers/questions/5234248/arabic-characters-are-displayed-as-in-excel)); the robust alternative is Data > From Text/CSV with UTF-8.
- **Unverified:** nobody has opened the rc8 file in Excel. **Recommend:** open it once; also note the tradeoff that a BOM can add a stray character in some non-Excel tools, so keep it only for the Excel-facing export.

### F14 two confirmations
- Prompt rule only. **Recommend:** suppress model-authored confirmation text when a real card is pending (deterministic), as with F03; a prompt rule alone is not enforceable.

### F15 UX polish
- Partly done (Sensitivity dialog message, etc.). Remaining items (LaTeX, stray ")", CRITICAL log noise, `print()` console noise, "a analysis") may or may not all be fixed; I have not re-audited the list against rc8. **Recommend:** re-check item by item in the smoke round; lowest priority.

### F16 stale "yes"
- Destructive confirmations need an explicit word; typed confirmations expire in 10 minutes; offline tests. Residual: 10 minutes is a guess. Fine.

### F17 live-test gap
- Built: point CRS, layer tree, facility access, WorldPop clip, transcript. **Missing:** F01 project identity, F11 highlights, F05 zero-length guard, F02/F16 widget flows. **Recommend:** close these; they are the defects that reached a human before CI.

### F18 plan gate ON
- Operator setting persisted as `'true'`. **Action: set it OFF** (`cartogen_ai/plan_validation_gate_enabled`) before the next round. Product follow-up: show it in Settings with a reset, since a hidden persisted flag caused wasted calls and confusing results.

### F19 whole-country WorldPop
- **Did:** `extent_layer`/`bbox` reads only that window through GDAL `/vsicurl/`; whole-country refused unless opted in; clamp/overlap check (found because `gdal.Translate` silently writes an empty raster outside the window).
- **Honest gap:** verified on a synthetic GeoTIFF only. Windowed reads are efficient only when the file is tiled/COG-like ([COG explained](https://cogeo.org/), [GDAL /vsicurl/ range requests](https://frodriguezsanchez.net/post/accessing-data-from-large-online-rasters-with-cloud-optimized-geotiff-gdal-and-terra-r-package/)); I do not know that WorldPop country files are. If they are strip-organised the window read may fetch most of the file anyway.
- **Recommend:** measure one real read now (Yemen, small bbox: bytes transferred and seconds) before calling F19 closed. If it is slow, fall back to download-once-and-cache the country file, then clip locally.

### F20 CRS assumption
- Range check (values >180/90 cannot be degrees) plus the origin handling. Residual: a projected pair that happens to be small is still ambiguous; asking is the only complete answer. Acceptable.

### F21 schema exposure - DECISION
- Field names and counts of a SENSITIVE layer reach the cloud model because `get_layers` is ungated. OWASP's framing is data-minimisation of what the model can see and exfiltrate ([OWASP LLM06 Excessive Agency](https://owasp.org/www-project-top-10-for-large-language-model-applications/2_0_vulns/LLM06_ExcessiveAgency.html)).
- **Options:** accept and document; or mask schema for SENSITIVE layers in STRICT mode only.
- **Recommendation: document now (SECURITY.md + Settings help), gate in STRICT mode only.** Field names are rarely the sensitive part; layer names can be, so in STRICT mode also replace the name with a neutral alias toward the cloud model.

### F22 silent downloads
- Default now 50 MB, cached extracts do not ask, whole-country WorldPop refused. **Open:** other fetch tools (geoBoundaries, HDX, building footprints) do not ask; no metered-connection signal in Qt; no Settings control. **Recommend:** one shared "size known and over threshold -> ask" helper for every fetch tool, and a Settings field; skip the metered check (unreliable).

### F23 coordinates in memory
- Memory notes containing coordinates are refused; the model may not write project memory unasked (prompt + check). Confirm the "persist project memory" setting is OFF (still an open question to you).

### F24 Memory dialog empty
- Empty-state text and refresh-on-show were added; the original cause was never established. **Recommend:** re-test both cases (right after a message, right after `load_project`).

### F25 chat export - SOLVED (verified)
- Owner decision B shipped: full transcript per project, default ON, Settings toggle, Memory-dialog delete, bounded at 2,000 messages/2 MB. Verified by a real .qgz write/reopen test.
- **My caution, for the record:** default-ON storage of conversations in a shareable project file is the opposite of GDPR data protection by default (Art. 25(2) applies to the period and accessibility of storage, [EDPB guidelines](https://www.edpb.europa.eu/sites/default/files/files/file1/edpb_guidelines_201904_dataprotection_by_design_and_by_default_v2.0_en.pdf)). You accepted the risk and SECURITY.md §7 says so. Cheap mitigations worth adding: a one-time notice on first save in a project, and stripping the transcript when exporting or sharing the project. **Open:** the UI restores only the 10-message window.

## 3. Decisions for you

1. **F06:** persist analysis outputs to GeoPackage (recommended) or warn only.
2. **F09:** reach buffer default 250 m (recommended) vs 500 m; always show the hull as upper bound.
3. **F21:** document + STRICT-mode masking (recommended).
4. **F25:** add first-use notice and strip-on-share (recommended)?

## 4. What I would do next, in order

1. You: set plan-validation OFF (F18), install the rc8 zip, run the smoke round with attention to F01, F02, F03, F08, F13 (Excel), F19 (real WorldPop), F24.
2. Me: live tests for F01, F05, F11, F16 (closes F17); healing pass for old layer trees (F07).
3. Me: one real WorldPop windowed-read measurement (F19), pin markercluster and fix the slider last date (F12).
4. After your decisions: F06 GeoPackage persistence; shared download-size helper (F22).
5. Do not tag stable until F01-F06 are live-verified and the clean-profile/upgrade gate has run.

## Sources
- QGIS temporary layers: [QGIS docs](https://docs.qgis.org/3.44/en/docs/user_manual/managing_data_source/create_layers.html), [QGIS #39226](https://github.com/qgis/QGIS/issues/39226)
- Layer tree moves: [PyQGIS cookbook](https://docs.qgis.org/testing/en/docs/pyqgis_developer_cookbook/legend.html)
- Isochrone geometry: [hull vs buffer](https://www.researchgate.net/figure/ariable-Distance-Buffer-versus-Concave-Hull-Approach_fig2_321707440)
- Network analysis: [QNEAT3](https://plugins.qgis.org/plugins/QNEAT3/), [Anita Graser's toolbox comparison](https://anitagraser.com/2019/07/07/five-qgis-network-analysis-toolboxes-for-routing-and-isochrones/)
- Cloud rasters: [cogeo.org](https://cogeo.org/), [windowed reads with GDAL](https://frodriguezsanchez.net/post/accessing-data-from-large-online-rasters-with-cloud-optimized-geotiff-gdal-and-terra-r-package/)
- Excel CSV encoding: [Microsoft Q&A](https://learn.microsoft.com/en-us/answers/questions/5234248/arabic-characters-are-displayed-as-in-excel)
- Agent safety: [OWASP LLM06](https://owasp.org/www-project-top-10-for-large-language-model-applications/2_0_vulns/LLM06_ExcessiveAgency.html), [guardrails](https://dev.to/aws/ai-agent-guardrails-rules-that-llms-cannot-bypass-596d)
- Privacy by default: [EDPB Art. 25 guidelines](https://www.edpb.europa.eu/sites/default/files/files/file1/edpb_guidelines_201904_dataprotection_by_design_and_by_default_v2.0_en.pdf)
- Searches did not find anything specific to WorldPop file tiling; that is why F19 needs a measurement, not an assumption.
