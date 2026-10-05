# rc15 installed-profile smoke report: triage (2026-10-06)

A dated record, not a result of re-testing. Input: `docs/RC15_LIVE_SMOKE_REPORT_2026-10-06.md` (the report as received; screenshots and
artifacts stayed with the reporter). rc15 overall: **FAIL**, no 16/16. This file says, per defect, what the code shows and what changed.
"Fixed in code" means offline tests and, where it touches QGIS, a live test that runs in CI; **nothing here is hand-verified**.

| Defect | What the code shows | Status |
|---|---|---|
| D01 prompt refinement substitutes unrelated tasks | Reproduced offline: the hub-siting prompt matched OSM export task 19.18 at 0.50 and the imagery prompt matched OSM download task 19.02 at 0.50, so a "prefer these tools" list the user never asked for was injected. | **Fixed in code (rc17 candidate):** a request that names a tool is only matched to a task that uses it, else it is sent as typed (`task_matcher.named_tools`, tests/test_task_matcher_named_tools.py). **Open:** requests that name no tool but sit in a cross-section tie (the severity prompt matched 21.09 whose first tool is a WorldPop fetch) still get a directive; the reported "Jordan OSM offer" on that prompt is not reproduced offline and needs the turn's log. |
| D02 `get_layers` / `get_attributes` fail | The #138 dict-only check (rc12-rc15). | **Fixed in rc16** (PR #202), live-tested in CI. The read-only SQL failure on a virtual provider is a separate tool error and is not addressed. |
| D03 hub distance wrong, table removed | Independent planar averages (887 / 1036 / 1622 m) were recomputed from the fixture's coordinates and match the report's "correct" column, so the question is whether the tool or the reply was wrong. The tool's own code measures planar metres on a projected CRS. | **Undecided:** tests/test_hub_siting_smoke_live.py pins the tool's output on the smoke fixture in CI. If it passes, the fault is in the model's reply (and the guard removed a table the tool did return); if it fails, it is a tool bug. |
| D04 unrelated operations, false DONE | Consequence of D01 (wrong directive, 20-call limit). | Addressed only as far as D01 is. |
| D05 confirmed edit does not continue to styling | By design: `_resolve_pending_confirmation` executes the confirmed tool directly "with no model turn involved", so the rest of a multi-step request never runs after Apply edit. | **Decision needed (not changed):** after a confirmed step succeeds, send one follow-up model turn ("the confirmed step finished; do any remaining part of my request") or have the tool apply the documented follow-on style itself. Recommendation: the follow-up turn, capped at one per confirmation. It changes behaviour users may rely on and cannot be live-tested here. |
| D06 imagery checkpoint failure freezes QGIS, URL shown | `FastSAM("FastSAM-s.pt")` downloads on QGIS's main thread. HTTP 416 is what resuming a partial download earns. | **Partly fixed:** failure text no longer contains URLs and says to delete the partial file (`describe_model_failure`). **Open:** the download still blocks the main thread (needs a two-phase tool). |
| D07 save says all persisted, memory layers come back empty | Correct: memory layers are saved as provider references. | **Fixed in code:** `save_project` lists temporary layers and warns they come back empty. A real fix (exporting them) is a product decision. |
| D08 raster classification range serialises as nan | The renderer's own `classificationMin/Max` default to NaN and only the shader had the range. | **Fixed in code:** `output_style.set_renderer_range` at all three pseudo-colour sites; live test added (CI). |
| D09 processing/script recovery noise (`native:buffer` not found in the script sandbox, `os` blocked) | Not investigated; the blocked `os` import is the sandbox working as designed. | Open, not reproduced. |
| D10 web source link malformed | The malformed text appears in the model's own grounded-search reply (`download.html">https://...`), not in a tool result. Gemini grounded search was used instead of `search_web`. | Open: provider output; no code change made. |
| A1 name `smoke_points_buffer_500` (missing `m`) | Naming from the model/tool. | Open, minor. |

## Environment findings (not code)
- Plugin Manager listed two Cartogen AI entries (one disabled). Remove the stale folder before the next run.
- The ZIP hash and installed-source equivalence were not established; the rc16 release publishes `SHA256-1.16.0-rc16.txt` for that.
- PostGIS (C2) skipped; fresh-profile install, upgrade, restart-twice and uninstall/reinstall checks remain unrun.
