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
