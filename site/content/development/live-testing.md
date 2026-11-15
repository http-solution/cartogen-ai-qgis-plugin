---
description: The hand test of the installed plugin in desktop QGIS: what the pack contains, the rules, and how to run it and report results.
---
CI proves the code behaves inside QGIS 4.2.2 against test servers and fakes. It cannot prove that the plugin works in a person's desktop with a real model and real data. The **live test pack** is the procedure for that. Nothing in a release counts as hand-tested until a row has been run by a person and has evidence.

## What is in the pack

| Item | Where | What it is |
|---|---|---|
| The procedure | `docs/FULL_LIVE_TEST_rc34.md` | Rules, setup, input inventory, outputs and evidence, order of work |
| Older rows | `docs/FULL_LIVE_TEST_rc34_ROWS.csv` | 179 rows: every prompt or action, expected result, input files, promised output, last known result. Built from the rc22 result matrix, the 16-category runbook and the clean-profile gate. |
| Newer rows | `docs/FULL_LIVE_TEST_rc37_ROWS.csv` | 23 rows (`RC37-*`) for what changed after rc34: research answers, incident search, earthquake and conflict tools, URL downloads, responsiveness, Processing |
| Fixtures | `docs/release_smoke_assets/inputs/` | Synthetic Amman-area data: a GeoPackage of five layers, a DEM, an RGB image, small CSVs, a Word and a PDF table, and a starting project `smoke_start.qgz`; checksums in `FULL_LIVE_TEST_rc34_INPUTS.sha256` |
| Helper | `tools/live_test_pack.py` | `prepare` builds a run folder and verifies fixtures; `check` reports rows with a result but no evidence |
| Bundle builder | `tools/build_live_test_bundle.py` | Builds a tester-friendly zip: `README_FIRST.txt`, the plugin zip, the fixtures, a `3_PROMPTS.html` page with Copy buttons and a `4_RESULTS.csv` sheet. No Python needed to *run* the test. |
| Older sheets | `docs/SMOKE_RUN_SHEET_rc15…rc22`, `RC24_`/`RC34_HAND_VERIFICATION_SHEET.md` | Source of the exact wording of older rows |

## Rules

1. **Data and destination.** Every prompt goes to the model provider you configured together with what the agent reads (layer and field names, counts, results). Use only the **synthetic fixtures**.
2. **A plausible chat answer is not evidence.** Check the Activity panel for the tool that ran and the real layer, file or canvas. A traceback, hang, silent no-op, fabricated result or a success message without an artifact is a failure.
3. **Result words:** PASS, PASS (degraded, only where the row allows), FAIL, INCONCLUSIVE (you could not tell), NOT RUN (say why), SKIP. **Never write a pass you inferred.**
4. **Never paste an API key** into a result, note or screenshot, and keep QGIS's Network Logger closed while a key is configured.
5. **Read confirmation cards** before approving.
6. **Use a fresh QGIS 4.2 profile** and a writable copy of the fixtures.
7. A row that passes in **more than four model calls** is a finding: record the call count.
8. **Do not close an issue because a row passed.** An issue is closed on a hand-verified pass of its own row.
9. **Do not put the Stop instruction in the prompt.** Press the Stop button yourself while the job runs; a model that reads "press Stop" may refuse the task, which tests nothing.

## Order of work

0. **Install gate** (about 15 minutes): install, restart twice, one toolbar action, one dock, the right version in Help, "Hello." gets a real reply.
1. **The newest features** (the rc37 rows).
2. **Responsiveness** (long jobs, Stop).
3. **Regression**: the 16 categories, then the older rows in the order the procedure gives.
4. **Upgrade gate**: a clean profile, then an in-place upgrade from the last stable release.

## Evidence per row

A screenshot named for the row, the Activity panel showing the tool call, the layer or file it produced, the model-call count (`model_call` lines in Log Messages, tag `Agent`), and a result with notes. With the evidence folder switched on, the plugin also records each call's arguments, results and timings. That folder is what exposed, in the rc37 run, a tool that had been failing on every call since rc24 and a layer of invented records the tester had marked as passing.

## What the most recent hand test found

The rc37 run ([report](repo:docs/RC37_LIVE_TEST_REPORT_2026-10-13.md)) was driven by an automated tester, then re-judged against the evidence and the code: 17 of 23 rows passed, two were inconclusive (Stop was never exercised against a running job), two were not recorded and two optional rows were skipped. It found a registration bug (fixed in rc38), a false "step did not run" note (rc38) and invented incidents added after empty searches (fixed in rc39). It also showed that three "failures" were wrong expectations in the rows themselves, which were corrected.

## Reporting

Send back `results.csv`, `summary.md`, the screenshots and logs, plus the plugin version shown in Help, QGIS version, OS, provider and model, free or paid plan, and whether a proxy or VPN was on. Do not include API keys or an API trace that contains one.
