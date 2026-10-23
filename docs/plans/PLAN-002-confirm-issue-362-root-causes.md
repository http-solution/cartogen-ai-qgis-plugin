# PLAN-002: confirm the causes behind issue #362

Status: in progress

## Goal
Know why "animate the layer over time" was answered as a how-to, and why "Produce charts linked to maps" built an HTML dashboard, instead of guessing. The third
finding of #362 (the elevation-profile loop) has a code fix; the other two have wording fixes whose effect is unproven.

## Scope
In: capture the tool list the model was offered, the tool calls it made and the final text for those two prompts, using the saved CartogenAI log
(`tools/summarize_usage_log.py`) and the evidence folder. Out: changing router or prompt rules before the trace shows what the model actually did.

## Acceptance
1. Rows A15 to A17 of the rc47 bundle have results with the tool the assistant chose.
2. If A15 or A17 fail, the trace says whether the right tool was offered (router) or offered and not chosen (prompt/model); the fix then goes to the right layer and gets a ledger entry.

## Guard tests
`fragment-guard`, `linked-charts-routing` and `elevation-profile-along-layer` in `docs/FEATURE_LEDGER.json`.

## Rollback
The wording changes are alias and verb-list additions in `tool_router.py` and `task_matcher.py`; revert those lines.

## Status log
- 2026-10-18: wording fixes and `along_layer` merged in rc47 (PRs #364, #365). CI only.
- 2026-10-23: rows A15 to A17 are in the combined bundle; waiting for the run.
