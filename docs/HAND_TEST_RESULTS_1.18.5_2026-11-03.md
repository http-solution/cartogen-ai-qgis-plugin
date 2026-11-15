# Results of the 1.18.5 hand-test run, 2026-11-03 (triage)

Run by an AI agent driving QGIS 4.2 and a terminal on a Windows machine (provider: a Codex CLI client), not by a person. Source: `results/4_RESULTS.csv` and the evidence folders it sent back. Dated record: not edited after the fact; later facts go in a new doc. The agent's verdicts are below with my re-check against the code, which is a reading of the code, not a run.

## Verdicts, after re-check
| Row | Agent said | After re-check |
|---|---|---|
| V3, V5, V6, V7, V8 | Pass | Pass |
| W2, W4, W6, W7, W8, W10 | Pass | Pass (W6/W7: the Allow once dialog and Deny/timeout were observed by the agent, not by a person) |
| W9 | Fail | **Pass for the plugin; the fault was in the package.** The dialog and the lineage both hold `530ce23c...`, the correct fingerprint. `check_workflow_file.py` hashed the document including its own fingerprint field and printed `181c6cbe...`; row W9 pinned that wrong value. Fixed in the package (commit after this doc). The provenance text names the workflow, not the file name; the row asked for the name of the workflow, which it shows. |
| W11 | Fail | **Real defect, D1 below.** |
| W1 | Fail | **Real defect, D2 below.** |
| W3 | Partial | Real, D3 below (misleading text), the rest passes. |
| V4 | Fail | Model chose a how-to instead of the animation tool on the second request. A model-choice result, not a plugin fault; matters for HT-3 (tool-choice evals). Run once; the sheet allows one retry. |
| V1, V2, V5-V9 partials | Partial | Evidence gaps (no attribute-table screenshots, Stop pressed about 50 s late, the CLI client's own "request was cancelled" message when the plugin was unticked mid-request). Not plugin faults on this evidence. V1's untick-during-request outcome needs a rerun with an API provider. |
| W5 | Partial | Facts match the HDX page (licence, modified date, location). Partial only because no screenshot file could be saved. Also: the reply listed 3 formats, the page lists more (incomplete, not wrong). |
| W12 | Skip | Needs a reader who did not write the guide. |

## Defects (read in the code; not yet fixed; each needs a failing test first)
- **D1. Fetch tools skip the egress gate (W11).** The gate runs in `_real_execute_tool` (`agent_orchestrator.py:755`). The 15 `TWO_PHASE_TOOLS` go through `_execute_two_phase_tool` instead, which never calls `_egress_gate_decision`. `fetch_worldpop_population(extent_layer=<a RESTRICTED layer>)` therefore goes out to WorldPop with no card, with the gate in enforce mode (the saved `context.json` shows mode enforce, a non-local client). Whether the gate was meant to cover an outbound request carrying only an extent is a design question; the argument scan treats any named layer as touched, so the code as written intends it. The same path skips the stray-fragment and plan gates.
- **D2. A confirmed step skips the result gate, source record and lineage wrapper (W1).** The Apply button calls `agent._real_execute_tool(..., user_confirmed=True)` directly (`chat_tab_widget.py:255`), not `_execute_tool`, so `result_gate.attach_checks`, the before/after capture and the transaction record do not run. Every write that needs a confirmation card (for example the severity index) ends up without recorded checks. This contradicts the ledger entry `result-gate-hook`, which I wrote as covering all tools.
- **D3. Provenance "QA" section reads the dataset-status record, not the stored result checks (W3, W9).** A layer with `cartogen/checks` is reported as "No status, checks, or history recorded". Misleading rather than wrong, but it contradicts the report next to it.
- **D4. Noise: the result gate records "The output has 3 features" against a layer after `set_layer_sensitivity`** (seen in W11's `layer_properties.json`). A tagging tool is not a result.

## Package faults found by the run (fixed)
`check_workflow_file.py` printed the wrong fingerprint; the bundle did not ship `smoke_image.tif`, so `smoke_start.qgz` opened with unavailable layers (the agent rebuilt each project from `work/inputs`); `snap()` did not dump the `cartogen_ai/*` properties (sensitivity, lineage); a dialog is not captured by `snap()` (a screenshot has to be taken another way); `layout_check.json` was not produced, so STEP A did not run.

## Not established by this run
No person has used any of this. The agent's W7 pass saw the dialog work; whether it reads clearly to a non-technical person is untested. The MCP server froze QGIS when a client blocked on the main thread (agent's report; no evidence file named, not re-checked here).
