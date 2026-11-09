# PLAN-068: The four small defects from the round-3 tester CSV (DEF-31, DEF-32, DEF-35, DEF-36)

Status: in progress

## Goal
Four P3 findings from `4_RESULTS.csv` of round 3: a Gemini bad-key Test that printed raw JSON (A2), a CRITICAL log line when the plugin is unticked mid-request (V1), a JIAF write card that hides the statement and the open validation items (D3), and the undo test changing a shared input file (V9).

## Scope
- DEF-31: `providers/base.py` `format_http_error` treats an HTTP 400 whose body names the reason `API_KEY_INVALID` (what Gemini sends for a bad key) as an authentication failure: same plain sentence, body withheld. Any other 400 keeps the provider's own text.
- DEF-32: `agent_orchestrator.py`: a provider error that arrives after Stop or an unload is a stop (reply "[Agent stopped] Stopped by user.", model_call outcome `cancelled`, logged at INFO). `cli_bridge.py`: a cancelled CLI call logs `cli_bridge_cancelled`. The CLI bridge line was already INFO; only the orchestrator's model_call line was CRITICAL.
- DEF-35: `jiaf_engine.py` `preview_card_text` puts the standing statement, the ids of the open validation items and the empty-severity warning into the preview's `rationale`, which is what the card shows. The payload keeps the full texts.
- DEF-36: row text, no plugin change. V9, E4 and E5 say to work on a copy of the whole test-files folder; the package README tells the tester to run `verify_inputs.py` again at the end and write down any CHANGED file.

## Acceptance
`tests/test_gemini_bad_key_wording.py`, `tests/test_cancelled_call_is_not_critical.py`, `tests/test_jiaf_preview_card_text.py` and `TestRowsThatWriteDataWorkOnACopy` pass; the live JIAF test also asserts the card text; ruff, mypy and the ledger guard pass. Live: A2 with a bad Gemini key (plain sentence), V1 untick mid-request (no CRITICAL line), D3 JIAF write card, and a package run in which `smoke_data.gpkg` is unchanged.

## Guard tests
The tests named above; ledger features `settings-api-provider-test-button`, `jiaf-write-preview-carries-statement-and-blockers`, `full-smoke-package` and the new `cancelled-request-is-a-stop-not-an-error`.

## Rollback
Revert the commit; each change is independent.

## Status log
- 2026-11-09: built, offline tests pass; CI only, none seen live. DEF-32 correction found while building it: the first draft also made ordinary CLI bridge errors CRITICAL, which was wrong because `cli_bridge_error` was INFO already; reverted before commit. Cause of the card gap (DEF-35) is read from the card code path (it shows `rationale` and the code), not seen on screen.
