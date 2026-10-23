# PLAN-001: verify the open issues on rc47

Status: in progress

## Goal
Close every open issue that rc47 has fixed, with evidence, and turn the rest into either a decision for the owner or a new, specific defect. Today 28 issues are open
and none was re-run since rc40 (2026-10-14); rc41 to rc47 shipped in between. Issues: the table in `docs/OPEN_ISSUES_STATUS_2026-10-23.md`.

## Scope
In: the 18 open-issue rows plus two set-up rows in Part 1 of the rc47 test bundle (`tools/build_lean_bundle.py`), chosen automatically from the open-issue table.
Out: issues closed with evidence at rc40 (their rows are not in the bundle); #305 (optional); umbrellas #72, #169, #233 (they close when their children do).

## Acceptance
1. Every Part 1 row has a result and the tool the assistant chose. Offline checks cannot decide this; it is a hand test.
2. Row Pass: the issue gets a comment with the row id and evidence, then is closed. Row Fail/Partial: a new issue states the observed behaviour; the old issue gets a pointer. Row Skip: the reason is written in the result and the row goes to the next bundle.
3. `docs/OPEN_ISSUES_STATUS_<date>.md` is regenerated from GitHub after each batch (it is the bundle's source of truth for what is open).

## Guard tests
`tests/test_test_bundle.py` (bundle only contains rows of open issues); fixes that come out of Fail rows add their own ledger entries.

## Rollback
Not applicable (test campaign).

## Status log
- 2026-10-23: plan created with the combined bundle (PR for this plan). Nothing run yet.
