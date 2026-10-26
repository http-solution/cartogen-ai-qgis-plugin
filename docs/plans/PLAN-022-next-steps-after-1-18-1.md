# PLAN-022: next steps after 1.18.1, from a review of every list, plan, tracker and task

Status: planned

## Goal
On 2026-10-26, with 1.18.1 released and the owner's hand run not yet back, review every list the project keeps (the session task list, the 21 plans, the feature ledger, the two trackers, the open issues, the CI configuration) and say what is really still to do, in what order, who does it, and what is deliberately not being done. After this plan: nothing is open without an owner, a next action and a proof; lists that disagree with what happened are corrected; and the work that needs no hand test is separated from the work that is waiting for one.

## Scope
In: the review findings below; the work packages N1 to N6; the decisions only the owner can take. Out: new features, a release other than a patch that fixes what the hand run finds, and anything that needs the owner's credentials (HX4) or a real QGIS profile (done only through the hand-test bundle).

## What the review found
- **Session task list (89 entries):** 84 done, 5 pending. Three of the pending ones (Smoke 16 to 18, from the rc10 smoke round) are superseded by the v2 hand test and are removed; two are owner tasks that stay (JIAF validation blockers, HX4 credentialed integrations).
- **Plans (21 before this one):** 5 done (004, 010, 011, 012, 019), 16 not. Of the 16, fourteen carry a status their own log no longer matches: PLAN-001, 002, 003, 005 to 009, 013 to 015, 017 and 018 say "in progress" for releases (rc48 to 1.18.0) that were built, tested and published or replaced; PLAN-016 says "planned" although its items 1, 2, 4 and 5 shipped in rc51. The other two, PLAN-020 and PLAN-021, are correctly `planned` (they wait for the owner's rows). The rule in `docs/plans/README.md` is that a plan is done only when its acceptance is met and the log says what was hand-verified, so most of these cannot honestly be `done`; each needs a one-line log entry saying what is still unproven.
- **Feature ledger (83 entries):** 66 carry a hand-verified statement, 5 say "partly", 12 say "not verified". All 12 are this week's work (legend fit, footer check numbers, layout name, layout check script, v2 bundle and checker, one log tab, loaded DEM, repeated listing, undo of a new field, point layer kept, coverage chart, items say whether they drew). None names the hand row that would verify it.
- **Issues:** 2 open (#362, #380), both waiting for hand rows V3 to V8. 10 closed on 2026-10-25 under the owner's fix-or-close decision (#148, #130, #169, #223, #224, #97, #120, #425, #72, #379), several on CI evidence only; each comment says which.
- **Trackers:** `docs/IMPLEMENTATION_TRACKER.md` has stale open items (section 1.23 still says A16 is not live-tested and A18 needs the upgrade gate; both now have tests), duplicated section numbers (1.19 to 1.24 each appear twice) and a long 1.17 list whose items are closed. `docs/BUG_TRACKER.md` has one `open` row (BUG-2026-09-25-3, `maxspeed` set on 0.9 percent of roads) and four `fixed-unverified`.
- **CI and release:** `windows-latest` is unpinned; `release.yml` uses `upload-artifact@v4`, not checked against the Node 20 notice; the release workflow writes a fixed body, so a release cannot say "not hand-tested" unless someone edits it by hand (this session cannot edit releases); the README test count is typed by hand.
- **Not done on purpose and said so:** undo of `rename_field` and `delete_field`; the temporary-layer note for tools other than `add_point_layer` (incident, hazard and event layers); the clean-profile install test (tracker 1.10) is not a row of the v2 sheet; I4 (animate answered as a how-to) and I9 (an HTML dashboard instead of a layout chart) are model answers that CI cannot reproduce.

## Work packages (order of work)

### N0: waiting on the owner (nothing here can be done for them)
Install 1.18.1, run `layout_check_script.py` once, do the nine rows V1 to V9, return the layout-check folder, `4_RESULTS.csv` and `cartogen_evidence`; paste the "CI-checked, not hand-tested" note into the release; unpublish the old Pages site; decide on the plugins.qgis.org upload; JIAF validation blockers; HX4 credentials. I act on the returned files within the same session: `python tools/check_evidence.py <folder>`, then close #362 and #380 or open a fix.

### N1: plan and task hygiene (docs only, no owner needed)
Read each of the 14 stale plans' logs and set its status to what they support (`done` only where acceptance is met; otherwise keep `in progress` with a new last line that names what remains and where it is tracked), correct PLAN-016, remove the three superseded tasks, and add a "state of the lists" line to `docs/plans/README.md`. Proof: `tests/test_plans.py`; a new check that every plan marked `done` has a log line containing "hand" or "CI only".

### N2: ledger traceability
Each of the 12 "not verified" ledger entries gets the id of the hand row that would verify it (or "CI only by decision"), kept in a `hand_row` field, and a test fails when a new entry says "not verified" with neither. Proof: `tests/test_feature_ledger.py`.

### N3: tracker sweep
Correct `IMPLEMENTATION_TRACKER.md` sections 1.17 and 1.23 to the present state, renumber the duplicates, move closed items to a dated "closed" list, and decide with the owner what to do with BUG-2026-09-25-3 (a measured data limit of the Jordan extract, not a code fault). Docs only.

### N4: CI and release hygiene
Pin the Windows runner (`windows-2025`, after checking the name the Actions docs give), check `upload-artifact@v4` against the Node notice and move to the current major if there is one, and give `release.yml` an optional `status_note` input that is written into the release body, so a release says what was and was not hand-tested without anyone editing it. Make the README test count come from a check, not from memory. Proof: `tests/test_workflow_runners_pinned.py` and the workflow's own run.

### N5: what the hand run decides (starts when N0 returns)
For each failed or partial row: reproduce from the evidence folder, write the fix with a CI test, and put it in a 1.18.2 patch with the same release texts. Likely candidates, none confirmed: the footer slack on the owner's fonts, the legend note wording, the log tab text, V3 to V8 model answers. Not started before the rows are back.

### N6: owner decisions that change the plan
(1) Extend the temporary-layer note to incident, hazard and event layers (small, mechanical). (2) Undo for `rename_field` and `delete_field` (a design question: renaming is reversible, deleting a filled column is not). (3) Add a clean-profile install row to the next bundle (costs the owner one more row). (4) Stay with a stable 1.18.1 release that is not hand-tested, or mark it a pre-release until the rows pass. (5) Whether to spend time on the architecture items of tracker sections 1.5 to 1.8 (plan-then-validate-then-execute, project folder architecture, task matcher normalisation), which are design work with no hand-test dependency.

## Acceptance
1. N1 to N4 merged with their tests green, in pull requests that each revert alone; each list in "What the review found" agrees with the facts it describes.
2. After N0, every row has a verdict from `check_evidence.py` or a stated decision, and #362 and #380 are closed with the evidence or have a fix in flight.
3. Anything built is labelled CI only or hand-verified in its ledger entry and plan log; nothing is called done on CI evidence alone unless the owner decided that in writing.

## Guard tests
`tests/test_plans.py` (extended), `tests/test_feature_ledger.py` (extended), `tests/test_workflow_runners_pinned.py`. Named as each package is written.

## Rollback
One pull request per package; each reverts alone. N1 to N3 change documents only; N4 changes workflow files and can be reverted to the pinned versions it replaced.

## Status log
- 2026-10-26: plan written from a review of the task list, 21 plans, the 83-entry ledger, both trackers, the open issues and the workflows. Nothing built yet. N0 waits for the owner; N1 to N4 can start now; N5 and N6 wait for N0 and for decisions.
