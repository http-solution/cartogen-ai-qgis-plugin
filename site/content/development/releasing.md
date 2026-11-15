---
description: The version-bump checklist, how the release zip is built and published, and the checks that keep release text in sync.
---
Releases are cut by pull request. A version bump touches several user-facing texts that must agree, and a test fails until they do.

## The checklist (every version bump)

When `version=` in `metadata.txt` changes, update **all** of these in the same change. `tests/test_release_docs_in_sync.py` fails until they agree.

1. **`metadata.txt`**: prepend a `changelog=` block for the new version (never edit older blocks). **Never write the percent character anywhere in this file; write "percent".** plugins.qgis.org parses it with Python's `ConfigParser` and rejects the upload otherwise (it refused rc24 for exactly this; `tests/test_metadata_parses.py` and `plugin_upload.py` both check).
2. **`CHANGELOG.md`**: a new row in the "Recent releases" table and a new `## [version]` section with its `<a id="v…">` anchor.
3. **`src/cartogen_ai/core/release_notes.py`**: `WHATS_NEW_VERSION`, `NEW_MARK_VERSIONS`, `WHATS_NEW_ITEMS` (shown in the plugin's Help dialog), and any new tool in `HUMANITARIAN_WORKFLOWS` with its `TOOL_NEW_IN` entry.
4. **`README.md`**: the version line, the status line, a new "What's new" section (keep the previous one below it), and the humanitarian table, regenerated from `release_notes.render_readme_table()`.
5. **`pyproject.toml`**: the version string.
6. **Counts**: the tool count (README and `docs/TOOLS_REFERENCE.md`, via `python docs/generate_tools_reference.py`) and task and section counts (`docs/USER_GUIDE.md`); the Help dialog reads them live.
7. **Say plainly what was and was not verified** (hand-tested or CI only), then build the zip with `python plugin_upload.py`.

This documentation site reads the version, tool count and task count from the repository at build time, so it needs no edit for a release.

## Building the zip

`python plugin_upload.py` writes `dist/cartogen_ai_v<version>.zip` (and a root `cartogen_ai.zip`). The top-level folder is **`cartogen_ai_plugin`**, never `cartogen_ai` or the GitHub-generated `<repo>-<tag>`. It excludes tests, tools, the site, service prototype, hidden files, binary documents and sample data, and ships only the user-facing documents. The zip must be at most 25 MB. See [Repository layout](@development/layout) for the reasons.

## Publishing

`.github/workflows/release.yml` is **manual** (`workflow_dispatch`): publishing is a deliberate act, never a side effect of a push.

| Input | Meaning |
|---|---|
| `ref` | The commit to build from: use the **merged** SHA on `main`, not the branch tip |
| `tag` | `cartogen-ai-v<version>`, for example `cartogen-ai-v1.16.0-rc39` |
| `prerelease` | `true` for release candidates |
| `draft` | `true` (default) creates a draft: nobody is emailed until you publish it by hand from the Releases page |

It builds the zip with `plugin_upload.py`, checks it, and attaches `cartogen_ai_v<version>.zip` and `SHA256.txt` to a GitHub release. **The same file** is the one to upload to plugins.qgis.org, so the directory and GitHub carry one checksum.

Tag naming: new tags use `cartogen-ai-v<version>`. Older tags used a `commercial-plugin-` prefix that suggested a proprietary licence the project never had; they are left untouched because published releases reference them.

## Sequence used for a release candidate

1. Branch from `main`, make the change, bump the version (checklist above), run the offline suite, `ruff`, `mypy` and the release-docs test.
2. Open a pull request; wait for **all** CI jobs to pass.
3. Squash-merge. 4. Run the release workflow with the merged SHA. 5. Confirm the asset and its checksum. 6. For the plugin directory, upload the same zip with your plugins.qgis.org login, read the scan report, and fix anything it flags.

## Stable release

A release candidate becomes `1.16.0` only after the gates in [Status and open work](@project/status): a hand-tested pass of the live test pack, the clean-profile and upgrade checks, the directory scan, and the open issues closed on hand-verified evidence.
