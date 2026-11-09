# PLAN-070: The open defects from earlier tests that could be worked on without a live run (DEF-1, 8, 9, 17 and the second half of 37)

Status: in progress

## Goal
After the round-3 results and the small fixes, nine older defects were still listed as not fixed. This plan takes the ones where evidence in hand allows a real step, and says plainly for each what was and was not done.

## Scope
- **DEF-9 (evidence collector log files empty):** `tools/collect_evidence.py`. The slot `_on_message` called `int(level)`; QGIS 4 (PyQt6) passes the message level as an Enum member, and `int()` of a plain Enum raises TypeError, which Qt drops silently, so nothing was recorded (37 of 41 log files empty in round 3, log_all.txt too). New `_level_number` reads `.value` and never raises; the slot never raises. Cause is inferred from the code and from how QGIS 4 enums behave, not seen in a debugger on the tester's machine; the live test and the next package run confirm it.
- **DEF-37, second half (frame after Zoom Full):** not a plugin defect. With the layers row E3 loads, `smoke_admin` and `smoke_zones` cover 92 % of the DEM's area and `smoke_roads` alone 56 %, so `pick_layout_extent` (frames the vectors only when they fill under half of the project) correctly keeps the whole DEM. Row E3 step 2 now has the tester untick all but `smoke_dem` and add `smoke_points` (27 %), where the frame must follow the points. Pinned by `TestTheSmokeDataExtents` with the real extents.
- **DEF-1 (profile renders empty intermittently):** closed on evidence. Its own condition was "open until one happens and its pictures are read": it happened at main 59e3b76 and the pictures show the curve drawn in a pale colour measured as empty (DEF-38, PLAN-069). The two failures of 2026-10 are very likely the same cause; that is inference, no pictures of them exist.
- **DEF-8 (broad exception handlers):** `tools/broad_except_review.py` classifies all 551 broad handlers; none only passes, continues or breaks. `tests/test_broad_except_review.py` pins that and caps the 219 swallow-and-return handlers. `docs/BROAD_EXCEPT_REVIEW_2026-11-09.md` is the snapshot. Not done: line-by-line review of 209 of the 219.
- **DEF-17 (Gemini model-choice failures):** nothing to build; it needs the Claude-provider rerun of nine rows (OWN-15). Round 3 again used Gemini and a CLI model, so it adds no Claude evidence.

## Acceptance
The new offline tests pass (`test_collect_evidence_log`, `test_broad_except_review`, the extents class); the live test `test_collect_evidence_log_live` passes in CI; ruff, mypy, the ledger guard and the master-list check pass. Live: after the next package run the log files of `snap()` are not empty; row E3 step 2 passes with only the DEM and the points ticked.

## Guard tests
`tests/test_collect_evidence_log.py`, `tests/test_collect_evidence_log_live.py`, `tests/test_layout_extent_pick.py`, `tests/test_broad_except_review.py`; ledger entries `hand-test-v2-bundle-and-evidence-checker` and `layout-frames-the-vectors-after-zoom-full`.

## Rollback
Revert the commit. The collector returns to its old slot; row E3 returns to its old setup text; the review tool and its pin disappear.

## Status log
- 2026-11-09: built; offline tests pass; the live collector test runs in CI only. The DEF-9 cause is probable, not proven.
