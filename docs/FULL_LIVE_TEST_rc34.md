# Full live test: rc34 (every category, every input, every output)

This is the one document to follow for a **complete** hand test of the installed plugin. It exists because the last full hand run was on **rc22** (2026-10-09, `docs/RC22_LIVE_SMOKE_REPORT_2026-10-09.md`), and rc23 to rc34 have only been checked by CI. Everything the earlier sheets asked is gathered here with the data, the file paths and the evidence each row needs.

**Nothing in rc23 to rc34 has been hand-tested.** CI was green on each build, including live checks inside QGIS 4.2.2 against a local test server, but no row of this pack has been run by a person against a real model provider. Treat every row as unverified until you have run it and have the evidence.

## 1. What is in the pack

| Item | Where | What it is |
|---|---|---|
| This document | `docs/FULL_LIVE_TEST_rc34.md` | The procedure, the input inventory, the output and evidence rules |
| The row list | `docs/FULL_LIVE_TEST_rc34_ROWS.csv` | **179 rows**: every prompt or action, the expected result, the input files, the output file it should produce, the screenshot file name, and what the row did in the rc22 run. Built from the rc22 result matrix, the rc24 and rc34 sheets, the 16-category runbook and the clean-profile gate |
| The fixtures | `docs/release_smoke_assets/inputs/` | The synthetic data (section 4) |
| Fixture checksums | `docs/FULL_LIVE_TEST_rc34_INPUTS.sha256` | SHA-256 of every fixture file; the tool refuses to prepare a run if one differs |
| The helper | `tools/live_test_pack.py` | `prepare` builds the run folder; `check` reads your results and reports missing evidence |
| Older sheets | `docs/SMOKE_RUN_SHEET_rc15..rc22*.md`, `docs/RC24_HAND_VERIFICATION_SHEET.md`, `docs/RC34_HAND_VERIFICATION_SHEET.md`, `docs/RELEASE_LIVE_TEST_SCENARIOS.md` | Still the source of the exact wording; the row list copies them verbatim |

### Rows by group

| Group | Row ids | Rows | Last result in the rc22 hand run |
|---|---|---:|---|
| rc17 regression rows | R1 to R7 | 7 | 5 PASS, 1 FAIL, 1 NOT RUN |
| Fixes after the rc15-rc17 reports | N1 to N9 | 9 | 4 PASS, 3 FAIL, 1 INCONCLUSIVE, 1 NOT RUN |
| rc19 re-tests | A1 to A12 | 12 | 2 FAIL, 2 NOT RUN, 5 PASS, 3 INCONCLUSIVE |
| rc22 audit fixes | H1 to H10 | 10 | 4 NOT RUN, 4 PASS, 1 FAIL, 1 INCONCLUSIVE |
| rc21 re-tests | F1 to F7 | 7 | 4 PASS, 2 FAIL, 1 NOT RUN |
| rc20 new rows | D1 to D14 | 14 | 13 NOT RUN, 1 PASS |
| Map looks and allocation (rc13-rc15) | V1 to V11 | 11 | 8 FAIL, 1 PASS, 2 NOT RUN |
| Imported tables and measured values | T1 to T8 | 8 | 2 PASS, 4 FAIL, 2 NOT RUN |
| JIAF 2 analysis support | J1 to J17 | 17 | 12 FAIL, 4 PASS, 1 INCONCLUSIVE |
| Must still pass | K1 to K5 | 5 | 3 NOT RUN, 2 PASS |
| Plain language and map readability | P1 to P20 | 20 | 20 NOT RUN |
| rc24 new rows | Q1 to Q5 | 5 | not run before |
| rc34 sheet: Install and first run | RC34-I1 to RC34-I5 | 5 | not run before |
| rc34 sheet: Gemini through the QGIS network stack (first real-provider use) | RC34-G1 to RC34-G8 | 8 | not run before |
| rc34 sheet: The sender switch (rc32) | RC34-S1 to RC34-S2 | 2 | not run before |
| rc34 sheet: Log lines (rc32 to rc34) | RC34-L1 to RC34-L3 | 3 | not run before |
| rc34 sheet: Dialog notices and redraw (rc31) | RC34-D1 to RC34-R1 | 5 | not run before |
| rc34 sheet: Downloads through the QGIS network stack (rc30) | RC34-W1 to RC34-W4 | 4 | not run before |
| rc34 sheet: Lifecycle and package | RC34-P1 to RC34-P3 | 3 | not run before |
| Scenario A: Vector & Geoprocessing | SC-A1 | 1 | not run before |
| Scenario A: Raster | SC-A2 | 1 | not run before |
| Scenario A: Humanitarian Logistics | SC-A3 | 1 | not run before |
| Scenario A: Data Analysis & Prediction | SC-A4 | 1 | not run before |
| Scenario A: Styling & Labeling | SC-A5 | 1 | not run before |
| Scenario A: Export & Reporting | SC-A6 | 1 | not run before |
| Scenario A: Print Layouts | SC-A7 | 1 | not run before |
| Scenario B: Humanitarian Data | SC-B1 | 1 | not run before |
| Scenario B: AI Imagery Feature Extraction | SC-B2 | 1 | not run before |
| Scenario B: Satellite Imagery & Vision | SC-B3 | 1 | not run before |
| Scenario B: Reporting & Document Analysis | SC-B4 | 1 | not run before |
| Scenario B: System Web Search | SC-B5 | 1 | not run before |
| Scenario C: Monitoring & Scheduling | SC-C1 | 1 | not run before |
| Scenario C: Database & Workflows | SC-C2 | 1 | not run before |
| Scenario C: Project Management and upgrade round-trip | SC-C3 | 1 | not run before |
| Scenario C: Task & Memory Management | SC-C4 | 1 | not run before |
| Scenario C: PyQGIS scripting sandbox | SC-C5 | 1 | not run before |
| Final clean-profile and upgrade gate | GATE-1 to GATE-7 | 7 | not run before |

Row ids are unique. Rows from the 16-category runbook start with `SC-`, from the rc34 sheet with `RC34-`, from the final gate with `GATE-`. The other ids (R, N, A, H, F, D, V, T, J, K, P, Q) are the ones used since rc18.

## 2. Rules

1. **Data and destination.** Every prompt goes to the model provider you configured, together with what the agent reads to answer it (layer and field names, counts, tool results, which can include coordinates). Run these rows only on the synthetic fixtures, with a provider you are authorised to send them to; for anything else use a local Ollama model. If an egress card names a layer you did not expect, cancel it and report it. Nothing here authorises sending real or sensitive data anywhere (`docs/RELEASE_LIVE_TEST_SCENARIOS.md` section 1a).
2. **A plausible chat answer is not evidence.** Check the Activity panel for the tool call that ran and the real canvas, layer, attribute table, file, layout or timer. A traceback, hang, silent no-op, fabricated result, or a success message without an artifact is a **FAIL**.
3. **Result words:** `PASS`, `PASS (degraded)` (only where the row says it is allowed), `FAIL`, `INCONCLUSIVE` (you could not tell), `NOT RUN` (and write why), `SKIP` (only for the PostGIS rows with no disposable database). Never write a pass you inferred.
4. **Never paste an API key into a result, a note, a screenshot or a report.** Where a row shows the last four characters of a key, write only those four. Keep QGIS's Network Logger panel closed while a key is configured: while it is open, request headers, including the API key, appear in it.
5. **Read confirmation cards before approving:** check the operation and the target.
6. **Use a fresh QGIS 4.2 profile**, and a writable copy of the fixtures, never the files in the repository.
7. A row that passes but takes **more than 4 model calls** is a finding. Record the call count in the `model_calls` column.
8. Do not close an issue because a row passed here. An issue is closed on a hand-verified pass of its own row.

## 3. Before you start

You need:

- QGIS **4.2.x** on Windows, macOS or Linux, and a fresh profile (Settings > User Profiles > New profile; start QGIS with it).
- The rc34 zip `cartogen_ai_v1.16.0-rc34.zip` and its SHA-256 from the release page (`SHA256.txt`). Record both.
- A model provider: Google Gemini (note whether the key's project is on the free or a paid plan), OpenRouter, or a local Ollama model. Settings offers only these three and the Cartogen API stub (do not test the stub: no hosted gateway exists).
- Internet access for the rows that call real services: building footprints (SC-B1), satellite scene search (SC-B3, N4), web search (SC-B5, N6), data downloads (RC34-W1 to W4). Write down whether a proxy or VPN is on. One retry for third-party rate limiting is acceptable; a fabricated or silently empty result is not.
- Optional; mark the rows that need them NOT RUN, with the reason, when you do not have them: Python packages for imagery (`torch`, `ultralytics`) and the FastSAM model download (SC-B2, R3, H9), `pypdf`/`pdfplumber`/`python-docx` for table extraction (SC-B4), a disposable read-only **PostGIS** database `cartogen_smoke` with table `smoke_records(id, value)` (SC-C2, Q4, Q5), and any extra service keys a tool asks for.
- Time: the 16-category runbook alone states 45 to 75 minutes for a first pass. The full 179-row list is much longer; no one has timed it. Plan it in sessions (section 7) and do not claim a quick pass: a row counts only when its evidence exists.

### Set up the run folder

```
python tools/live_test_pack.py prepare C:/Cartogen-AI-Smoke/rc34
```

Use any empty, writable folder; this one is called **TEST_ROOT** below. The command:

1. checks every fixture file against `docs/FULL_LIVE_TEST_rc34_INPUTS.sha256` and stops if one differs;
2. creates `inputs/`, `outputs/`, `screenshots/`, `logs/` and `results/` under TEST_ROOT;
3. copies the fixtures into `inputs/`;
4. writes `results/results.csv` (the file you fill in) and `results/prompts_filled.csv` (every prompt with `{TEST_ROOT}` replaced by the real absolute path, ready to paste);
5. writes `README_FIRST.txt` with these paths.

Then:

1. Install the zip: Plugins > Manage and Install Plugins > Install from ZIP. If an old `cartogen-ai` folder (rc24 or earlier) is in the profile's `python/plugins` folder, delete it first. Restart QGIS twice.
2. Open **View > Panels > Log Messages** and keep it visible. Capture the plugin's displayed version in Help and Settings.
3. Open `TEST_ROOT/inputs/smoke_start.qgz` directly. Its layer paths are relative to `inputs/`. Check all **seven** layers load; if one does not, stop and repair the copy, do not have the agent invent data.
4. In Settings: choose the provider and model (use **auto (recommended)**), enter the key, and tick **"Record every model request and reply to a local folder (diagnostics)"**. The trace is one file `cartogen_api_trace/api_calls_<date>.jsonl` written next to the project (here `TEST_ROOT/inputs/`, because the project is opened from there) or, for an unsaved project, in the QGIS profile folder.
5. Save the screenshot `TEST_ROOT/screenshots/00_start.png` showing the seven layers, the Log Messages panel and the Cartogen dock.
6. Fill in the candidate record (section 9).

## 4. Input inventory

All spatial layers use **EPSG:32636** (metres). The data are synthetic Amman-area fixtures and must not be read as real population, need, elevation, buildings or imagery. `smoke_start.qgz` was written by QGIS 4.2.2.

| File in inputs/ | Size (bytes) | SHA-256 | Content | Rows that name it |
|---|---:|---|---|---|
| `smoke_data.gpkg` | 180224 | `7bd3fe2b616539b41fe24862194968bc4f354befa7d21cfd06166652b03b2b4f` | The five vector layers (next table) | 38 rows (see the inputs_used column) |
| `smoke_dem.tif` | 16752 | `5dad1e3e1dd34b4f406cd995cbb77b1212e065205d1dfd104baa8db015b16b01` | 128 x 128, one band, values 35 to 214 (mean 124.2) | R4, A11, A12, T4, SC-A2 |
| `smoke_dem.tif.aux.xml` | 359 | `430f87023fc8736aff69eb62e50fd9fa7df08fbd3799b79e7469aac44c293753` | Band statistics for smoke_dem.tif (keep it next to the raster) | with its raster |
| `smoke_image.tif` | 49566 | `9f829b4583e27df6d43d63385b164f81f7f9e1ddcb4f7754d8bb418c443e19da` | 128 x 128 synthetic RGB. Useful for the inference and dependency path, not for asserting that real objects exist: a truthful zero-detection result is acceptable | R3, A4, T6, SC-B2 |
| `smoke_image.tif.aux.xml` | 1023 | `9e14947e3ccc6def301e621fe10ca76728c6ab6fe77f393a7e74baa6fbe0bf6e` | Band statistics for smoke_image.tif (keep it next to the raster) | with its raster |
| `smoke_inform.csv` | 158 | `18b554e8d7a2a01790b795d7345d70196f8e33e25915224243075f9fd582d665` | admin_name, inform_risk, hazard_exposure, vulnerability, lack_of_coping_capacity: District_1 2.4, District_2 7.1, District_3 4.6 (plus components) | T2 |
| `smoke_ipc.csv` | 106 | `ba06d7876a7ab591d00802a9b7ed3ba1e2e2e489cf1312dcea268c58d4a34531` | admin_name, phase, population, phase3plus: District_1 2/1000/150, District_2 4/2000/1200, District_3 3/1500/600 | T1 |
| `smoke_jiaf_hxl.csv` | 822 | `6d7e3354b1e45305dd4dadcde06a5576e5bf5da9fd2c7dddde1cab23b0656ecf` | JIAF 2 sector table with an HXL tag row: Admin2 P-code, District, Population and a PiN and Severity pair for eight sectors (cccm, education, nutrition, food_security, health, protection, shelter, wash). District_1 and District_2 are complete, District_3 has gaps (not assessed), and an Outside_area row matches no polygon | T8, J1, J3, J4, J5, J9, J12, J13, J14, J15, J16, J17 |
| `smoke_start.qgz` | 14765 | `d0d85213ced6992099745b8ab5401cd1f33ad9b37a9f26006c48f329872db6ca` | The starting project: seven layers (smoke_image, smoke_dem, smoke_points, smoke_hubs, smoke_admin, smoke_zones, smoke_boundary), project CRS EPSG:32636, data sources relative to inputs/ | all rows start from it |
| `smoke_tables.docx` | 35474 | `ba946dcfe3f05f316ebaa26babf1f737401f5965656d6f368303fa36b3aa1fb4` | Table id / value = A01/10, A02/20, A03/30 (same content as the .pdf) | SC-B4 |
| `smoke_tables.pdf` | 2745 | `47f5a31e4b8f2bd354bcb0406897163ce22bff657cad19276e34f3a8b3e223c1` | Table id / value = A01/10, A02/20, A03/30 (same content as the .docx) | SC-B4 |
| `smoke_unosat.csv` | 246 | `80eaa1b3789999ddea32160d3d635f0f6c7490fd72d6e9ffdf5e59e36ca2b82c` | site_id, latitude, longitude, main_damage_site_class: six damage points around 31.94 N 35.92 E (Destroyed, Severe Damage x2, Moderate Damage, Possible Damage, No Visible Damage) | T3 |

Full checksums for every file are in `docs/FULL_LIVE_TEST_rc34_INPUTS.sha256`; `prepare` verifies them.

### The vector layers in `smoke_data.gpkg`

| Layer | Features | Fields and values |
|---|---:|---|
| `smoke_points` | 5 | `name` / `category` / `population` / `need`: North clinic 1200 3; Central school 2100 8; East clinic 1650 6; West shelter 950 9; South school 1800 4 |
| `smoke_hubs` | 3 | `name`: Hub_A, Hub_B, Hub_C (candidates for the hub-ranking rows) |
| `smoke_boundary` | 1 | `admin_name` "Smoke Area", `admin_type` "test boundary" (polygon around all points) |
| `smoke_zones` | 3 | `zone_type`: urban, mixed, open |
| `smoke_admin` | 3 | `admin_name` / `population` / `need` / `severity_smoke`: District_1 1000 3 0.0; District_2 2000 7 0.7857; District_3 1500 10 0.75 |

**Fixture note you must read.** The shipped `smoke_admin` already holds a populated `severity_smoke` field. Row V1 relies on it. Row SC-A4 says "verify no field exists before approval", which cannot be true of this file: for SC-A4 either write the score to a **new** field name as row N1 does (`severity_rc18`) or drop the field in your copy first, and write which you did in the notes. Row N1/N2 use `severity_rc18`, so run those on a copy where it does not exist yet.

Rebuilding the fixtures (developers only): `python tests/build_release_smoke_fixtures.py --documents`, then QGIS's `python-qgis.bat tests/build_release_smoke_fixtures.py --spatial`. Update `docs/FULL_LIVE_TEST_rc34_INPUTS.sha256` afterwards.

## 5. Outputs and evidence

### Folder layout

```
TEST_ROOT/
  inputs/        copied fixtures (the project and GeoPackage change as rows write to them)
  outputs/       files the rows write
  screenshots/   evidence images
  logs/          exported logs, API trace summary
  results/       results.csv, prompts_filled.csv, summary.md
  README_FIRST.txt
```

Never write test output inside the installed plugin folder.

### Output files the rows promise

| Row | File | Path under TEST_ROOT | What to check |
|---|---|---|---|
| N3, SC-A6 | CSV export of `smoke_points` | `outputs/smoke_points.csv` | exists, headers, 5 data rows, formula-like values serialised safely; N3: the overwrite card appears when a non-empty file is already there, Cancel leaves it untouched |
| N8, SC-A7 | Print layout PDF | `outputs/smoke_layout.pdf` | opens, not blank, title "Smoke Test Layout", legend, north arrow, scale bar |
| N9 | GeoPackage from the four-step plan | `outputs/plan_rc18.gpkg` | the clipped buffer layer is inside |
| SC-C3 | Saved project | `outputs/smoke_roundtrip.qgz` | reopens with layers, styles, layout, CRS and one visible label intact |
| SC-C4 | GeoPackage from the plan | `outputs/smoke_plan_result.gpkg` | the clipped result is inside |
| SC-C5 | **must NOT exist** | `outputs/sandbox_should_not_exist.txt` | the blocked script must not create it |

For N3, N8 and N9 the prompts give a **relative** path (`outputs/...`) on purpose, to test path resolution. The reply must name an absolute path and the file must exist there; if the project is saved the file lands next to the project, which here is `inputs/`. Write the absolute path from the reply in the notes, and copy the file into `outputs/` if it is elsewhere. `check` looks for the file by name anywhere under TEST_ROOT.

Rows without a promised file may still write one (an export, a dashboard, a layout). Note the path the reply names and copy the file into `outputs/<row id>_<name>`.

### Screenshots

- Save them as `TEST_ROOT/screenshots/<row id>.png`, or `<row id>_<what>.png` when a row needs several (for example `N3_card.png`, `N3_after_cancel.png`). `check` accepts either form and treats a decided row with no matching image as missing evidence.
- Every row: the chat reply **and** the Activity panel showing the tool that ran, in one image where you can.
- Rows that change the map: the canvas with the legend open, and the attribute table of the layer that was written.
- Rows that write a file: the file explorer showing the file with its size and date, and the opened file.
- Confirmation rows (cards): one image of the card before you click, one after.
- A FAIL: also the Log Messages lines for that turn (tool names, statuses, CRITICAL lines; no coordinates) and what you did to recover.

### Logs

- After the run, in Log Messages select all text of the plugin's tab and the `Agent` tab, copy it into `TEST_ROOT/logs/qgis_log_<date>.txt`.
- Before sharing any log, search it for your key (the last four characters, then the first four). A key anywhere in a log is a FAIL of row RC34-L3.
- API trace summary (section 1b of the 16-category runbook): after the last row, `python tools/summarize_api_trace.py TEST_ROOT/inputs/cartogen_api_trace > TEST_ROOT/logs/api_trace_summary.txt`, and for any flagged turn add `--show-turn <turn id>`. Do **not** send the raw `.jsonl`: it holds layer names, attribute values and tool results. Turn the Settings option off when you finish.

### The results file

`results/results.csv` has one line per row. Fill in `result`, `model_calls` (from the `model_call` lines for that request, or the trace summary), `notes` (what you saw, absolute paths, provider and model) and `defect` (issue number if you filed one). The columns `last_known`, `inputs_used`, `expected_output_file`, `evidence_to_save` and `screenshot_file` are guides and need no editing.

## 6. Check your evidence at any time

```
python tools/live_test_pack.py check C:/Cartogen-AI-Smoke/rc34
python tools/live_test_pack.py check C:/Cartogen-AI-Smoke/rc34 --strict
```

It writes `results/summary.md` and prints it: result counts overall and by group, FAIL rows, rows with a result but no screenshot, PASS rows whose promised file is missing, forbidden files that exist, PASS rows with more than 4 model calls, unrecognised result words, and which input files the run changed (expected for the project and the GeoPackage). With `--strict` it exits 1 if a decided row has no evidence. It never edits `results.csv`.

## 7. Order of work

Run in this order so a problem in an early phase does not waste the later ones. Each phase can be a separate session.

1. **Phase 0 (install gate), about 15 minutes:** install, restart twice, exactly one toolbar action, one Plugins-menu action and one dock; Help shows rc34; Settings lists only OpenRouter, Gemini, Ollama and the Cartogen stub. Rows `RC34-I1` to `RC34-I5`, `GATE-1`, `GATE-2`. If any fails, stop.
2. **Phase 1 (provider path):** rows `RC34-G1` to `RC34-G8`, `RC34-S1`, `RC34-S2`, `RC34-L1` to `RC34-L3`. Nothing else is worth running until a plain "Hello." gets a real reply. If it does not, the error line now says what each model answered and which key was sent; follow `docs/RC34_HAND_VERIFICATION_SHEET.md` section 2.
3. **Phase 2 (the 16 categories):** `SC-A1` to `SC-A7`, `SC-B1` to `SC-B5`, `SC-C1` to `SC-C5`. Use a fresh project copy for `SC-A7` (the layout tool replaces an existing layout of that name).
4. **Phase 3 (what changed since rc22):** `RC34-D1` to `RC34-R1` (dialogs and redraw), `RC34-W1` to `RC34-W4` (downloads), `RC34-P1` to `RC34-P3` (lifecycle and package), then the rc24 rows `Q1` to `Q5`.
5. **Phase 4 (carry-over matrix):** groups in this order: R, N, A, H, F, D, then V, T, J, K, P. Open a **NEW CHAT** before every row that says NEW CHAT. Prior failures are listed in section 8, so you know which rows to watch.
6. **Phase 5 (upgrade gate):** `GATE-3` to `GATE-7`: clean-profile critical path, then an upgrade profile that starts on the last stable release (install, open the plugin once, save `smoke_start.qgz`, then install the rc34 zip over it, restart, and check version, settings, credentials, project round-trip, actions, docks and chat/task state), then uninstall and reinstall.

### Procedure for each row

1. Open a new chat if the row says so, and have the Log Messages panel visible.
2. Copy the prompt from `results/prompts_filled.csv`, not from this document: the paths in it are real. Send it exactly; do not rephrase.
3. Read any confirmation card before approving, and take the screenshot.
4. Compare with the `expected` column using the Activity panel and the real layer, file or state.
5. Count the `model_call` lines for the request (tag `Agent` in Log Messages).
6. Save the evidence (section 5), then fill in `result`, `model_calls` and `notes`.
7. Cancel any recurring schedule you created (SC-C1) before moving on.

## 8. What each earlier row did, and what is known to be open

Last hand run (rc22, 120 matrix rows): 32 PASS, 33 FAIL, 6 INCONCLUSIVE, 49 NOT RUN. The `last_known` column in the row list carries each row's note. A row that failed in rc22 is not automatically fixed in rc34: expect some of these to fail again and report them as such.

- **Passed in rc22 (watch for regressions):** R1, R3, R4, R5, R6, N1, N2, N4, N7, A5, A7, A10, A11, A12, H2, H3, H4, H10, F1, F4, F5, F6, D5, V5, T1, T7, J2, J8, J11, J12, K2, K5
- **Failed in rc22:** R2, N3, N8, N9, A1, A4, H5, F2, F3, V1, V2, V3, V4, V6, V7, V8, V11, T2, T3, T4, T6, J1, J3, J4, J5, J6, J7, J9, J10, J13, J14, J15, J16
- **Inconclusive in rc22:** N5, A6, A8, A9, H8, J17

Known open, do not expect a pass (from the rc22 sheet and later): other expensive tools still block the GUI, so QGIS can freeze on a large raster (#221); database and web-service layers are still writable by a script (#220), and a read-only database role is the real protection for SQL; model-added plans and arrange steps (N3 and N9); geography suggested from project memory in prose (N1); PostGIS connections that authenticate through a QGIS auth configuration; the legend-by-role and attribution items in #165. Whether a redirect on your network ever caused the Gemini 403 is open: rc33 handles redirects, tested in CI against a local server only.

## 9. Candidate record and report

Fill this in at the top of your report.

| Field | Value |
|---|---|
| Candidate version and tag | rc34, `cartogen-ai-v1.16.0-rc34` |
| Zip file name and SHA-256 | |
| Git commit of the release | `c7cec6c0c7b30f6dfa503292d721879dcb2fbbce` |
| QGIS version, build and OS | |
| Fresh profile name | |
| Provider and model; free or paid plan | |
| Proxy or VPN on? | |
| Optional pieces present (torch/ultralytics, FastSAM, pypdf/pdfplumber/python-docx, PostGIS) | |
| Tester and date/time | |

Send back: `results/results.csv`, `results/summary.md`, the `screenshots/` folder, `logs/` (after the key search), and the files in `outputs/`. For each FAIL use this block:

```text
Candidate/version and SHA-256:
QGIS/OS/profile:
Row id and exact prompt:
Expected versus actual result:
Tool shown in Activity and confirmation decision:
Input layer/file, CRS, and output path:
Sanitized QGIS log excerpt:
Screenshot filenames:
Reproducibility: always / intermittent / once
Cleanup or recovery performed:
```

After an unexplained destructive-action or database-security failure, preserve the evidence, close the project without further edits, and reproduce only in a disposable project and profile.

**Overall PASS** requires every mandatory row to pass, and every skip or degraded result to be one the row permits and to be documented. Any security-control failure (the key in a log, the sandbox file existing, a database write that went through, a confirmation that could be bypassed) blocks the release at once.

## 10. When you finish

- Cancel every recurring schedule and close the project.
- Turn off the API trace option in Settings.
- Remove the test API key from Settings if the key is not yours to keep in this profile, and delete `cartogen_api_trace/` after you have kept what you need (it holds layer names and tool results).
- Keep TEST_ROOT until the report has been read; do not leave it on a shared drive.
