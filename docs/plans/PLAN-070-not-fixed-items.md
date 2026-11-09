# PLAN-070: The open defects from earlier tests that could be worked on without a live run (DEF-1, 8, 9, 17 and the second half of 37)

Status: in progress

## Goal
After the round-3 results and the small fixes, nine older defects were still listed as not fixed. This plan takes the ones where evidence in hand allows a real step, and says plainly for each what was and was not done.

## Scope
- **DEF-9 (evidence collector log files empty):** `tools/collect_evidence.py`. The slot `_on_message` called `int(level)`; QGIS 4 (PyQt6) passes the message level as an Enum member, and `int()` of a plain Enum raises TypeError, which Qt drops silently, so nothing was recorded (37 of 41 log files empty in round 3, log_all.txt too). New `_level_number` reads `.value` and never raises; the slot never raises. That was a real fault but, as the first live run showed, not the whole one: a real `QgsMessageLog.logMessage` reached the collector's connection not at all (CI 42639289496, QGIS 4.2.2, `{}` lines). So `setup()` now connects every signal form that exists and `_on_message` drops the resulting duplicates, and a live test prints which forms deliver (the `COLLECTORFORMS` lines in the CI output). Which single form is right on QGIS 4 is read from that output, not guessed.
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
- 2026-11-09: built; offline tests pass. First live CI run: the collector's old connection received no line from a real log message, so the int(level) fix alone was insufficient. Second build: connect every form, dedupe, and a live probe of the forms. The DEF-9 cause is partly known (int(level) on an enum; a connection form that delivers nothing); not confirmed on the tester's QGIS 4.2.3.
- 2026-11-09 (later): the second live run (CI 42640715853) again recorded nothing through any signal form, and the probe I had written passed only on the bool form, so it proved nothing. The collector now reads the plugin's own log lines from a small in-memory buffer in `core/logger.py` (`recent_lines`, 2000 lines, redacted like the lines sent to QGIS) and writes a sentence into an empty log file instead of leaving it empty. The signal forms stay connected as a bonus; which of them deliver is written to `collector_signal_forms.txt` in the CI artifact, informational only. This changes the plugin (logger), not only a tool: it adds a bounded in-memory copy of lines already logged.
