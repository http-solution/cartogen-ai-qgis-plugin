# PLAN-018: release rc52 and its hand-test pass

Status: in progress

## Goal
Put the owner's disclaimer wording (merged after rc51, PR 424) into one installable pre-release (1.17.0-rc52) with a hand-test row that checks it on a real page, so the longer footer and the Help section get a human verdict.

## Scope
In: the version bump with every user-facing text CONTRIBUTING.md section 8 lists; one new row (P17) in the bundle on top of the rc50 and rc51 rows, which the owner has not run yet; the release workflow as a pre-release on the owner's go-ahead (given 2026-10-25). The CI changes since rc51 (runner pin, Node 24 actions, control-script enum) and the issue closures are not user-facing and are not in the release texts.
Out: uploading to plugins.qgis.org (the owner does that); closing any issue without a hand-verified pass; new features.

## Acceptance
1. `tests/test_release_docs_in_sync.py`, `tests/test_metadata_parses.py`, `tests/test_tools_reference_in_sync.py`, `tests/test_test_bundle.py` and the full offline suite pass; CI green including live QGIS 4.2.2.
2. The bundle is built around the zip the release workflow published (same SHA-256 as the release asset) and holds no `.py` files.
3. After the owner's run: every row has a verdict in the status log, failures become GitHub issues, fixes go in as offline-tested changes first. Hand-tested means the owner, bundle rows only.

## Guard tests
`tests/test_release_docs_in_sync.py`, `tests/test_metadata_parses.py`, `tests/test_test_bundle.py`, `tests/test_tools_reference_in_sync.py`, `tests/test_disclaimer_text.py`.

## Rollback
Delete the pre-release (it does not affect `main`) or release a corrected rc53; the bump is one pull request and can be reverted.

## Status log
- 2026-10-25: owner said go. Version, metadata changelog, CHANGELOG, README, Help text updated; the bundle builder gained the P17 row. The release workflow has not been run yet.
