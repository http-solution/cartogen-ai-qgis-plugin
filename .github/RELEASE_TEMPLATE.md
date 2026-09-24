<!--
Release notes template for GitHub Releases. GitHub doesn't load this file automatically.
Copy it into the release description, or pass a filled-in copy to
`gh release create <tag> --notes-file <file>`.

Replace every <version> with the version from metadata.txt (e.g. 1.16.0-rc4). It must match
the asset name plugin_upload.py builds (dist/cartogen_ai_v<version>.zip). Keep the install
block at the top. The reason is below. This comment doesn't show in the rendered release.

Why the install block exists: GitHub adds a "Source code (zip)" to every release. Its top-level
folder is <repo>-<tag>, and QGIS uses that folder name as the plugin's module name. The dots
in the version make it unimportable, so QGIS fails with
"ModuleNotFoundError: No module named 'cartogen-ai-qgis-plugin-commercial-plugin-v1'".
This was reported live on QGIS 4.2.2 with v1.16.0-rc4 (docs/BUG_TRACKER.md, Known non-bugs).
The plugin can't catch it because the import fails before any plugin code runs.
-->

> **Install `cartogen_ai_v<version>.zip` (under Assets below), not "Source code (zip)".**
> GitHub's auto-generated source zip puts everything in a folder whose name contains dots,
> so QGIS can't load it and you get
> `ModuleNotFoundError: No module named 'cartogen-ai-qgis-plugin-...'`.
> If you already installed it, delete that folder from your QGIS profile's `python/plugins/`
> directory, then use Plugins → Manage and Install Plugins → Install from ZIP with the asset
> above.

## What's new in <version>

<!-- Summarize this version's CHANGELOG.md / metadata.txt changelog= entry. -->

## Verification

<!-- What was actually run for this release: test suite, ruff, release-zip packaging check,
smoke test (docs/RELEASE_SMOKE_TEST.md run log entry), and what was NOT verified. -->

**Asset sha256:** `<sha256 of cartogen_ai_v<version>.zip>`
