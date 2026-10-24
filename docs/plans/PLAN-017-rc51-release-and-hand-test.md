# PLAN-017: release rc51 and its hand-test pass

Status: in progress

## Goal
Put the four PLAN-016 changes merged after rc50 (profile re-read at export, export gate and QA following lineage, footer measured in the real font, contour tool descriptions) into one installable pre-release (1.17.0-rc51) and give the owner a bundle whose new rows check them, so the findings of the first rc50 desktop run get a hand verdict.

## Scope
In: the version bump with every user-facing text CONTRIBUTING.md section 8 lists; 3 new rows (P16) in the bundle and the reworded OI-150 row; the release workflow as a pre-release on the owner's go-ahead (given 2026-10-25). The two CI fixes (control script enum, pinned Ubuntu) are not user-facing and are not in the release texts.
Out: uploading to plugins.qgis.org (the owner does that); closing any issue without a hand-verified pass; new features.

## Acceptance
1. `tests/test_release_docs_in_sync.py`, `tests/test_metadata_parses.py`, `tests/test_tools_reference_in_sync.py`, `tests/test_test_bundle.py` and the full offline suite pass; CI green including live QGIS 4.2.2.
2. The bundle is built around the zip the release workflow published (same SHA-256 as the release asset) and holds no `.py` files.
3. After the owner's run: every row has a verdict in the status log, failures become GitHub issues, fixes go in as offline-tested changes first. Hand-tested means the owner, bundle rows only.

## Guard tests
`tests/test_release_docs_in_sync.py`, `tests/test_metadata_parses.py`, `tests/test_test_bundle.py`, `tests/test_tools_reference_in_sync.py`.

## Rollback
Delete the pre-release (it does not affect `main`) or release a corrected rc52; the bump is one pull request and can be reverted.

## Status log
- 2026-10-25: owner said go. Version, metadata changelog, CHANGELOG, README, Help text updated; the bundle builder gained 3 P16 rows and the OI-150 row was reworded in the open-issue sheet. The release workflow has not been run yet.
