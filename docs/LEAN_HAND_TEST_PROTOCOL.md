# Lean hand-test protocol (from rc47)

Why: the rc46 run re-tested ~245 algorithm rows whose code had not changed since rc45 and cost a lot of API credit. Every live row
sends about 24k tokens of system prompt and tool schemas per model call, plus the growing chat history.

1. **Free gates first (no API credit).** The full unit suite replays every tool-sheet prompt and the 385 plain-language prompts through the
   router and task matcher with no model (`tests/test_rc46_hand_test_fixes.py`, `tests/test_plain_prompts.py`). Routing defects
   (tool not offered, wrong task, prompt dismissed as a fragment) are found here, not in QGIS.
2. **Plan the live run from the diff.** `python tools/plan_hand_test.py --base <last tested tag> --previous <last results csv> --target <tools a fix aimed at> --out delta.csv`
   lists only rows whose tool code changed, the fix targets and a small canary set when shared code changed. Everything else keeps its
   previous verdict (carried forward).
3. **Algorithm rows.** Run an algorithm row only if its family or `_processing_allowlist.py` / `processing_allowlist_tools.py` changed. A
   Processing-algorithm family that passed on the previous release and is unchanged is not re-run.
4. **Plain-language prompts.** Sample about 40 (the offline misses plus a few per family), not 385.
5. **One row, one chat** (new chat per row) so history does not pile up; screenshots only for failures; use a cheaper model for sweeps.
6. **Record cost.** Save the CartogenAI log (QGIS Log Messages) after the run and run `python tools/summarize_usage_log.py cartogen.log --csv usage.csv`: one line per prompt with model calls, input/cached/output tokens and tools offered, plus the five most expensive prompts.

Build the lean bundle with `python tools/build_lean_bundle.py --plugin-zip dist/cartogen_ai_v<version>.zip` (rows A: fix-targeted tool rows; rows B: plain-language sample). Build it around the zip the release workflow published, not a local build: the hashes differ.

rc48: the bundle for 1.17.0-rc48 replaces the rc47 one (rc47 was never run). It adds 8 rows for wave E1 (statistics, polygonize) and the export routing, DXF and spreadsheet changes, and appends a `dem_classes` raster to the fixture script for the polygonize row. See PLAN-007.

rc49: the bundle for 1.17.0-rc49 keeps only what is not proven. rc48's own rows were run on 2026-10-24, so its extra rows are replaced by 9 rows for the PLAN-008 to PLAN-012 changes (routing, geometry guard, coverage report, MultiPoint, contours, export confirmation card, publication reason, atlas, footer); the open-issue rows (OI-120, OI-128, OI-145/146, OI-148, OI-150 and the rest still open) come from the status table as before. The fixture script now also adds a MultiPoint layer `sens_multi`.

rc50: the bundle for 1.17.0-rc50 adds 7 rows for PLAN-014 (credits, No data, page size, export preset, profile, logo, sign-off) and a `districts_gaps` fixture layer to the rc49 bundle; the rc49 rows stay because they have not been run. The profile rows need a `cartogen_profiles/handtest.json` file next to the saved project; the first profile row gives its text. See PLAN-015.

rc51: the bundle for 1.17.0-rc51 adds 3 rows for PLAN-016 (profile re-read, lineage on export, footer fit) and rewords the OI-150 row to the real check (a cloud question about the renamed layer; the rc50 expectation was the layer's own tag). The rc50 rows stay because the first desktop run covered only 20 of 87. See PLAN-017.

1.18.0: the precise hand-test file for 1.18.0 (`python tools/build_lean_bundle.py --precise --plugin-zip ...`) holds only the rows that check what has never been seen by a person: set-up, the rc49 to 1.18.0 release rows (P8 to P17) and the open-issue rows of issues still open. It leaves out the rc44 tool re-checks and the plain-language sample. See PLAN-018.

1.18.1: the hand test is no longer a 29-row sheet. `python tools/build_hand_test_v2.py --plugin-zip dist/cartogen_ai_v1.18.1.zip` builds a bundle with (A) `layout_check_script.py`, run once in the QGIS Python console, which makes no model calls and costs no API money and measures and exports the layouts, and (B) the rows of `docs/HAND_TEST_V2_ROWS.json` that still need a person or a real model, each starting from its own stated state. `tools/check_evidence.py` reads what comes back. See PLAN-021.

1.18.3: re-run the five rows the 2026-10-26 hand run failed or flagged: A13 (Sentinel-2 scenes over Aden, last month, under 20 percent cloud: every scene listed must come from the tool and show cloud_cover under 20), C9 (score a convoy route against incidents within 500 metres on a latitude/longitude layer: only incidents within 500 m count), D5 (load a forecast CSV without coordinates: one table layer, no repeat), A4 and B6 (no literal <br> and no stray $ in the reply). See PLAN-025.

1.18.2: no new rows. The 1.18.1 bundle (script plus rows V1 to V9) still applies unchanged; add one row for the Yemen ADM1 request that failed on 2026-10-26 ("create a new layer of ADM1 Yemen"; expect a layer, or a log line that names the host and the status). See PLAN-024.
