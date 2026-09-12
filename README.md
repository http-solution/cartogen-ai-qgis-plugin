# Cartogen AI

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="branding/cartogen-lockup-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="branding/cartogen-lockup-light.svg">
  <img src="branding/cartogen-lockup-light.svg" alt="Cartogen AI" width="440">
</picture>

<p align="center">
  <strong>Spatial AI for QGIS — plan it, run it, inspect the work.</strong><br>
  Describe a mapping or analysis task in plain language and Cartogen AI turns it into
  visible, real operations against your open QGIS project.
</p>

<p align="center">
  <a href="https://github.com/cartogenai-glitch/CARTOGEN-AI/actions/workflows/tests.yml"><img src="https://github.com/cartogenai-glitch/CARTOGEN-AI/actions/workflows/tests.yml/badge.svg" alt="Tests"></a>
  <a href="https://github.com/cartogenai-glitch/CARTOGEN-AI/releases"><img src="https://img.shields.io/github/v/release/cartogenai-glitch/CARTOGEN-AI?display_name=tag&include_prereleases" alt="Release"></a>
  <a href="https://github.com/cartogenai-glitch/CARTOGEN-AI/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-GPL--2.0-blue.svg" alt="GPL-2.0 license"></a>
  <a href="https://github.com/cartogenai-glitch/CARTOGEN-AI/issues"><img src="https://img.shields.io/github/issues/cartogenai-glitch/CARTOGEN-AI" alt="Issues"></a>
</p>

**Community edition · Version 1.11.0 · GNU GPL v2 · QGIS 3.0–4.99**

Cartogen AI is built for GIS analysts, humanitarian teams, researchers, and anyone who
needs to move from a question to a reproducible spatial result without leaving QGIS.
The agent exposes its plan, tool calls, progress, and errors instead of returning a
black-box answer.

> **Project status:** active Community edition. The automated suite is green, while the
> full pre-release checklist still requires verification in an interactive QGIS session.
> See [the release smoke test](docs/RELEASE_SMOKE_TEST.md) and
> [the implementation tracker](docs/IMPLEMENTATION_TRACKER.md) for current status.

> This repository is the single public Cartogen AI Community codebase. See the
> [changelog](CHANGELOG.md) for the consolidation history.

<details>
<summary><strong>Table of contents</strong></summary>

- [What it does](#what-it-does)
- [Editions](#editions)
- [Installation](#installation)
- [Quick start](#quick-start)
- [Documentation](#documentation)
  - [Getting started](#getting-started)
  - [Security & compliance](#security--compliance)
  - [Engineering & process](#engineering--process)
  - [Product & humanitarian standards](#product--humanitarian-standards)
  - [Roadmap, specs & dated reviews (archive)](#roadmap-specs--dated-reviews-archive)
  - [Project reference](#project-reference)
- [Contributing](#contributing)
- [Development](#development)
- [Support](#support)

</details>

<p align="center">
  <img src="docs/images/dock-panel.png" alt="Cartogen AI dock panel — Chat and Activity tabs, with the provider switcher" width="440">
</p>

## What it does

- **Multi-provider**: OpenRouter, Google Gemini, OpenAI, Anthropic Claude, or a local
  Ollama server — switch anytime, bring your own API key (OpenRouter has a free tier;
  Ollama is free and fully local).
- **169 tools** covering vector and raster geoprocessing, styling and labeling, print
  layouts, exports, humanitarian data (HDX / OpenStreetMap / geoBoundaries / building
  footprints), satellite imagery search, database queries, trend forecasting, humanitarian
  severity/needs indexing (JIAF/INFORM-style composite scoring for fund-allocation
  prioritization), 3W/4W operational-presence analysis and coverage-gap detection, live hazard
  monitoring (NASA FIRMS active fires, NASA EONET natural events, GDACS disaster alerts) with
  recurring-workflow tracking, an interactive HTML situation dashboard export with per-layer
  freshness badges for non-QGIS audiences, geoprivacy obfuscation for sensitive point data (Do
  No Harm), and workflow presets — see
  [docs/TOOLS_REFERENCE.md](docs/TOOLS_REFERENCE.md) for the full, auto-generated list.
- **Guided by a 791-task Humanitarian Mapping Task Register** (v1.4.3–1.4.4): a request that
  matches a task shows the exact prompt about to be sent, with the reasoning behind it, before
  it's sent; stops to ask only when a detail genuinely can't be safely guessed (e.g. hazard or
  facility type); and checks the response against what the task promised, with one automatic,
  disclosed follow-up if a promised dashboard, export, or chart didn't actually get produced.
  See [docs/USER_GUIDE.md](docs/USER_GUIDE.md).
- **Task Manager**: multi-step requests get a visible plan with progress tracking,
  retry, and edit-and-resend for failed steps.
- **File attachments**: PDF, Word, CSV, Excel, and images. CSV/Excel attachments can be
  loaded as full real layers (not just a preview) with automatic point-geometry
  detection for coordinate columns.
- **Native web search grounding** on Gemini and OpenAI, with automatic model fallback
  if a configured model is retired.
- **Stop button**: cancel an in-progress request instead of waiting it out.
- **Security-conscious by design** — see [SECURITY.md](SECURITY.md) for the full
  threat model and what was actually adversarially tested (not just intentions):
  a restricted execution sandbox for model-generated PyQGIS scripts, fail-closed
  read-only SQL enforcement, an SSRF guard on fetched URLs, and a destructive-action
  confirmation gate the model cannot self-approve.

## Editions

This release is the **Community edition** — free, GPL v2, everything in this README and in
[docs/TOOLS_REFERENCE.md](docs/TOOLS_REFERENCE.md), no account or license key. It runs fully offline
via a local Ollama server, or with a cloud provider using your own API key.

A Professional (hosted cloud-model gateway) and Enterprise (RBAC/SSO, private deployment, M365
integration) tier are planned but **not yet built** — nothing in this repository is tier-gated today.
See [docs/PRODUCT_TIERS.md](docs/PRODUCT_TIERS.md) for the honest breakdown of what's shipped versus
roadmap for each.

## Installation

**From the release zip** (recommended):
1. In QGIS: `Plugins` → `Manage and Install Plugins…` → `Install from ZIP`.
2. Select `cartogen_ai.zip` (or the versioned archive under `dist/`).
3. Enable the plugin if it isn't auto-enabled.

**From source** (development):
1. Copy this repository into your QGIS profile's plugin folder, e.g.
   `%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\cartogen_ai` on Windows.
2. Restart QGIS, or use the Plugin Reloader plugin.

This build is not currently published on the public QGIS plugin repository
(plugins.qgis.org); install it via one of the methods above.

### Optional dependencies

Document parsing (PDF/Word/Excel attachments), `search_web`, chart/dashboard generation, and PDF
table extraction need a few extra Python packages, listed in [requirements.txt](requirements.txt).
Install them either:
- through the bundled `qpip` plugin dependency (QGIS will offer to install them), or
- manually in the OSGeo4W Shell: `python -m pip install -r requirements.txt`.

Everything else works without them — a missing optional package degrades that one
feature with a clear error message rather than breaking the plugin.

**Install optional dependencies with QGIS fully closed, not while it's running.** A package install
that replaces a module QGIS already has loaded — most likely with the heavier
`extract_features_from_imagery` dependency group, which shares `jinja2`/`markupsafe` with `folium` —
can fail on Windows with `PermissionError: [WinError 5] Access is denied` on a locked `.pyd` file.
This is a Windows file-lock issue, not a plugin bug, and no code running inside the same locked
process can work around it. Close QGIS completely, install (via `qpip` on next launch, or the
OSGeo4W Shell), then reopen QGIS.

## Quick start

1. Open the **Cartogen AI** panel (toolbar icon or `Plugins` menu).
2. Click the ⚙ settings icon, pick a provider, and paste an API key (or point at a
   local Ollama server — no key needed). Get a key from the provider you picked:
   - OpenRouter (has a genuinely free tier): https://openrouter.ai/keys
   - Google Gemini: https://aistudio.google.com/apikey
   - OpenAI: https://platform.openai.com/api-keys
   - Anthropic Claude: https://console.anthropic.com/settings/keys
   - Ollama needs no key — just a local server endpoint URL.
3. Type a request, e.g. *"List all layers in the project"* or *"Calculate the area for
   the active layer"*. See the in-app **Help** tab for more examples, or
   [docs/USER_GUIDE.md](docs/USER_GUIDE.md) for a full walkthrough.

## Documentation

`docs/` also has its own [index](docs/README.md) with the same grouping, for anyone browsing
the folder directly on GitHub.

### Getting started

| Doc | Covers |
|---|---|
| [docs/USER_GUIDE.md](docs/USER_GUIDE.md) | Chat, Task Manager, memory, file attachments, settings, live hazard monitoring — with screenshots |
| [docs/TOOLS_REFERENCE.md](docs/TOOLS_REFERENCE.md) | All 169 tools, auto-generated from the live registry |

### Security & compliance

| Doc | Covers |
|---|---|
| [SECURITY.md](SECURITY.md) | Threat model, protections, adversarial testing results, known limitations |
| [docs/GDPR_COMPLIANCE_REVIEW.docx](docs/GDPR_COMPLIANCE_REVIEW.docx) | GDPR compliance review |
| [docs/DPIA_SCREENING_WORKSHEET.docx](docs/DPIA_SCREENING_WORKSHEET.docx) | Data Protection Impact Assessment screening worksheet |
| [docs/GDPR_HOSTED_ACCOUNT_ADDENDUM_2026-09-08.md](docs/GDPR_HOSTED_ACCOUNT_ADDENDUM_2026-09-08.md) | GDPR addendum specific to the planned hosted-account (Professional tier) data flows |

### Engineering & process

| Doc | Covers |
|---|---|
| [docs/IMPLEMENTATION_TRACKER.md](docs/IMPLEMENTATION_TRACKER.md) | **Start here for "what's open right now."** Living doc consolidating every genuinely open item from the dated review/audit/spec docs, kept current as things resolve |
| [docs/MASTER_TASK_REGISTRY.md](docs/MASTER_TASK_REGISTRY.md) | The full humanitarian mapping task register plus engineering task history |
| [docs/BUG_TRACKER.md](docs/BUG_TRACKER.md) | Living, in-repo bug tracker — currently-open real defects only, plus the known sandbox test-artifact baseline so it's never mistaken for a regression |
| [docs/RELEASE_SMOKE_TEST.md](docs/RELEASE_SMOKE_TEST.md) | ~15-minute manual checklist to run in a real QGIS session before each release |
| [docs/RELEASE_GOVERNANCE.md](docs/RELEASE_GOVERNANCE.md) | Who can cut a release and the steps a release must follow |
| [docs/OPERATIONS_LOG.md](docs/OPERATIONS_LOG.md) | Dated operational narrative — incidents, sandbox quirks, decisions made in the moment |
| [docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md](docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md) | 27-point production-readiness architecture review |
| [docs/CODE_REVIEW_2026-09-08.md](docs/CODE_REVIEW_2026-09-08.md) | Dated code review with concrete findings |

### Product & humanitarian standards

| Doc | Covers |
|---|---|
| [docs/PRODUCT_TIERS.md](docs/PRODUCT_TIERS.md) | Editions/pricing tiers, target clients, verticals — shipped vs. roadmap |
| [docs/HUMANITARIAN_CARTOGRAPHY_STANDARDS.md](docs/HUMANITARIAN_CARTOGRAPHY_STANDARDS.md) | Cartographic design/QA standards the agent's styling and layout tools follow |
| [docs/HUMANITARIAN_MAPPING_TASK_REFERENCE.md](docs/HUMANITARIAN_MAPPING_TASK_REFERENCE.md) | Humanitarian mapping task taxonomy for tool coverage, prompts, workflows, and acceptance testing |

### Roadmap, specs & dated reviews (archive)

Frozen historical documents — accurate to when they were written, never edited after the fact
(see [CLAUDE.md](CLAUDE.md)). Corrections live in newer docs that supersede them, not in-place
edits. See [docs/archive/README.md](docs/archive/README.md) for the full, one-line-each index of
every archived file; a few of particular note:

| Doc | Covers |
|---|---|
| [docs/archive/OPEN_CORE_REPO_STRATEGY.md](docs/archive/OPEN_CORE_REPO_STRATEGY.md) | Decided (not yet built): public repo stays open Community core, Pro/Enterprise built in a separate private repo, one-way sync, license-key-gated distribution |
| [docs/archive/MULTITIER_REPO_ARCHITECTURE_SPEC.md](docs/archive/MULTITIER_REPO_ARCHITECTURE_SPEC.md) | Technical spec for the above: `src/cartogen_ai` namespace package layout, QGIS loading path, sync-workflow history-protection details, distribution channels per edition |
| [docs/archive/STATUS_REVIEW_2026-08-20.md](docs/archive/STATUS_REVIEW_2026-08-20.md) | Full-codebase status review: architecture, tool registry, security, docs, open items, next steps |
| [docs/archive/DESTRUCTIVE_TOOLS_AUDIT_2026-08-21.md](docs/archive/DESTRUCTIVE_TOOLS_AUDIT_2026-08-21.md) | Audit of which destructive tools have the preview/confirm safety gate and which don't, with an open product decision on 4 humanitarian analysis tools |
| [docs/archive/DOCUMENTATION.md](docs/archive/DOCUMENTATION.md) | Earlier, superseded full-repo documentation pass |

### Project reference

| Doc | Covers |
|---|---|
| [CONTRIBUTING.md](CONTRIBUTING.md) | How this codebase is written: comment discipline, honest status labeling, testing conventions |
| [CHANGELOG.md](CHANGELOG.md) | Version history, `[1.4.0]` onward -- see [CHANGELOG_ARCHIVE.md](CHANGELOG_ARCHIVE.md) for `[1.3.0]` and earlier |
| [LICENSE](LICENSE) | GNU GPL v2 |

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) — it's short and specific to this codebase, not a generic
PR-process doc. It covers comment discipline (explain *why*, not *what*), honest status labeling
for anything unverified in a non-QGIS sandbox, and the testing conventions the suite expects.
Issues and PRs go through [github.com/cartogenai-glitch/CARTOGEN-AI](https://github.com/cartogenai-glitch/CARTOGEN-AI).

## Development

```bash
# Run the full test suite (no QGIS installation required -- every module
# degrades gracefully outside QGIS via its own QGIS_AVAILABLE guard).
# -t . is required -- see CLAUDE.md's "Running things" section for why.
python -m unittest discover -s tests -t . -p "test_*.py" -v

# Regenerate docs/TOOLS_REFERENCE.md after adding/changing a tool
python docs/generate_tools_reference.py

# Build the release zip (reads the version from metadata.txt)
python plugin_upload.py
```

CI runs the same test suite automatically on every push/PR — see
[.github/workflows/tests.yml](.github/workflows/tests.yml). See
[CLAUDE.md](CLAUDE.md) for an orientation aimed at AI coding agents working in
this repo.

The codebase is organized as:
- `agent/` — provider clients (`agent/providers/`), tools (`agent/tools/`), the
  tool-calling loop and dispatcher (`agent/agent.py`), task/memory management.
- `ui/` — the dock widget, settings dialog, canvas highlighting.
- `tests/` — unit tests, runnable outside QGIS.
- `docs/` — user guide, tool reference, specs/proposals, and living trackers
  (see the Documentation table above).
- `service/` — a standalone hosted-gateway/monetization prototype for the
  planned Professional tier (see [docs/PRODUCT_TIERS.md](docs/PRODUCT_TIERS.md)).
  Not part of the QGIS plugin itself; excluded from the release zip.
- `branding/` — brand guidelines and logo assets.

This is a single tree — there is no second copy to keep in sync. (An earlier
version of this project did maintain two parallel trees; see the note at the
top of this file.)

## Support

Internal/commercial use — for issues or questions, contact
[alaa.alshoubaki@gmail.com](mailto:alaa.alshoubaki@gmail.com).
