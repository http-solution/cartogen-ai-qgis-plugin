# rc17 installed-profile smoke report: triage (2026-10-06)

A dated record, not a re-test. Input: `docs/RC17_LIVE_SMOKE_REPORT_2026-10-06.md` (as received). Of the 7 regression rows, 5 passed their core
check (R1, R2 core, R4, R5, R7), R3 failed on the model download, R6 failed again. The 16-category result was PASS 7, FAIL 8, SKIP 1.
"Fixed in code" means offline tests and, where it touches QGIS, a live test in CI; **nothing here is hand-verified**.

| Report item | What the code shows | Status |
|---|---|---|
| R6 / D04: after "EPSG:3857" no tool call, model says `add_point_layer` is unavailable | Confirmed offline. The router scores tools on the NEW message only; "EPSG:3857" shares no word with any tool, so `add_point_layer` was not in the turn's tool list at all. The rc16 hint could not help because the tool was never offered. | **Fixed in code:** `ToolRouter.filter_relevant_tools(carry_over_tools=)` keeps the tools the previous turn used (at most 8, for two turns); the orchestrator passes them. `tests/test_tool_router_carry_over.py` reproduces the missing tool without it. |
| D02: R2 ranking footnoted "Not from a tool result ... 886.49 m; 1,870.49 m ..." | Confirmed: the guard's `_SCALED` pattern read a lowercase "m" as million ("886.49 m" = 886.49 million), so every metre distance looked like an ungrounded national total. | **Fixed in code:** one-letter suffixes count only as capitals ("29.8M"); `m` is metres. |
| D02: B3 STAC table replaced by "Table removed ... No data was retrieved" although the STAC call succeeded | Confirmed: any failed call (three unrelated SQL calls, one web search) made the guard strip every table, even when another data tool succeeded. | **Fixed in code:** with a successful data tool and nothing pending, failed calls add a note and the tables stay. The old behaviour is kept when nothing succeeded or a call is pending. The model's drift into unrelated calls (B1, B3) is D01's consequence. |
| D01: refiner proposes unrelated tasks (A4 severity, C4 plan; also R4, A7, B1, B3) | Reproduced: the severity request (22 words) and the buffer-clip-export plan (18 words) tied across sections on two generic words each and kept a wrong directive. R4 and A7 already fell below the floor offline (no directive); the wrong previews seen there are not reproduced offline. | **Partly fixed:** a cross-section tie is trusted only if the task's keywords cover at least a quarter of the request's content words (`task_matcher._coverage`). **Open:** B1/B3/A7/R4 behaviour in a real chat is unverified; the matcher stays a keyword scorer. |
| R3 / D03: FastSAM checkpoint 416, QGIS not responding ~43 s | The URL cleanup worked (`<url removed>`, useful message). The download still runs on QGIS's main thread. | **Open** (needs the extraction as a two-phase tool). |
| A4 / D05: Apply edit does not continue to the requested styling | By design (the confirm button runs the tool with no model turn). | **Still needs your decision** (see `RC15_SMOKE_TRIAGE_2026-10-06.md`, D05). |
| A6 / D06: explicit "preview before replacing" ignored on a CSV overwrite | `export_to_csv` overwrites an existing file without a confirmation gate. | **Decision needed, not changed:** gate overwrites of existing files behind the same confirmation card. It changes repeat-export workflows. |
| A7 / D07: layout title/path taken from earlier turns | Model/context behaviour after a wrong directive; not reproduced offline. | Open. |
| D10: stale "latest release" from grounded search | Provider/model knowledge, not a tool result. | Open; no code change. |
| D11 buffer name `..._500` for `..._500m`; D12 repeated facility-type question | Not investigated. | Open. |

## Passed in rc17 (per the report, hand-run)
R1 `get_layers` works; R2 hub ranking with the correct task (21.19) and distances 886.49 / 1035.21 / 1621.51 m; R4 raster range survives save/reopen; R5
the save warns about the temporary layer; R7 single-point layout prints at a valid scale (1:20,808); C1 scheduler, B4 PDF/Word tables, A5 styling, C5 sandbox, C3
project round-trip. The rc16 CRS retry (R6) did not work, for the router reason above.

## Update, same day: the rest of the report, fixed in code
A second pass went through every remaining item. None of this has run in QGIS or against a real model; each has offline tests, and the QGIS-touching
parts are covered by the CI live job where one exists.

| Item | Cause found | Fix |
|---|---|---|
| The wrong clarification, preview or "OSM question" on an unrelated request (D01, also A4, A7, B1, B3) | The chat folded whatever came next into the open question as "Details: ...", so a user who answered by typing a NEW full request got the OLD request run with the new one pasted under it. | `reply_vocab.is_new_request`: a full request typed over an open question abandons the question (short answers behave as before). |
| Apply edit does not continue to the requested styling (D05, A4) | By design the confirm button runs the tool with no model turn. | After a successful confirmed step, a request with more than one step (or a sequence word) gets one follow-up turn (max 3 per request, marked, not echoed as a user bubble). Tool logic, no decision needed. |
| CSV overwritten although a preview was requested (D06, A6) | `export_to_csv` / `export_layer` had no overwrite gate. | They return a PREVIEW_REQUIRED card when the target exists, is non-empty and was not written by the plugin this session; re-running the plugin's own export stays silent. Only the Apply button can set `confirmed`. |
| Imagery download freezes QGIS ~43 s, then HTTP 416 (R3 / D03) | The checkpoint downloaded inside the tool on the main thread; 416 is a resume from a partial file. | `extract_features_from_imagery` is a two-phase tool: `ensure_checkpoint` runs on the background thread, deletes a partial file and retries once; only inference and layer creation run on the main thread. |
| "Which facility or service type?" asked twice of a request that names its own layers (D12, R2) | Slot evidence knew health/school/clinic words but not hubs, and ignored named layers. | A layer-like identifier or data file answers facility, area, admin level and population-source slots; hub/depot/facility/site/camp/centre/station words answer the facility slot; hazard, sector and DEM are still asked. |
| Buffer named `..._500` for a requested `..._500m` (D11, A1) | The tool had no way to be told a name. | `buffer_analysis(output_name=)`. |
| Stale "latest QGIS release" (D10, B5) | The search had no date. | `freshen_query` adds today's date and a freshness instruction to recency queries (Gemini and OpenAI grounded search). |
| `Algorithm native:buffer not found` in the script sandbox (rc15 D09) | The isolated worker has no Processing providers. | The error gets a hint naming `buffer_analysis`, `clip_layer` and `run_allowlisted_processing_algorithm`. |
| 14-15 unrelated calls before a named tool runs (B1, B3) | No check that the tool the user named was ever called. | A single corrective nudge after four calls without the named tool (`_named_tool_drift_nudge`). |
| R4: a raster ramp request matched a data-standards task | One shared word in a long request. | A request of more than 8 content words needs two distinct keyword hits. |

Still open: A7 (layout title and path taken from earlier turns) and A4's wrong output field are model-argument problems with no reproduction offline; the matcher and state fixes above remove the known
ways stale text reached them. Not code: the second Cartogen entry in Plugin Manager and the stale web answer's source.
