# PLAN-015: release rc50 and its hand-test pass

Status: in progress

## Goal
Put everything merged since rc49 (PLAN-014: credits, No data class, layout checks, page sizes, export presets, map profiles with branding, sign-off and COD wording, the footer fit) into one installable pre-release (1.17.0-rc50) and add its hand-test rows to the bundle, so one pass by the owner replaces the CI-only state of those changes.

## Scope
In: the version bump with every user-facing text CONTRIBUTING.md section 8 lists; 7 new rows (P14) and one new fixture layer (`districts_gaps`) in the hand-test bundle, on top of the rc49 rows, which the owner has not run yet; the release workflow as a pre-release on the owner's go-ahead (given 2026-10-24).
Out: uploading to plugins.qgis.org (the owner does that); closing any issue; new features.

## Acceptance
1. `tests/test_release_docs_in_sync.py`, `tests/test_metadata_parses.py`, `tests/test_tools_reference_in_sync.py`, `tests/test_test_bundle.py` and the full offline suite pass; CI is green including live QGIS 4.2.2.
2. The bundle is built around the zip the release workflow published (same SHA-256 as the release asset) and holds no `.py` files.
3. After the owner's run: every row has a verdict in the status log, failures become GitHub issues, fixes go in as offline-tested changes first. Hand-tested means the owner, bundle rows only.

## Guard tests
`tests/test_release_docs_in_sync.py`, `tests/test_metadata_parses.py`, `tests/test_test_bundle.py`, `tests/test_tools_reference_in_sync.py`.

## Rollback
Delete the pre-release (it does not affect `main`) or release a corrected rc51; the bump is one pull request and can be reverted.

## Status log
- 2026-10-24: owner said go. Version, metadata changelog, CHANGELOG, README, Help text and counts updated (tools unchanged at 296; 4,908 offline tests, 723 skipped); the bundle builder gained 7 P14 rows and the `districts_gaps` fixture. The release workflow has not been run yet.
- 2026-10-24: merged as #411 (c2986af), all CI green including live QGIS 4.2.2. Release workflow published the pre-release `cartogen-ai-v1.17.0-rc50`; zip SHA-256 4bd62fdb09fb294d9da2bf68cccffde557e936137208457a45a6d80008a2eeaa, downloaded and checked equal to the published SHA256.txt and the asset digest. Bundle `dist/cartogen_ai_test_bundle_1.17.0-rc50.zip` built around exactly that zip: 87 rows (17 open-issue, 29 release incl. the 7 new P14 rows, 41 plain-language), no .py files. Waiting for the owner's run and `4_RESULTS.csv`; the rc49 rows are still unrun and are in this bundle too.
