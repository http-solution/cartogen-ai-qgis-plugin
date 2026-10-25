# PLAN-018: version 1.18.0 and the precise hand-test file

Status: in progress

## Goal
On the owner's instruction (2026-10-25) build two files from `main` once CI is green: the plugin zip with the version bumped to 1.18.0, and a precise hand-test file that holds only the points that need a person to look. This replaces the rc52 plan: the disclaimer wording and everything since rc51 go into 1.18.0 directly, no rc52 was published.

## Scope
In: the version bump to 1.18.0 with every user-facing text CONTRIBUTING.md section 8 lists (a cumulative what's-new since 1.16.3, the last stable build); a `--precise` mode of `tools/build_lean_bundle.py`; the two zip files built locally.
Out: publishing a GitHub release or uploading to plugins.qgis.org (the owner does that; releases only on the owner's say-so); closing any issue without a hand-verified pass.

## Decision recorded
Earlier stable builds (1.16.1) were exactly an rc that had passed its hand test. 1.18.0 is not: it is CI-checked, with only parts of rc44 to rc46, rc48 and 20 rows of rc50 hand-tested. The owner asked for 1.18.0 anyway; every release text says so plainly, and the hand-test file is part of the delivery. Recommended: upload to plugins.qgis.org as experimental, or hold the upload until the precise hand test has results.

## Acceptance
1. `tests/test_release_docs_in_sync.py`, `tests/test_metadata_parses.py`, `tests/test_tools_reference_in_sync.py`, `tests/test_test_bundle.py` and the full offline suite pass; CI is green including live QGIS 4.2.2.
2. The plugin zip built by `plugin_upload.py` is version 1.18.0; the precise test file embeds that zip with its SHA-256 and holds no `.py` files.
3. The precise file contains the set-up rows, the rows P8 to P17 and the open-issue rows of issues still open, and nothing else. After the owner's run: every row gets a verdict in the status log, failures become issues.

## Guard tests
`tests/test_release_docs_in_sync.py`, `tests/test_metadata_parses.py`, `tests/test_test_bundle.py`, `tests/test_tools_reference_in_sync.py`, `tests/test_disclaimer_text.py`.

## Rollback
The bump is one pull request and can be reverted; nothing is published.

## Status log
- 2026-10-25: owner asked for 1.18.0 and a precise test file. Texts, versions and the `--precise` mode written; CI not yet run.
