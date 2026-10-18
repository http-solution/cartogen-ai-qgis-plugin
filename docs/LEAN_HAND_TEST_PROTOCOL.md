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
