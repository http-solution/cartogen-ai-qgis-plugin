# rc37 live smoke test: results and triage (2026-10-13)

Run on the rc37 bundle in desktop QGIS 4.2 with Gemini (`gemini-flash-latest`), by a computer-use agent following `3_PROMPTS.html`, with
the plugin's own evidence folders (`cartogen_evidence/<turn>/steps.jsonl` and `summary.md`) enabled. This report re-reads the agent's
`4_RESULTS.csv` against that evidence and the code; where they disagree the verdict below is the corrected one. Frozen once written: a
later run gets its own dated report.

**Evidence backing.** Rows F1 to F5, P1 and P2 (SC-A1 to SC-A3) are backed by evidence folders (every tool call, its arguments and result).
Rows A, N, E and W are backed by the agent's notes and screenshots only; their evidence folders were not in the returned zip.

## Verdicts

| Row | Agent said | Corrected verdict | Why |
|---|---|---|---|
| I1, I2 | blank | NOT RUN | Never recorded. The plugin was installed and working, but Help, the What's new text and the toolbar count were not checked |
| I3 | blank | PASS | Evidence turn 1: "Hello." answered in 1 call |
| A1 | PASS | PASS | Answer with named sources and a not-searched section; no "[Agent stopped]" |
| A2 | PASS | PASS (observational) | The model refused without calling a tool. The stall guard was not exercised |
| N1, N4 | PASS | PASS | `find_incident_reports` ran; one "Incident reports" layer, replaced not duplicated. Jordan returned 0 records from all five sources while A1 (Amman) found 10: not checked whether those 10 lie outside Jordan |
| N2, N3 | PASS | PASS | Social media and news refused honestly; Turkey layers built |
| E1, E2 | PASS | PASS | USGS layer coloured by magnitude; UCDP says preliminary and names the newest event, 31 Aug 2026 |
| **E3** | PASS | **INCONCLUSIVE** | The UCDP file was cached, so the request finished before Stop could matter. Stop was never tested against a running job |
| W1, W2 | PASS | PASS | GeoJSON added through the QGIS stack; 127.0.0.1 refused as non-public |
| **F1** | FAIL | **PASS** | The ranking is correct (Hub_A 886.5 m, Hub_B 1035.2 m, Hub_C 1621.5 m). My row wrongly demanded a result layer; `optimal_hub_siting` returns a table only. Row corrected |
| **F2** | FAIL | **INCONCLUSIVE** | The prompt contained "Press Stop about five seconds after it starts". The model called it a QA test and refused with no tool call, so nothing ran. Not a product freeze. Row corrected: the Stop instruction is no longer in the prompt |
| **F3** | FAIL | **PASS (degraded)** | The reply had the order (Hub_A, Central, North, West, East, South) and the total, 4,266.2 m; the agent only saw the bottom of the reply. No route line layer, because `optimize_delivery_route` builds one only from a road network layer. Finding: 9 model calls (limit 4) and four slow `execute_pyqgis_script` calls (about 4 s each) to build the stops layer by hand |
| F4 | PASS | PASS, **plus a real bug** | The classification worked. A follow-up call to `run_allowlisted_processing_algorithm` failed with `_run_allowlisted() got an unexpected keyword argument 'params'` (see below) |
| F5 | PASS | PASS | "Stopped by the user after 19 of 25 locations", counted honestly |
| F6, F7 | SKIP | SKIP | Optional |
| P1 | PASS | PASS | `smoke_dem_slope` added, range 0 to 7.16 degrees. The agent's note of "EPSG:32630" is not in the evidence, which says EPSG:32636, the file's real CRS |
| P2 | PASS | PASS | Buffer, multicolour stretch and hub ranking all match the rc22 values |

## Real defect found and fixed

`run_allowlisted_processing_algorithm` has been unusable for the model since rc24. PR #249 inserted the helper `_run_allowlisted` between
the `@register_tool` decorator and the tool function, so the registry held the helper, which takes `(alg_id, resolved_params)`. Every model
call therefore failed with `unexpected keyword argument 'params'`. Direct calls from tests worked, which hid it. Fixed by moving the
decorator back onto the tool function, with a new registry-wide test (`tests/test_tool_registry_signatures.py`) that checks every registered
tool accepts the arguments its schema advertises. Mutation check: with the old ordering the test fails and names the tool. All other tools
pass it. Not hand-retested: re-run RC37-F4's follow-up request after the next build.

## Corrections to the row list

F1, F2, F3, E3 and F5 corrected in `docs/FULL_LIVE_TEST_rc37_ROWS.csv`: Stop instructions moved out of the prompt (the model reads them and
may refuse), and expectations that did not match what the tools return.

## Still open

- Stop on a long running job is not yet proven on real data (E3, F2 inconclusive). Next run: press Stop during a request that takes more than
  10 s, for example a worldwide GDACS or USGS request, or a large grid from `generate_mapping_task_grid`.
- F3 efficiency: 9 calls for a 5-stop route.
- I1, I2 not recorded; F6, F7 not run.
- A1 vs N1: confirm the 10 Amman-area events are outside Jordan.
