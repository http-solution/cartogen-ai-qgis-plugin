# Full live smoke run, 2026-11-04: triage of the agent's results

Run by an AI agent driving QGIS 4.2.3 on Windows 11 with Gemini (`gemini-flash-latest`), package `cartogen_ai_full_smoke_1.18.5` (44 rows). Reported: 5 Pass, 22 Partial, 12 Fail, 4 Skip, 1 Blocked. This is not a person's hand test: nothing here changes a ledger entry's "verified by hand" status. Dated record; not edited later.

## What the agent's Fail and Partial verdicts turned out to be
| Kind | Rows | Detail |
|---|---|---|
| Plugin, fixed | W13 | Help said Qt 6.11.0, QGIS said 6.11.1: `QT_VERSION_STR` is the build-time constant. Now `qVersion()` (the running library). |
| Plugin, fixed (probable cause) | A2, A3 | Connections opened from Settings saved the connection but the panel dropdown refreshed only if Settings was then accepted. Now Settings announces a saved connection and the dock refreshes. |
| Plugin or script, open | A1 | Every exported test page has an empty Legend box (heading only) and a blank map frame; the script's 11 checks pass. Needs a person to open `legend_A4_Landscape.pdf` and then try a real layout. |
| Plugin, open (UX) | V9 | Undoing a filled column offers a destructive remove-field card; the refusal only runs on Apply. The agent pressed Cancel, so the refusal was not seen. |
| Plugin, observation | A2 | The bad-key error shows the key's last 4 characters (`providers/base.py:283`, deliberate); an owner call. |
| My regression, fixed | F3 | `check_evidence.py` crashed (`KeyError 'failed'`): a loop variable shadowed the layout check. Also read `4_RESULTS.csv` from the wrong folder and called a confirm turn a FAIL. |
| My rows, fixed | D2, D3, E2, E4, E5, C1, F2, B5, B1-B4 | Rasters were 900 km from `smoke_admin`; lat/lon guard does not cover buffer; geographic CRS needs reprojecting; tidy needs same name and data; `native:polygonize` is outside the guard; dashboard needs live events; JIAF needs a full path; F2 hit the extent lookup first; "delete" meant Clear Saved Chat; "new chat" has no button. |
| Model wording, plugin record right | V3, W1, W2, W3, W5 | The tool result held the storage note, the check records, the licence flag, the `Data source:` line and the ranking `why`; the reply left some out. Rows now say to judge the record. |
| Agent slip | B1, V4, V5, many screenshots | `snap('B1')` typed into the chat; unsaved projects left no evidence folder; screenshots not saved as files. Prompt, rows and a new `shot()` helper address it. |
| Environment | V2, D1, B2, B4, W6, W7, F1 | Gemini unreachable, Overpass timeout, lock screen, no localhost from the agent's shells, no person at dialogs. |
| Unresolved | V4 | The model did not call `export_temporal_animation_frames` (the router does offer it offline); no evidence because the project was unsaved. Rerun. |

## What the run showed working (agent-observed, not hand-verified)
D5 (refusal names 4 km, grid at 4 km has 3,080 tasks), W11 (card with the "QGIS may pause" sentence; Cancel sends nothing), D2 steps 1, 5, 6, 7, D4 matrix and classification, C1 steps 1 to 5, E4 DXF, xlsx, CSV and PDF, E2 admin snap across CRSs, W8 to W10 workflow export, import and six refusals, W1 and W2 records, W4 report.

## Changes made in answer
`tools/check_evidence.py`, `tools/collect_evidence.py` (`shot()`, version lookup), `tools/layout_check_script.py` (console run, version lookup, docstring), `tools/make_full_smoke_fixtures.py` (rasters over `smoke_admin`), `docs/FULL_SMOKE_ROWS.json` (row corrections and v2 overrides), `docs/FULL_SMOKE_AGENT_PROMPT.md`, `src/cartogen_ai/core/environment.py`, `settings_dialog.py`, `dock_widget.py`. Tests: `tests/test_full_smoke_package.py`, `tests/test_environment_qt_runtime.py`, `tests/test_connection_panel_sync.py`, one live test in `tests/test_connections_window_live.py` (CI only).
