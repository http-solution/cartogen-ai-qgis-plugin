# PLAN-013: release rc49 and its hand-test pass

Status: in progress

## Goal
Put everything merged since rc48 (PLAN-008 to PLAN-012 and the self-audit follow-ups) into one installable build (1.17.0-rc49) and one precise hand-test bundle, so a single pass by the owner replaces the unverified CI-only state of those changes. It also carries the evidence rows for the two rc48 findings that could not be reproduced (OI-128, OI-150).

## Scope
In: the version bump with every user-facing text that CONTRIBUTING.md section 8 lists; the hand-test bundle (open-issue rows still open, rc49 rows for the changes below, a small plain-language sample); the release workflow run as a pre-release, on the owner's go-ahead (given 2026-10-24).
Out: uploading to plugins.qgis.org (the owner does that); closing any issue without a hand-verified pass or an owner decision; new features.

What rc49 carries (all CI only): routed reachability totals (OI-148), tidy asks first and normalises sources (OI-120), script failure honesty (145/146), dashboard internet note (84), admin zoom labels (127), layout frame after Zoom Full (129), Memory dialog wording (95), layout charts and profile placement and axes, plain requests vs the task library, Processing run guards, evidence `context.json`; the audit fixes (cross-CRS admin snap, MultiPoint, coverage report, QA unknown, replace order, persist warning, GeoJSON name, temp notes); export gates (confirm card, publication reason, atlas) and the footer sources and disclaimer.

## Acceptance
1. `tests/test_release_docs_in_sync.py`, `tests/test_metadata_parses.py`, `tests/test_tools_reference_in_sync.py`, `tests/test_test_bundle.py` and the full offline suite pass; CI is green incl. live QGIS 4.2.2.
2. The bundle is built around the zip the release workflow published (same SHA-256 as the release asset) and holds no `.py` files.
3. The bundle's open-issue rows are those of issues still open in the newest `docs/OPEN_ISSUES_STATUS_*.md`; its 9 rc49 rows each state the exact prompt and the observable result.
4. After the owner's run: every row has a verdict in the status log, failures become GitHub issues, fixes go in as offline-tested changes first. Hand-tested: owner, bundle rows only.

## Guard tests
`tests/test_release_docs_in_sync.py`, `tests/test_metadata_parses.py`, `tests/test_test_bundle.py`, `tests/test_tools_reference_in_sync.py`.

## Rollback
Delete the pre-release (it does not affect `main`) or release a corrected rc50; the bump is one pull request and can be reverted.

## Status log
- 2026-10-24: owner said go. Version, metadata changelog, CHANGELOG, README, Help text and counts updated (tools unchanged at 296; 4,803 offline tests, 689 skipped); bundle builder gained 9 rc49 rows and a MultiPoint fixture. The release workflow has not been run yet.
