# PLAN-007: release rc48 and its hand-test pass

Status: done

## Goal
Put everything merged since rc46 into one installable build (1.17.0-rc48) and one precise hand-test bundle, so a single pass by the owner replaces the never-run rc47 pass and covers wave E1 (PLAN-005), the export routing fixes, the DXF export and the spreadsheet export (PLAN-006). Nothing in rc47 or later has been hand-tested; this plan exists so the first real use of these changes happens in one bounded, recorded run.

## Scope
In: the version bump with every user-facing text that CONTRIBUTING.md section 8 lists; the hand-test bundle (open-issue rows still open, the rc47 fix-targeted rows, a small plain-language sample, and 8 new rows for the rc48 changes); the release workflow run as a pre-release, only on the owner's go-ahead; the result recording after the run.
Out: uploading to plugins.qgis.org (the owner does that); closing any issue without a hand-verified pass or an owner decision; new features (the plot probe, E2b and E2a stay with PLAN-006).

## Acceptance
1. `tests/test_release_docs_in_sync.py`, `tests/test_metadata_parses.py` and the full offline suite pass on the bump; CI is green (offline: yes; CI-live: yes).
2. The bundle is built around the zip the release workflow published (same SHA-256 as the release asset) and holds no `.py` files (`tests/test_test_bundle.py`).
3. The bundle's rows exclude issues already closed (read from the newest `docs/OPEN_ISSUES_STATUS_*.md`), and its 8 new rows each state the exact prompt and the observable result.
4. After the owner's run: every row has a verdict in the status log, failures become GitHub issues, fixes go in as offline-tested changes first. Hand-tested: owner, bundle rows.

## Guard tests
`tests/test_release_docs_in_sync.py`, `tests/test_metadata_parses.py`, `tests/test_test_bundle.py`, `tests/test_tools_reference_in_sync.py`.

## Rollback
Skip the release (do not run the workflow) or release a corrected rc49; the bump is one pull request and can be reverted. A published pre-release can be deleted without affecting `main`.

## Status log
- 2026-10-23: plan written with the bump (branch claude/rc48-prep). Version, metadata changelog, CHANGELOG, README, Help text and counts updated; bundle builder gained the 8 rc48 rows and a fixture for the polygonize row. The release workflow has not been run: it waits for the owner's go-ahead.
- 2026-10-28: status set to done from this plan's own log and the GitHub release list (master list HY-1): the pre-release cartogen-ai-v1.17.0-rc48 exists on GitHub (published 2026-10-23). Hand-test findings continue in PLAN-008.
