# PLAN-060: Work through the master-list rows that are "Not started" (AR-3, AR-4, DEF-1, HU-3, HU-5, HY-2, HY-5, PR-R rows)

Status: in progress

## Goal
The owner asked for the rows with status "Not started" to be worked in id order. Of 27, 15 wait on an owner decision, a live run or a dependency and are NOT started here (each says what it waits on); the rest are workable now and are done one at a time, each with its own measurement or test, its own ledger entry where behaviour changes, and its own line below. A row is never marked finished on a guess.

## Scope
- In scope, in id order: AR-3, AR-4, DEF-1, HU-3, HU-5, HY-2, HY-5, then the unblocked roadmap releases PR-R3, PR-R8, PR-R9, PR-R10, PR-R11 as far as each can be done and verified honestly.
- Out of scope until their dependency moves: HT-3, HT-4, HT-5, HU-4 (RM-A in progress), HY-4 (deleting remote branches needs the owner's confirmation), LEAD-5, LEAD-6, LEAD-7, PR-R1, PR-R2, PR-R4, PR-R5, PR-R6, PR-R7, PR-R12.

## Acceptance
Per row, stated in its status line: what was measured or tested, whether it is CI only, and what a person must still see. `python tools/master_list.py check` says "in step" after every change.

## Guard tests
`tests/test_task_matcher_length_fairness.py` (AR-3), `tests/test_unsupervised_background.py` and the live case in `tests/test_raster_numpy_live.py` (AR-4); ledger entry `unsupervised-classification-in-background`. More are added below as rows land.

## Rollback
Each row is its own commit; revert it. AR-4 is one `run_callable` call in `unsupervised_classification` and a constant (`_BACKGROUND_MIN_CELLS`).

## Status log
- 2026-11-05: AR-3 measured, not changed. Asking every one of the 792 tasks' own titles for its task: 613 find it, 165 find none ("too short to be a request": the fragment guard, by design), 13 lose to a task whose keyword set is identical, 1 loses to a task with fewer strong keywords, none to one with more; and only 2 of the 385 plain prompts still get a task directive, both right (issue 380's figure). So no length bias is measurable on the register's own wording; the live case behind the note (2026-09-19) was fixed by a targeted re-rank and the shared formula was deliberately left alone (wide blast radius). Pinned by `test_task_matcher_length_fairness.py`. Changing the scoring would be a routing change that needs the owner's go; recommendation: close AR-3 as "no measurable bias". Side finding: a 3 or 4 word task title with no action word from `_ACTION_WORDS` (for example "Model walking access") is treated as a fragment and gets no task directive; harmless (the message goes as typed) and left as is.
- 2026-11-05: AR-4 half stale, half built. The chunked k-means shipped on 2026-10-11 (#222; the tracker line saying "not built" is stale, for HY-2). The remaining half, GUI-thread offloading, is done for this tool: a raster of 250,000 cells or more is classified on a worker thread via `run_callable` (QGIS stays responsive, Stop works, the worker gets the source path and never a layer). Offline tests fail on the old code; a live test runs a 600 x 600 raster through real GDAL (CI only, first execution). Not shown by any run: that the window stays responsive on a very large raster.
- 2026-11-05: DEF-1 half done, cause not found. Already there before today: the render test prints the profile PNG into the log as base64, renders five times and compares the ink counts, and the tool reports a `render_check`. What the row asked for and was missing: the picture kept as a file. The live render tests now save their PNGs through `tests/_render_artifacts.py` into `$CARTOGEN_LIVE_ARTIFACTS` and the live job uploads that folder as the artifact `live-render-pngs` (`if: always()`, `continue-on-error`, nothing uploaded when nothing was written). No recurrence to learn from: the live job ran about ten times on 2026-11-04 with no empty render, and a QGIS 3.34 reproduction was not comparable. The next empty render will leave its pictures. The row stays open until one does and the cause is read from it.

