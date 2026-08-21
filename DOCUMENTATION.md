# Cartogen AI — Full Project Documentation

**Version:** 1.4.1 · **License:** GNU GPL v2 (see [LICENSE](LICENSE)) · **QGIS:** 3.0 – 4.99
**Repository:** this file (`cartogen-ai`, public, Community edition) — consolidated single-tree
successor to an earlier dual-tree setup (see `CHANGELOG.md`'s `[1.4.0]` entry)
**Author / maintainer:** Alaa Alshoubaki ([alaa.alshoubaki@gmail.com](mailto:alaa.alshoubaki@gmail.com))
**Document generated:** 2026-08-21, against commit `e5682c2` on `main`

This is a single, consolidated reference for the whole project — what it is, how it's built, what's
shipped versus roadmap, how it's licensed, and how an AI coding agent (or a human) should work in
this codebase. It pulls together (in full detail, not just summary) the content of `README.md`,
`CLAUDE.md`, `CONTRIBUTING.md`, `SECURITY.md`, `LICENSE`, `LICENSE_AUDIT.md`, `CARTOGEN_AI_PRD.md`,
`CARTOGEN_AI_FEATURE_LIST.md`, `docs/PRODUCT_TIERS.md`, `docs/OPEN_CORE_REPO_STRATEGY.md`,
`docs/MULTITIER_REPO_ARCHITECTURE_SPEC.md`, `docs/BUG_TRACKER.md`, `docs/IMPLEMENTATION_TRACKER.md`,
`docs/USER_GUIDE.md`, and `docs/TOOLS_REFERENCE.md`. Those individual files remain the
living/authoritative sources for their own topics — this document is a snapshot consolidation, not
a replacement for them; if this file and one of those disagree in the future, the individual doc is
more current and this file should be regenerated.

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Editions & Business Model](#2-editions--business-model)
3. [Architecture](#3-architecture)
4. [Tool Registry (131 tools)](#4-tool-registry-131-tools)
5. [Installation & Usage](#5-installation--usage)
6. [Security](#6-security)
7. [Development & Contributing Conventions](#7-development--contributing-conventions)
8. [Licensing](#8-licensing)
9. [AI Agent Instructions (CLAUDE.md, full text)](#9-ai-agent-instructions-claudemd-full-text)
10. [Product Requirements & Roadmap](#10-product-requirements--roadmap)
11. [Known Issues & Bug Tracker](#11-known-issues--bug-tracker)
12. [Project Status — What's Open Right Now](#12-project-status--whats-open-right-now)
13. [Repository Map & Documentation Index](#13-repository-map--documentation-index)

---

## 1. Project Overview

Cartogen AI is a QGIS plugin: a spatial AI agent that plans, executes, and shows its work against a
user's open QGIS project. A user types a request in plain language; the agent plans the steps, calls
real PyQGIS/Processing tools, and executes actual spatial operations — every step is inspectable, not
just suggested or hidden inside a black box.

It targets two overlapping audiences: GIS specialists who need transparency and control over what an
AI assistant actually does to their data, and non-specialist stakeholders (program officers, sitrep
authors, decision-makers) who need to ask questions of a map without learning QGIS themselves.

### What it does

- **Multi-provider LLM support** — OpenRouter, Google Gemini, OpenAI, Anthropic Claude, or a local
  Ollama server. Switch providers anytime; bring your own API key (OpenRouter has a free tier;
  Ollama is free and fully local/offline).
- **131 tools** spanning vector and raster geoprocessing, styling and labeling, print layouts,
  exports, humanitarian data (HDX / OpenStreetMap / geoBoundaries / building footprints), satellite
  imagery search, database queries, trend forecasting, humanitarian severity/needs indexing
  (JIAF/INFORM-style composite scoring for fund-allocation prioritization), 3W/4W
  operational-presence analysis and coverage-gap detection, an interactive HTML situation-dashboard
  export for non-QGIS audiences, geoprivacy obfuscation for sensitive point data (Do No Harm), and
  saved workflow presets.
- **Task Manager** — multi-step requests get a visible plan with progress tracking (TODO →
  IN_PROGRESS → PREVIEW_READY → CONFIRMED → DONE/FAILED), retry for failed steps, and
  edit-and-resend.
- **File attachments** — PDF, Word, CSV, Excel, and images. CSV/Excel attachments can be loaded as
  full real layers (not just a preview), with automatic point-geometry detection for coordinate
  columns.
- **Native web search grounding** on Gemini and OpenAI, with automatic model fallback if a
  configured model is retired.
- **Stop button** — cancel an in-progress request cooperatively instead of waiting it out.
- **Security-conscious by design** — a restricted execution sandbox for model-generated PyQGIS
  scripts, fail-closed read-only SQL enforcement, an SSRF guard on fetched URLs (including
  redirect-hop re-validation), and a destructive-action confirmation gate the model cannot
  self-approve. See [§6 Security](#6-security) for the full, adversarially-tested threat model.

### Project identity and history

This repo (`cartogen-ai`) is the single, consolidated successor to an earlier dual-tree setup. That
prior setup lived at `C:\qgis_ai_assistant` and maintained two parallel plugin trees — a root source
tree and a separately-distributed copy kept in sync by a build script (`build_cartogen_ai.py`) —
so two QGIS plugin listings could exist side by side. This repo consolidates that into one tree,
dropping the now-unnecessary `_core` suffix from internal identifiers (`CartogenAiCore` →
`CartogenAi`, `cartogen_ai_core` → `cartogen_ai`). This repo started from a fresh `git init`; full
commit history predating it lives in the old `qgis_ai_assistant` location, not here. See
`CHANGELOG.md`'s `[1.4.0]` entry for the full account of what changed and why.

---

## 2. Editions & Business Model

**Status as of this document: only the Community tier exists.** Everything the plugin currently
does — all 131 tools, every provider integration, every security protection — is Community-tier
functionality, shipped under GPL v2, with no backend service, no billing system, no accounts, and
no per-tier feature gating anywhere in the code.

### 2.1 The three planned tiers

1. **Community** (free, GPL v2) — the field responder and independent consultant. **This is what
   ships today, in full.**
2. **Professional** (target ~$20/month, "Cloud Connect Gateway") — the regional GIS analyst / SME.
   **Not built.**
3. **Enterprise** (custom SLA) — the institutional partner (major crisis-response networks,
   defense, large public-sector agencies). **Not built.**

### 2.2 Community Tier — what's actually shipped

Target persona: field officers, emergency responders, and freelance GIS consultants operating in
austere or off-grid environments.

- **Fully offline execution via Ollama.** A local REST endpoint means no API key and no outbound
  request to any cloud provider is required for the reasoning loop itself. The one honest caveat:
  tools that are *inherently* network-dependent (HDX/OSM/geoBoundaries fetches, web search,
  satellite imagery search) still need connectivity when actually invoked — "offline-first" means
  the AI reasoning loop needs no cloud, not that every tool works with zero network ever.
- **GPL v2, free to use and modify**, no account or license key of any kind.
- **The full 131-tool registry**, not a limited/gated subset — including the humanitarian-specific
  tooling (severity indexing, geoprivacy obfuscation, 3W/4W presence-gap analysis).
- **Bring-your-own API key** for OpenRouter, Gemini, OpenAI, or Claude — no gateway, no proxy, no
  plugin-side billing; the key goes straight from the user's own account to the provider.

### 2.3 Professional Tier — target design, not built

Target persona: GIS specialists and data analysts at regional NGO/government hubs or mid-sized
engineering/logistics firms who want cloud-model power without managing their own API keys or rate
limits.

| Claimed capability | Status |
|---|---|
| "Cloud Connect Gateway" — frictionless cloud LLM access without managing an API key/rate limits | **Not built.** No gateway, proxy, or plugin-hosted credential-sharing service exists. A user who wants a cloud model must obtain and paste in their own API key today. |
| Automated A3/A4 SitRep generation | **Already shipped** in Community, via `create_print_layout` + `generate_report`. |
| Pull humanitarian data from HDX/OSM | **Already shipped** in Community. |
| Extract structured data from PDF/Word attachments into charts | **Already shipped** in Community. |

The real gap for this tier is narrow but non-trivial: everything except the gateway itself is
already built and already free. The Cloud Connect Gateway isn't an enhancement to the plugin — it's
the entire prerequisite for this tier having any paid value proposition at all. It's related to, but
distinct from, `CARTOGEN_AI_PRD.md` §5.1's "live, synced data connections" idea (data access, not
model access).

### 2.4 Enterprise Tier — target design, not built

Target persona: operations directors/IT leads at major crisis-response networks, defense
organizations, or large public-sector agencies (e.g. USAID/UNHCR/IOM-scale institutions).

| Claimed capability | Status |
|---|---|
| Private data enclaves, zero-retention policies | **Not built.** No hosted data-storage layer exists — everything runs client-side against the user's own QGIS project. |
| RBAC (Role-Based Access Control) | **Not built.** No user/role/permission model — every installation is single-user by construction. |
| SSO/SAML integration | **Not built.** No auth layer to integrate SSO into. |
| Push generated maps/metadata to SharePoint Document Sets, Power BI dashboards | **Not built.** No Microsoft 365/Graph API integration anywhere. |
| Fail-closed, secure database querying | **Already shipped** in Community — `execute_read_only_sql` (see §6.2). |
| Offline-first architecture | **Already shipped** in Community (Ollama). |

Bottom line: the two capabilities enterprise buyers in this space actually care about most on
security grounds (fail-closed SQL, offline execution) are real and already shipped — but not fenced
behind anything, so there's currently no product mechanism to sell them as an Enterprise
differentiator. Everything that *would* need to be Enterprise-exclusive requires backend
infrastructure that doesn't exist yet.

### 2.5 Industry verticals — accuracy check

| Vertical | Real, shipped differentiators | Aspirational (not shipped) |
|---|---|---|
| **Humanitarian & crisis response** | Native HDX, OSM Overpass, geoBoundaries, HDX COD-AB (P-codes), OCHA FTS, WorldPop integrations; severity indexing, geoprivacy obfuscation, 3W data — a genuinely deep, verified tool set. Strongest, most accurate claim in the whole positioning. | None identified — this vertical's claims hold up well. |
| **Defense & intelligence** | Offline-first (Ollama) execution; fail-closed read-only SQL enforcement; an AST-based execution sandbox with a documented, adversarially-tested threat model. | Framing implies Enterprise-tier exclusivity, but these protections are available in the free Community tier today. Nothing is defense-specific (no classification handling, no air-gapped tooling, no compliance certifications) — general-purpose defense-in-depth, valuable but not purpose-built. |
| **Local government & urban planning** | Zonal statistics, population exposure estimation (WorldPop), print layouts, the full raster/vector geoprocessing suite. | No municipal-specific tooling (zoning-code-aware analysis, permit workflows, cadastral-specific tools) — general-purpose GIS capability, not purpose-built. |

### 2.6 Where Pro/Enterprise code will actually live

This repo stays the single, public, GPL v2 Community codebase — it does **not** become a
multi-edition codebase with tier-gating logic inside it. See [§3.3](#33-open-core-two-repo-strategy)
for the full public/private repo architecture this implies.

> **Note on a competing, not-yet-decided proposal:** `docs/TIER_RESTRUCTURE_PROPOSAL_2026-08-20.md`
> (dated 2026-08-20, frozen) sketches a different split — Community (77 of 134 tools, connectivity
> capped, "open source" branded but source **locked**), Pro (full registry, same cap, **closed**
> source), Enterprise (full registry, all connectivity, closed source). Its "locked"/"closed" source
> framing conflicts with this project's actual GPL v2 license and was never resolved as an
> engineering decision — it needs real legal counsel and a business decision first (see
> `docs/IMPLEMENTATION_TRACKER.md` §1.3). The two-repo open-core model in §3.3 below is the
> currently-decided direction that resolves this tension for the Community side.

---

## 3. Architecture

### 3.1 Repository layout (current, post namespace-package restructure)

```
cartogen-ai/                          (repo root — this is the QGIS plugin folder itself)
├── __init__.py                       QGIS plugin entry point — classFactory(), sys.path bootstrap
├── plugin_main.py                    QGIS plugin main class (CartogenAi) — initGui()/unload()
├── metadata.txt                      QGIS plugin manifest (name, version, changelog=, license=)
├── pyproject.toml                    Builds distribution "cartogen-ai-core" (cartogen_ai.core only)
├── plugin_upload.py                  Packages the release zip from this repo
├── requirements.txt                  Optional Python deps (document parsing, web search, imagery)
├── icon.png
├── src/
│   └── cartogen_ai/                  ← NO __init__.py here (PEP 420 namespace root)
│       └── core/
│           ├── __init__.py           ← package proper starts here
│           ├── agent/                45 files — agent core, tool registry, providers
│           │   ├── agent.py          Tool-calling loop and dispatcher
│           │   ├── providers/        5 LLM provider clients + a Pro-tier stub
│           │   ├── tools/            Every callable tool, one file per domain
│           │   ├── task_manager.py, task_runner.py, scheduler.py
│           │   ├── memory.py, chat_persistence.py, lineage.py
│           │   ├── auth.py, model_selector.py, tool_router.py
│           │   ├── prompts.py, prompt_refiner.py, map_context.py
│           │   └── qgis_compat.py, deps.py
│           └── ui/                   6 files — dock widget, settings dialog, canvas highlighting
├── tests/                            Unit tests, runnable without a QGIS installation
│   └── __init__.py                   sys.path bootstrap for test discovery
├── docs/                             User guide, tool reference, specs, living trackers
├── service/                          Standalone hosted-gateway/monetization prototype for the
│                                      planned Professional tier — not part of the QGIS plugin,
│                                      excluded from the release zip
├── branding/                         Brand guidelines and logo assets
├── .github/workflows/                CI (tests.yml) + sync-to-private.yml (inactive scaffold)
├── LICENSE, LICENSE_AUDIT.md, SECURITY.md, CONTRIBUTING.md, CLAUDE.md
└── CHANGELOG.md                      Full version history
```

This is a single tree — there is no second copy to keep in sync. (An earlier version of this
project did maintain two parallel trees; see `CHANGELOG.md`'s `[1.4.0]` entry.)

### 3.2 Namespace package design

The real agent/UI code lives under `src/cartogen_ai/core/` using **PEP 420 implicit namespace
packages** — a directory with **no** `__init__.py` at the point the shared namespace begins. This
lets multiple, separately-installed distributions contribute subpackages under one shared top-level
import name with zero file conflicts:

```
cartogen-ai/ (this repo, public)          cartogen-ai-pro/ (private repo, not yet created)
└── src/cartogen_ai/  ← no __init__.py    └── src/cartogen_ai/  ← no __init__.py (same namespace)
    └── core/                                 └── pro/
        ├── __init__.py                           ├── __init__.py
        ├── agent/                                └── ...  (Cloud Connect Gateway client,
        └── ui/                                             RBAC/SSO, license validation)
```

When both distributions are `pip install`-ed into the same environment, Python merges
`src/cartogen_ai/` from each into one working `cartogen_ai` namespace — `cartogen_ai.core.*` and
`cartogen_ai.pro.*` resolve side by side, no file ever collides, and neither package needs to know
the other exists at import time. `src/cartogen_ai/__init__.py` must **never** be added in either
repo — doing so would turn `cartogen_ai` into a regular package owned by whichever distribution's
copy wins on `sys.path`, breaking the merge for the other.

**Why the code moved out of the repo root:** before this restructure, `agent/` and `ui/` lived
directly at the repo root (where QGIS's plugin loader expects importable code to start). That
layout can't coexist with the namespace split — it would give the public repo no natural place for
a private repo's `cartogen_ai.pro`/`.enterprise` to attach alongside it under a shared top-level
name. The old root-level `agent/`/`ui/`/`cartogen_ai.py` no longer exist at the repo root at all
(moved out via same-filesystem rename during the restructure — see
`docs/MULTITIER_REPO_ARCHITECTURE_SPEC.md` §3 for the full mechanical detail, including a real bug
this surfaced: a file literally named `cartogen_ai.py` at the repo root collided with the
`cartogen_ai` namespace package itself, since a regular module anywhere on `sys.path` always wins
over a namespace-package portion. Fixed by renaming it to `plugin_main.py` — full incident writeup
in `docs/BUG_TRACKER.md` BUG-2026-08-21-6).

### 3.3 Open-core two-repo strategy

**Decided direction — not yet built.** This repo is the **public** repo (Community edition, GPL v2,
the full 131-tool registry, no license key, no gating — anyone can clone, read, and run it
standalone). A **private repo** (not yet created) is planned to hold Pro/Enterprise-only modules:
the hosted Cloud Connect Gateway client, RBAC/SSO integration, M365/SharePoint/Power BI push, and
any capability that depends on backend infrastructure or is deliberately not given away for free.
The private repo is **not a fork** of this one — it builds on this repo as an upstream core.

This resolves a licensing tension `docs/TIER_RESTRUCTURE_PROPOSAL_2026-08-20.md` §3 flagged and
explicitly did not settle: under the two-repo model, Community stays genuinely open GPL v2 in the
public repo — only the *additional* Pro/Enterprise code, which doesn't exist in the Community
product at all, lives under separate (not-yet-decided) proprietary terms in the private repo.

**Sync mechanism — one-way, public → private:**
- A GitHub Actions workflow in this public repo (`.github/workflows/sync-to-private.yml`, currently
  disabled with `if: false` — the private repo doesn't exist yet) mirrors every push to `main` into
  a dedicated branch (`sync/public-core`) of the private repo, using a deploy key scoped to only
  that branch (`secrets.PRIVATE_REPO_DEPLOY_KEY`, a GitHub Secret).
- **Protecting private commit history:** the workflow only ever pushes to that one dedicated branch
  with a plain `git push` — never `--force`, never a force-push refspec. It never touches the
  private repo's own default branch or any branch containing its proprietary commits.
- **One-way only.** Nothing flows from the private repo back into this one automatically.

**Distribution:**

| Edition | Channel | Format | Status |
|---|---|---|---|
| Community | Public GitHub Releases / release zip via `plugin_upload.py` | Plugin release zip | **Implemented** — working today |
| Community | QGIS plugin repository (plugins.qgis.org) | Plugin release zip | Planned, not yet submitted |
| Community | Public PyPI (`cartogen-ai-core`) | Python wheel/sdist | **Not implemented** — `pyproject.toml` defines the distribution; no publish workflow exists yet |
| Pro/Enterprise | Gated website download | Precompiled wheel | **Not implemented** — depends on the private repo existing first |
| Pro/Enterprise | Gated website download | Standalone executable (PyInstaller or Nuitka) | **Not implemented** — tool choice not yet made |

Sensitive verification modules (license-check logic) must be stripped from source or compiled
before any Pro/Enterprise build leaves the private repo's pipeline — nothing to strip yet, since no
license-validation code has been written anywhere. License-key validation design (offline vs. online
checking) is not decided.

**Next steps (not done, no timeline):** (1) create the private repo when Pro/Enterprise work
actually begins; (2) fill in `sync-to-private.yml`'s `PRIVATE_REPO` placeholder
(`REPLACE-ME/cartogen-ai-pro`); (3) decide the private repo's license with real legal review before
any Pro/Enterprise code ships; (4) decide PyInstaller vs. Nuitka.

### 3.4 QGIS plugin loading path

QGIS's plugin loader is understood — **not yet confirmed in a live QGIS session** — to add a
plugin's own root directory to `sys.path` when it loads the plugin. `__init__.py` (repo root) adds
`src/` to `sys.path` before `classFactory()` triggers any import from `cartogen_ai.core.*`:

```python
_SRC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

def classFactory(iface):
    from .plugin_main import CartogenAi
    return CartogenAi(iface)
```

`plugin_main.py` then imports from the new location with absolute imports, e.g.
`from cartogen_ai.core.agent.agent import CartogenAi as AgentCore`. **This sys.path bootstrap has
not been tested in a real QGIS session** — run `docs/RELEASE_SMOKE_TEST.md` before the next release
to confirm it actually resolves `cartogen_ai.core.*` inside QGIS's own Python environment. (By
contrast, the `cartogen_ai.py`/namespace collision bug described in §3.2 *has* been confirmed and
fixed — it didn't need a live QGIS session to reproduce, since the same `sys.path` mechanics apply
to the plain Python interpreter running the test suite.) `tests/__init__.py` does the equivalent for
the test suite, and that half **is** verified every run — the suite simply wouldn't collect if it
were wrong.

### 3.5 Threading model

LLM calls run inside a real `QgsTask` (not `threading.Thread`), so they never block the QGIS UI
thread. PyQGIS-touching tool calls are safely bounced to the main thread via a `ToolDispatcher`
(`Qt.BlockingQueuedConnection`). Pure-network tools (`NETWORK_ONLY_TOOLS`) bypass this dispatch
entirely, since they're safe to run from a background thread. Tools that mix a fast QGIS-state read
with a slow network call split the two (`TWO_PHASE_TOOLS`) so neither blocks the GUI. Two real
freeze bugs were found and fixed during development: pure-network tools initially still bounced
through the main-thread dispatch, and two tools mixed network I/O with QGIS layer creation in one
blocking call.

### 3.6 Memory and persistence

- **Project memory** — stored in `QgsProject` custom properties, tied to the current project file.
- **Global memory** — stored in `QgsSettings`, persists across projects.
- **Spatial action log** — a sidecar SQLite `.sqlite` file next to the project (`agent/memory.py`),
  not just project properties — used for history/memory at a scale `QgsProject` custom properties
  alone wouldn't handle well.
- **Chat history** — persisted into the active project's `.qgz` file, but **opt-in, off by default**
  (see §6.7).

### 3.7 Credential storage

API keys go through `QgsAuthManager` (encrypted, OS-keyring-backed) first; if that's unavailable,
`save_credential` falls back to plaintext `QgsSettings` and flags it
(`CredentialManager.used_plaintext_fallback`) so the settings dialog can warn the user instead of it
happening silently. No credential value is ever written to a log or console print.

---

## 4. Tool Registry (131 tools)

Auto-generated from the live tool registry by `docs/generate_tools_reference.py` — that file is the
canonical, always-current source; the table below is a snapshot count per category as of this
document's generation date. Regenerate `docs/TOOLS_REFERENCE.md` after adding or changing any tool
(`python docs/generate_tools_reference.py`) so it never drifts from the actual code.

Flags used in the full reference: **network-only** tools bypass the main-thread QGIS dispatcher
entirely (pure HTTP, safe from a background thread); **two-phase** tools split a network fetch
(background thread) from the QGIS-touching part (main thread); **task-management** tools are
excluded from auto-advance in the Task Manager.

| Category | Tool count | Examples |
|---|---|---|
| Vector & Geoprocessing | 43 | clip, buffer, spatial join, dissolve, CRS repair, topology diagnosis, join assistant |
| Raster | 20 | NDVI/NDWI/NDRE, zonal statistics, hillshade, slope/aspect, classification, mosaic, pan-sharpening, interpolation |
| Humanitarian Data (HDX / OSM / geoBoundaries) | 9 | `search_hdx_datasets`, `fetch_osm_features`, `fetch_geoboundaries`, `fetch_hdx_admin_boundaries`, `fetch_building_footprints`, `fetch_worldpop_population`, `fetch_fts_funding_data`, `add_incident_point`, `add_point_layer` |
| Styling & Labeling | 9 | Graduated/categorized symbology, colorblind-safe ramps, labeling, hotspot analysis |
| Humanitarian Logistics | 7 | `calculate_service_area`, `travel_time_matrix`, `optimal_hub_siting`, `location_allocation`, `optimize_delivery_route`, `population_access_gap`, `score_route_incident_risk` |
| Data Analysis & Prediction | 6 | `calculate_severity_index`, `calculate_presence_gap`, `calculate_population_in_need`, `calculate_damage_exposure_severity`, `analyze_incident_trend`, `forecast_trend` |
| Export & Reporting | 6 | `export_layer`, `export_to_csv`, `generate_report`, `generate_spatial_report`, `generate_html_dashboard`, `print_map` |
| Reporting & Document Analysis | 6 | `extract_pdf_tables`, `extract_word_tables`, `aggregate_data`, `generate_chart`, `load_3w_data`, `generate_sector_coverage_report` |
| System, Search & Scripting | 6 | `execute_pyqgis_script`, web search, geocoding |
| Task & Memory Management | 5 | Plan/task tools, project/global memory store & retrieve |
| Monitoring & Scheduling | 4 | `schedule_recurring_workflow`, `run_monitoring_workflow`, `list_scheduled_workflows`, `stop_recurring_workflow` |
| Database & Workflows | 3 | `execute_read_only_sql`, `save_workflow_preset`, `load_workflow_preset` |
| Satellite Imagery & Vision | 3 | STAC satellite search, `inspect_canvas_visually`, `calculate_raster_change_detection` |
| Project Management | 2 | `load_project`, `save_project` |
| AI Imagery Feature Extraction | 1 | `extract_features_from_imagery` (FastSAM-based, optional heavy dependency) |
| Print Layouts | 1 | `create_print_layout` |
| **Total** | **131** | |

For the complete per-tool reference (parameters, return shapes, flags), see
[docs/TOOLS_REFERENCE.md](docs/TOOLS_REFERENCE.md).

### 4.1 Tool routing

As the registry grew, a `ToolRouter` (`agent/tool_router.py`) was added to filter tools to the
top-k most relevant candidates per request, to prevent context bloat from passing all 131 tool
schemas into every planning call. It uses keyword/substring intent scoring, **not** embedding-based
semantic similarity — an API-cost-optimization review measured its real recall against 9 realistic
paraphrased queries and found 3 of 9 (33%) never made it into the candidate set at all, a direct
cost problem (a missed tool means a failed turn, a heavier `execute_pyqgis_script` fallback, or
burned iterations). Root causes were fixed: a stable-sort tie-break bug that silently favored
whichever tools happened to be registered earliest (candidates now shuffle before scoring), a small
curated alias list, and `top_k` raised from 30 to 40 as the registry grew to 125+ tools (it was
originally tuned at 61).

---

## 5. Installation & Usage

### 5.1 Installation

**From the release zip (recommended):**
1. In QGIS: `Plugins` → `Manage and Install Plugins…` → `Install from ZIP`.
2. Select `cartogen_ai.zip` (or the versioned archive under `dist/`).
3. Enable the plugin if it isn't auto-enabled.

**From source (development):**
1. Copy this repository into your QGIS profile's plugin folder, e.g.
   `%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\cartogen_ai` on Windows.
2. Restart QGIS, or use the Plugin Reloader plugin.

This build is not currently published on the public QGIS plugin repository (plugins.qgis.org);
install via one of the methods above.

**Optional dependencies** (document parsing for PDF/Word/Excel attachments, `search_web`,
chart/dashboard generation, PDF table extraction) need a few extra Python packages, listed in
`requirements.txt`: `pypdf`, `python-docx`, `openpyxl`, `pandas`, `duckduckgo-search`, `pdfplumber`,
`matplotlib`, `folium`. Install either through the bundled `qpip` plugin dependency (QGIS offers to
install them) or manually in the OSGeo4W Shell: `python -m pip install -r requirements.txt`.
Everything else works without them — a missing optional package degrades that one feature with a
clear error message rather than breaking the plugin.

`ultralytics` (needed only for `extract_features_from_imagery`, a FastSAM-based tool) is a separate,
heavier optional dependency — pulls in `torch`, expects a ~200MB+ download plus a separately-fetched
model checkpoint on first use. **Install optional dependencies with QGIS fully closed, not while
it's running** — a package install that replaces a module QGIS already has loaded (most likely
`ultralytics`, which shares `jinja2`/`markupsafe` with `folium`) can fail on Windows with
`PermissionError: [WinError 5] Access is denied` on a locked `.pyd` file. This is a Windows
file-lock issue, not a plugin bug.

### 5.2 Quick start

1. Open the **Cartogen AI** panel (toolbar icon or `Plugins` menu).
2. Click the ⚙ settings icon, pick a provider, and paste an API key (or point at a local Ollama
   server — no key needed). The key field auto-fetches that provider's live model list.
3. Pick a model, or leave it on **Auto** — the agent routes simple requests to a cheaper/faster
   model and complex multi-step requests to a stronger one automatically.
4. Type a request, e.g. *"List all layers in the project"* or *"Calculate the area for the active
   layer."* See the in-app **Help** tab for more examples.

### 5.3 The panel

Three tabs: **💬 Chat** (talk to the agent), **📋 Tasks & Memory** (current plan + stored project
memory), **❓ Help** (provider list, quick tips, example prompts).

### 5.4 Attaching files

Click 📎 to attach a PDF, Word document, image, CSV, or Excel file.
- **PDF/Word:** full text is extracted and given to the agent. For tabular data specifically, ask
  explicitly (e.g. *"extract the tables from this PDF"*) — plain-text extraction flattens tables
  into hard-to-use text, but the agent can pull real structured rows/columns when asked.
- **Images:** sent directly to the model for visual analysis — only works if the current
  provider/model supports vision.
- **CSV/Excel:** the agent gets a short preview (columns, row count, sample rows) plus the real file
  path. Ask explicitly (*"load this as a layer"*) to load the full dataset as a real layer rather
  than just a description.

### 5.5 Multi-step requests and the Task Manager

Complex requests generate a visible plan (Tasks & Memory tab): each step shows TODO → IN_PROGRESS →
DONE/FAILED with a progress bar. Buttons available depending on task state: **✔ Confirm** /
**✕ Cancel** (for a `PREVIEW_READY` task), **🔁 Retry** (a `FAILED` task), **✏️ Edit & Resend**
(pre-fills an editable prompt), **📋 Copy Snippet** (copies PyQGIS code to clipboard), **✕ Clear
Plan**. A dropdown browses the last 5 plans this session (read-only; sending a new message snaps
back to the live plan).

### 5.6 Destructive actions

Removing a layer or running a field-calculator mutation always goes through a preview-then-confirm
gate: the agent shows what it's about to do and waits for an explicit **Confirm** click — it cannot
skip this itself, even if prompted to (the confirmation flag isn't something a tool call can set;
only the UI button can). See §6.5 for the full mechanism and the exact tool list currently covered.

### 5.7 Sensitive point data

Before mapping, exporting, or reporting on individually-identified sensitive locations (GBV
survivors, individual IDP households, named protection cases), use `obfuscate_sensitive_points`
first — a Do No Harm safeguard and, increasingly, an explicit donor/ECHO compliance requirement.
Three methods (in the layer's own CRS units, not meters — reproject first if a specific real-world
distance matters):
- **`grid_snap`** — every point sharing a grid cell moves to that cell's center. Strongest
  protection: multiple true locations become genuinely indistinguishable.
- **`jitter`** — random displacement within a radius (still 1:1 point per input point).
- **`admin_unit_snap`** — moves each point to the centroid of the admin-boundary polygon it falls
  within.

The agent won't apply this automatically — it's a judgment call, and it asks which method when it
looks relevant.

### 5.8 Interactive HTML dashboards

`generate_html_dashboard` exports one or more layers as a single interactive Leaflet map (pan/zoom,
layer toggles, click-a-feature popups) — the deliverable for a fund-allocation committee or donor
who won't open QGIS themselves. **It needs internet access to view, not just to generate** — the
file is created offline, but opening it in a browser loads the map library and basemap tiles from
public CDNs each time. Not a fully offline package despite being a single file. If the audience has
unreliable connectivity, use a static export instead (`print_map`, `create_print_layout`,
`generate_report`).

### 5.9 Building footprint data

`fetch_building_footprints` pulls from Microsoft's Global ML Building Footprints dataset —
pre-computed polygons covering 225 countries/regions. Good for baseline digitization where no local
footprint data exists. **This is not live extraction from a specific image, and it is not damage
assessment** — it's Microsoft's own periodic dataset refresh, so it can lag the latest imagery by
months. For damage assessment against a specific before/after image pair, use
`calculate_raster_change_detection` instead.

### 5.10 Troubleshooting

- **"No API key configured"** — add a key for the active provider in Settings.
- **A provider request fails** — cloud providers automatically retry transient errors and fall back
  to an alternate model if the configured one is retired; check the message text if it still fails.
- **"Reached the tool-call limit"** — usually means the request needed many individual actions; try
  rephrasing for bulk handling (*"create one layer with all of them"*) or split into smaller
  requests.
- **Something claims success but looks wrong** — the agent cross-checks its final answer against
  every tool call it actually made that turn and appends a correction if any failure goes
  unacknowledged — but this only catches an *unacknowledged* mismatch, not every possible error.
  Verify anything consequential.
- **A CSV/Excel file loaded with no location data, or points in the wrong place** —
  `load_tabular_data_as_layer` auto-detects coordinate columns by name; if it can't guess
  confidently it returns `FIELD_SUGGESTION` with the real column names instead of guessing wrong. If
  points are in the wrong place, check `x_field`/`y_field` or pass the correct `crs` (e.g. the data
  is in UTM meters, not WGS84 degrees).

---

## 6. Security

Full detail lives in [SECURITY.md](SECURITY.md) — reproduced here in full since it's part of the
"complete documentation" this file consolidates. Every claim below has a file:line reference in the
real `SECURITY.md` so it can be checked against the code directly, not trusted on its own.

### 6.1 Threat model

Two things in the tool-calling loop are **untrusted input**, not just data:
1. **The LLM's own output** — a cloud provider response, a prompt-injected instruction hidden
   inside fetched web/OSM/HDX content, or simply a model mistake can result in a tool call with
   attacker-influenced arguments (a script to execute, a URL to fetch, a SQL query to run).
2. **Content fetched from the internet** (`search_web`, `fetch_osm_features`,
   `search_hdx_datasets`, `fetch_geoboundaries`, `fetch_fts_funding_data`) that feeds back into the
   model's context and could contain text written to look like instructions.

The user running QGIS is trusted (they can already run arbitrary Python in the QGIS Python console
with no plugin involved). The protections below exist for the case where the *model* — not the
user — ends up driving a dangerous action, through prompt injection, hallucination, or a
compromised/malicious model provider.

### 6.2 Protections

1. **PyQGIS script execution sandbox** (`execute_pyqgis_script`) — two independent layers: static
   AST validation rejects a script before it runs if it imports a blocked module, references a
   blocked builtin even without calling it, or accesses a blocked attribute name (including the
   classic `().__class__.__bases__[0].__subclasses__()` escape chain, and `.format`/`.format_map`).
   Blocked modules: `os`, `subprocess`, `shutil`, `sys`, `socket`, `ctypes`, `importlib`, `pty`,
   `multiprocessing`, `pip`, `urllib`, `requests`, `http`, `ftplib`, `smtplib`, `pickle`, `codecs`,
   `base64`, `sqlite3`, `tempfile`, `platform`, `threading`, `asyncio`, `pdb`, `code`, `marshal`,
   `shelve`, `builtins`, `gc`, `inspect`, `types`, `copyreg`, `runpy`. Blocked Qt classes regardless
   of submodule: `QFile`, `QSaveFile`, `QTemporaryFile`, `QDir`, `QDirIterator`, `QFileInfo`,
   `QFileSystemWatcher`, `QProcess`, `QProcessEnvironment`, `QNetworkAccessManager`,
   `QNetworkRequest`, `QNetworkReply`, `QTcpSocket`, `QUdpSocket`, `QLocalSocket`, `QSslSocket`,
   `QSettings`, `QLibrary`, `QPluginLoader`, `QDesktopServices`. Beyond the AST layer, the script's
   `__builtins__` is a curated allowlist of ~50 safe names, not real Python builtins. **This is
   defense in depth against known techniques, not a formally proven sandbox.**
2. **Read-only SQL enforcement** (`execute_read_only_sql`) — a keyword blocklist (`DROP`, `DELETE`,
   `UPDATE`, `INSERT`, `ALTER`, `TRUNCATE`, `CREATE`, `GRANT`, `REVOKE`, `INTO`, `COPY`, `PROGRAM`,
   `EXECUTE`, `CALL`, `DO`, `MERGE`, `VACUUM`, `ANALYZE`, `LO_EXPORT`, `LO_IMPORT`,
   `PG_READ_FILE`, `PG_READ_BINARY_FILE`, `PG_LS_DIR`, `DBLINK`), a stacked-statement guard, **and**
   a DB-level layer that opens a real PostGIS connection, sets the session `READ ONLY`, and
   **fails closed** if that can't be confirmed.
3. **SSRF guard on fetched URLs** — resolves the hostname and rejects loopback, private,
   link-local (including the `169.254.169.254` cloud metadata endpoint), reserved, and multicast
   addresses (both IPv4/IPv6) before fetching. **Every redirect hop is re-validated, not just the
   initial URL** — confirmed live that a URL passing the check could `302` to an unvalidated address
   otherwise; a custom redirect handler now re-runs the check on every hop. Response body is
   streamed and capped at 200MB.
4. **Credential storage** — via `QgsAuthManager` (encrypted) with a flagged plaintext fallback (see
   §3.7). No credential value is ever logged.
5. **Destructive-action confirmation gate** — `remove_layer`, `load_project`, `field_calculator`,
   `calculate_area`, and `calculate_length` require a `confirmed` flag the dispatcher strips from
   any LLM-supplied arguments. The only real path to `confirmed=True` is a UI button click, not
   anything the model can inject. `calculate_area`/`calculate_length` were added to this gate after
   an inconsistency was found (they mutate the layer the same way `field_calculator` does but
   weren't gated). **Four tools deliberately do not yet have this gate**
   (`calculate_severity_index`, `calculate_presence_gap`, `calculate_population_in_need`,
   `calculate_damage_exposure_severity`) — pending an open product decision on the workflow-friction
   tradeoff (see §12).
6. **Prompt-injection guidance** — instructs the model to treat content returned by search/fetch
   tools as data, never as instructions to follow. This is a prompt-level mitigation, not
   code-enforced (see Limitations).
7. **Chat history persistence is opt-in** (default **off**) — a project file is a shareable
   artifact, and history was previously always saved into it with no opt-out, risking sensitive
   content traveling with the map file silently.
8. **Recurring monitoring scheduler** controls — a tool allowlist (7 read-only analysis tools, no
   geometry edits or file writes), a minimum interval floor (rejects intervals under 1 minute — a
   previous bug allowed near-zero intervals to become a self-inflicted denial-of-service), and a cap
   of 5 concurrent schedules.
9. **Prompt Refinement Layer external-call awareness** — when enabled (default off), doubles how
   many times a message leaves the machine to an external provider; same trust boundary, not a new
   vulnerability class, but relevant to any "private data enclave" claim (still not built).

### 6.3 Adversarial testing performed

An adversarial pass was run against the running code, not just theoretical review — each finding
below was *confirmed exploitable* before being fixed:

| # | Attempted bypass | Result before fix | Fixed by |
|---|---|---|---|
| 1 | `import builtins; builtins.open(path).read()` | Confirmed: full arbitrary local file read | Added `builtins` to blocked modules |
| 2 | `"{0.__class__.__bases__}".format(x)` / `.format_map()` | Confirmed: reaches dunder attributes invisibly to the AST walk | Block `.format`/`.format_map` as attribute access |
| 3 | `import gc; gc.get_objects()` | Confirmed: enumerates the live object graph | Added `gc` to blocked modules |
| 4 | `import inspect; inspect.currentframe()` | Confirmed: reaches other frames' globals | Added `inspect` to blocked modules |
| 5 | `SELECT lo_export(...)`, `pg_read_file(...)`, `dblink(...)` | Confirmed: none of the DML/DDL keywords catch these | Added to the SQL keyword/substring blocklist |
| 6 | Decimal/hex/octal IP notation for SSRF | Tested — fails closed already | No fix needed |
| 7 | URL userinfo/fragment confusion | Tested — not exploitable | No fix needed |
| 8 | `().__class__.__base__` (singular) | Tested — not exploitable | No fix needed |
| 9 | `from qgis.PyQt.QtCore import QDirIterator` to walk the filesystem | **Confirmed in live production use** — browsed real unrelated personal folders | Added `_BLOCKED_QT_NAMES` |
| 10 | `from qgis.PyQt.QtCore import QFile as F` (aliased import) | Confirmed the usage-only fix missed this | Check the `ImportFrom` alias's real name directly |
| 11 | `add_layer_from_path` with a URL that `302`-redirects post-validation | Confirmed exploitable with a real local HTTP server | Custom redirect handler re-validates every hop |

### 6.4 Known limitations (accepted risk, not fixed)

- **DNS rebinding (TOCTOU)** on the SSRF guard — a sophisticated attacker-controlled resolver could
  theoretically slip a private IP through between the validation lookup and the fetch lookup. Judged
  higher-risk to fix hastily (a broken pinning attempt could itself become a regression) than the
  narrow scenario it defends against.
- **Local file access is intentionally broad** — several tools will read/write any local file path
  the model names; this is core functionality (loading/exporting the user's own files), not a bug.
- **`execute_pyqgis_script`'s sandbox blocks specific dangerous names, not file I/O capability in
  general** — legitimate PyQGIS objects the script is allowed to use can themselves read/write
  files. Accepted: any sandbox exposing real PyQGIS functionality necessarily exposes what PyQGIS
  itself can do.
- **Prompt-injection guidance (rule 16) is not code-enforced.**
- **This is not a formal sandbox** — `exec()`-based restriction is inherently best-effort, not a
  provable security boundary.
- **`extract_features_from_imagery`'s model weights download is unpinned and unverified** — delegates
  entirely to `ultralytics`' own first-use download logic with no checksum verification.

### 6.5 Licensing note (from SECURITY.md)

This plugin is GNU GPL v2, consistent with PyQGIS (`qgis.core`, `qgis.gui`, `qgis.utils`), which it
imports at runtime. A proprietary license was considered and deliberately not used, specifically to
avoid the unresolved legal question of whether a proprietary license would be compatible with
importing GPL v2 PyQGIS code — monetization is services-based instead (support, hosting, custom
integration), not code licensing. See [§8 Licensing](#8-licensing) for the full picture.

---

## 7. Development & Contributing Conventions

Full detail in [CONTRIBUTING.md](CONTRIBUTING.md). This section reproduces it in full since it's
central to how this codebase — and any AI agent working in it — actually operates.

### 7.1 Comments explain *why*, not *what*

A comment that restates the code adds nothing. A comment that explains the failure mode the code is
defending against is worth its weight. When you fix a real bug, write the comment the way the
existing ones are written: what broke, how you know (a stack trace, a live report, a failing test),
and why the fix works. Skip comments that just describe what the next line does.

### 7.2 State what's shipped, roadmap, or unverified — honestly, in the code itself

This discipline belongs in code, not just docs. If something is a stub, a prototype, or unverified
against a live/real environment, say so in the code that implements it. If you're not sure something
works because it can't be tested in this sandbox, say that too, specifically. Don't let a doc's
status label go stale — update it in the same change that ships the thing it was describing as "not
yet built."

### 7.3 When you find a gap, flag it — don't silently fix it if it's a judgment call

Mechanical, low-risk fixes (a wrong error message, a missing retry) get fixed directly. Anything
that changes behavior a user or integration might depend on, or that this environment can't verify
live, gets flagged with a clear recommendation instead of applied silently.

### 7.4 Testing conventions

Run the full suite (no QGIS installation required — every module degrades gracefully via its own
`QGIS_AVAILABLE` guard):

```bash
python -m unittest discover -s tests -t . -p "test_*.py" -v
```

**The `-t .` flag is required** — without an explicit top-level directory, `discover()` treats
`-s tests` as also the top-level directory and imports each `test_*.py` as a bare top-level module
rather than as a member of the `tests` package, so `tests/__init__.py` never runs as a package
initializer and its `src/`-on-`sys.path` bootstrap never executes — every `cartogen_ai.core.*`
import then fails with `ModuleNotFoundError`. This was a real bug found and fixed across 6
documentation/CI locations on 2026-08-21 (see `docs/BUG_TRACKER.md` BUG-2026-08-21-7).

Other commands:
```bash
# Regenerate docs/TOOLS_REFERENCE.md after adding/changing a tool
python docs/generate_tools_reference.py

# Build the release zip (reads the version from metadata.txt)
python plugin_upload.py
```

CI (`.github/workflows/tests.yml`) runs the same test suite and a `py_compile` check on every
push/PR. There is no QGIS in CI — anything that only breaks inside a real QGIS session needs manual
verification via `docs/RELEASE_SMOKE_TEST.md`.

Pure-Python logic (chat formatting, color derivation, tool routing) is deliberately kept free of
Qt/QGIS imports so it's directly unit-testable — see `src/cartogen_ai/core/ui/chat_formatting.py`'s
own docstring for why, relative to `src/cartogen_ai/core/ui/dock_widget.py`. A structural bug this
project actually shipped (a duplicate dict key silently discarding `ToolRouter` aliases, no error at
parse or runtime) is now guarded against by an `ast`-based static test
(`tests/test_tool_router.py`'s `TestToolAliasesNoDuplicateKeys`) — consider a similar structural test
for any comparable "the interpreter won't warn you" footgun.

### 7.5 Single tree, one public codebase

This repo is a single source tree — no second copy to keep in sync — and, by design, the *only*
codebase for the Community edition. Pro and Enterprise are not built as tiers inside this repo;
they're planned for a separate private repo that syncs from this one (§3.3). **Do not add
tier-check or license-gating logic here** — out of scope for this repo by design, not just unbuilt.

### 7.6 Frozen historical docs

`CARTOGEN_AI_FEATURE_LIST.md`, `CARTOGEN_AI_PRD.md`, `IMPLEMENTATION_TASK_LIST.md`,
`CHANGELOG.md`'s past entries, and dated review/audit/spec docs (filenames ending in a date, e.g.
`docs/STATUS_REVIEW_2026-08-20.md`) are deliberately left untouched after the fact — a historical
record, not living documentation. If something in one is now wrong or superseded, add a new dated
doc or an `docs/IMPLEMENTATION_TRACKER.md` entry that supersedes it; don't edit the old one to match
current reality. This includes not "fixing" old identifier names in them (e.g. `QgisAiAgent`) even
after a rebrand.

---

## 8. Licensing

### 8.1 Plugin source code license

The Cartogen AI plugin source code is released under the **GNU General Public License v2 (GPL v2) or
later**, in compliance with the QGIS Plugin Architecture Guidelines and PyQGIS's own GPL v2
licensing. See [LICENSE](LICENSE) for the full legal text (also reproduced in §8.4 below).

A proprietary/all-rights-reserved license was considered for a period (2026-08-11), specifically to
weigh commercializing the plugin's code directly. That path was deliberately not taken: PyQGIS
modules (`qgis.core`, `qgis.gui`, `qgis.utils`) are GPL v2 components this plugin imports directly at
runtime, and whether that creates an obligation for the plugin itself to be GPL-compatible was
judged a genuine, unresolved legal question not worth betting a commercial license on. Monetization
is services-based instead (paid support, hosting/managed deployment, a SaaS layer, custom
integration work) — see [§2 Editions & Business Model](#2-editions--business-model). This removes
the licensing question entirely rather than resolving it.

- **QGIS API linkage:** PyQGIS modules are imported dynamically at runtime inside QGIS, not
  statically linked — but since the plugin is GPL v2 itself, this distinction carries no licensing
  risk either way.

### 8.2 Third-party dependency license matrix

Audit date: 2026-08-08 (dependency matrix), updated 2026-08-13/2026-08-14 for additional packages
and data sources; license basis reaffirmed 2026-08-11.

| Package | Version range | License | Linking type | Status |
|---|---|---|---|---|
| `pypdf` | ^3.0.0 | BSD-3-Clause | Isolated runtime import | Compliant |
| `python-docx` | ^0.8.11 | MIT | Isolated runtime import | Compliant |
| `openpyxl` | ^3.0.0 | MIT | Isolated runtime import | Compliant |
| `pandas` | ^2.0.0 | BSD-3-Clause | Isolated runtime import | Compliant |
| `duckduckgo-search` | ^6.0.0 | MIT | Isolated HTTP client import | Compliant |
| `requests` | ^2.28.0 | Apache-2.0 | Isolated HTTP client import | Compliant |
| `pdfplumber` | unpinned | MIT | Isolated runtime import | Compliant |
| `matplotlib` | unpinned | Matplotlib License (PSF-derived, BSD-style) | Isolated runtime import | Compliant |
| `folium` | unpinned | MIT | Isolated runtime import | Compliant |
| `branca` | unpinned | MIT | Isolated runtime import (folium's own dependency) | Compliant |

No proprietary software, copyleft-incompatible code, or statically vendored libraries exist inside
the codebase. All optional third-party Python packages are installed dynamically into the user's
OSGeo4W Python environment without license conflict.

### 8.3 External API services and their data licenses

All external REST APIs are queried over HTTPS without linking binary code:

| Service | Purpose | License / terms |
|---|---|---|
| OpenRouter API | Cloud LLM inference | Commercial API terms |
| Google Gemini API | Multimodal vision endpoint | Commercial API terms |
| Ollama API | Local REST endpoint | N/A (local) |
| Humanitarian Data Exchange (HDX) API | Humanitarian datasets | Open Data Commons Attribution License (ODC-BY) |
| OpenStreetMap Overpass API | Vector features | Open Database License (ODbL) |
| geoBoundaries API | Administrative boundaries | Creative Commons Attribution 4.0 (CC BY 4.0) |
| Nominatim Geocoding API | Geocoding | Open Database License (ODbL) |
| OCHA Financial Tracking Service (FTS) API | Humanitarian funding data | Publicly accessible; not independently re-verified against a specific open-data license |
| WorldPop API | Gridded population data | Creative Commons Attribution 4.0 (CC BY 4.0) |
| Microsoft Global ML Building Footprints | Building footprint polygons | Community Data License Agreement — Permissive, Version 2.0 (confirmed 2026-08-14; this dataset's license has changed before — re-verify at the source before relying on this for a formal audit) |

### 8.4 Full GPL v2 license text

The complete, verbatim text of the GNU General Public License, Version 2, June 1991, under which
this project is licensed, is available in [LICENSE](LICENSE) at the repository root. It is not
reproduced a second time in this file to avoid two copies of a legal text silently drifting out of
sync — `LICENSE` is the single source of truth for the license text itself; this documentation file
covers how that license applies to this specific project (§8.1–8.3 above).

---

## 9. AI Agent Instructions (CLAUDE.md, full text)

The following is the complete, current text of `CLAUDE.md` — the orientation document for Claude
Code (or any AI coding agent) working in this repository. Reproduced here verbatim per this
document's scope (the user's request explicitly named "custom instruction for AI agents MD" as
required content). `CLAUDE.md` itself remains the living source; if it changes, this section should
be regenerated to match.

> # CLAUDE.md
>
> Orientation for Claude Code (or any AI coding agent) working in this repo. Read this before
> making changes — it points at the conventions this project actually enforces, not generic advice.
>
> ## What this is
>
> Cartogen AI is a QGIS plugin: a spatial AI agent that plans, executes, and shows its work against
> a user's open QGIS project. Single Python package, installed as a QGIS plugin folder. No build
> step, no compiled artifacts beyond the release zip.
>
> ## Structure
>
> - `agent/` — the agent core. `agent/agent.py` is the tool-calling loop and dispatcher;
>   `agent/providers/` are the 5 LLM provider clients (OpenRouter, Gemini, OpenAI, Claude, Ollama)
>   plus a `cartogen.py` stub for a planned hosted gateway; `agent/tools/` is every tool the model
>   can call, one file per domain (vector, raster, styling, humanitarian, etc.), registered via
>   `agent/tools/registry.py`'s `@register_tool` decorator.
> - `ui/` — the QGIS dock widget, settings dialog, canvas highlighting. Everything here that
>   imports `qgis.PyQt`/`qgis.core` unconditionally can only be exercised inside a real QGIS
>   process — this sandbox (and CI) cannot run or visually verify it. `ui/chat_formatting.py` is
>   deliberately Qt-free so it stays unit-testable; follow that pattern for new pure logic.
> - `tests/` — unit tests, runnable without a QGIS installation. Every module that touches
>   `qgis.core` degrades gracefully via its own `QGIS_AVAILABLE` guard specifically so this works.
> - `docs/` — see the table in `README.md`. `docs/USER_GUIDE.md` and `docs/TOOLS_REFERENCE.md` are
>   living references; `docs/IMPLEMENTATION_TRACKER.md` and `docs/BUG_TRACKER.md` are living
>   trackers you should update when you close or find something; dated docs
>   (`docs/STATUS_REVIEW_2026-08-20.md` and similar) are frozen snapshots — see below.
> - `service/` — a standalone hosted-gateway/monetization prototype for the planned Pro tier. Not
>   part of the QGIS plugin; not built or tested by the CI workflow.
> - `metadata.txt` — QGIS plugin manifest, including an embedded `changelog=` field. Its historical
>   entries are frozen (see below) — only ever prepend a new entry, never edit an old one.
>
> *(Note added by this consolidated documentation, not part of `CLAUDE.md` itself: the `agent/` and
> `ui/` paths above describe the pre-restructure layout that `CLAUDE.md`'s own prose still uses as
> shorthand for "the agent core" / "the UI layer" conceptually — the actual current file locations
> are `src/cartogen_ai/core/agent/` and `src/cartogen_ai/core/ui/` respectively, per the namespace
> package restructure in [§3](#3-architecture). `CLAUDE.md` itself should be updated to reflect this
> path change in a future pass; flagging here rather than silently editing the quoted block, since
> this section is meant to be a verbatim reproduction.)*
>
> ## Before you touch anything: read CONTRIBUTING.md
>
> It's short and specific to this codebase, not a generic PR-process doc. The two rules that matter
> most for an AI agent working here:
>
> 1. **Comments explain *why*, not *what*.** If you fix a real bug, write the comment the way the
>    existing ones are written: what broke, how you know (a stack trace, a failing test, a live
>    report), and why the fix works. Don't write comments that just restate the next line.
> 2. **State what's shipped, roadmap, or unverified — honestly, in the code itself, not just in a
>    doc.** If something can't be verified in this sandbox (most things touching live QGIS or a
>    real LLM API response), say so explicitly rather than implying it works.
>
> Also: **frozen historical docs are never edited after the fact.** `CARTOGEN_AI_FEATURE_LIST.md`,
> `CARTOGEN_AI_PRD.md`, `IMPLEMENTATION_TASK_LIST.md`, `CHANGELOG.md`'s past entries, and any
> dated review/spec doc are accurate to when they were written — including old identifier names
> after a rebrand. If something in one is now wrong, add a new entry/doc that supersedes it; don't
> rewrite history.
>
> ## Running things
>
> ```bash
> # Full test suite -- no QGIS needed. -t . matters: without it, discover()
> # treats tests/ as its own top-level dir and never runs tests/__init__.py's
> # src/-on-sys.path bootstrap, so every cartogen_ai.core.* import fails --
> # see docs/BUG_TRACKER.md BUG-2026-08-21-7.
> python -m unittest discover -s tests -t . -p "test_*.py" -v
>
> # Regenerate docs/TOOLS_REFERENCE.md after adding/changing a tool
> python docs/generate_tools_reference.py
>
> # Build the release zip (reads version from metadata.txt)
> python plugin_upload.py
> ```
>
> CI (`.github/workflows/tests.yml`) runs the test suite and a `py_compile` check on every push/PR.
> There is no QGIS in CI — anything that only breaks inside a real QGIS session (Qt widget wiring,
> layer rendering, print layouts) needs manual verification; see `docs/RELEASE_SMOKE_TEST.md`.
>
> ## Editions
>
> Community, Pro, and Enterprise (`docs/PRODUCT_TIERS.md`) are three editions, but **not** three
> variants of this one codebase — this repo is, and stays, the single public Community codebase.
> Pro/Enterprise are planned to be built in a *separate private repo* that consumes this one as an
> upstream core (one-way sync, decided but not yet built — see `docs/OPEN_CORE_REPO_STRATEGY.md`).
> **Don't add tier-check/licensing-gate logic to this repo** — that kind of logic belongs in the
> private repo once it exists, not here. If you're ever asked to add tier-gating directly to this
> codebase, that's a sign the request conflicts with the decided architecture — flag it rather than
> implementing it.
>
> ## When you're not sure whether to just fix something
>
> Mechanical, low-risk fixes (wrong error message, missing retry, an obviously dead branch) — fix
> directly. Anything that changes behavior a user might depend on, or that you can't verify in this
> environment, or that involves a real product/design tradeoff — flag it with a clear recommendation
> instead of applying it silently. `docs/IMPLEMENTATION_TRACKER.md` §1 is where open items needing a
> human decision live; add to it rather than deciding unilaterally.
>
> ## History
>
> This repo was consolidated from an earlier dual-tree setup (`qgis_ai_assistant` at
> `C:\qgis_ai_assistant`, which maintained a second synced copy under a different internal
> identity). See `CHANGELOG.md`'s `[1.4.0]` entry for what changed. Full commit history predating
> this repo lives in the old location, not here — this repo started from a fresh `git init`.

---

## 10. Product Requirements & Roadmap

Full detail in `CARTOGEN_AI_PRD.md` (frozen, dated 2026-08-08/2026-08-15) and
`CARTOGEN_AI_FEATURE_LIST.md` (frozen, dated 2026-08-15). Both are historical snapshots — see
[§12](#12-project-status--whats-open-right-now) for the current living status.

### 10.1 Original architecture gaps (v1 → v2), all resolved

- **Threading model** — `QgsTask`/`QThread` from Phase 1. **Done.**
- **Credential storage** — `QgsAuthManager`, not plaintext. **Done.**
- **Dependency bundling** — resolved differently than originally envisioned: a first-run
  `pip`/`subprocess` installer was built then deliberately removed (known QGIS-community
  anti-pattern), replaced with `plugin_dependencies=qpip` + `requirements.txt`.
- **Packaging & submission** — partially resolved: `plugin_upload.py` zips locally but does not
  upload to the QGIS Plugin Repository (manual submission still required). GPL v2 licensing
  decision is done.
- **Testing** — `pytest-qgis` as the standard harness was **not done**; tests use plain
  `unittest`/pytest against per-module `QGIS_AVAILABLE = False` fallback paths instead.

### 10.2 Feature roadmap by tier (from the original PRD's most-wanted-features research)

**Tier 1 — table stakes (all implemented):** natural language → QGIS Expression/Processing chain;
geometry & topology repair with diagnosis; CRS mismatch auto-detection; preview-before-apply for
destructive operations.

**Tier 2 — adoption drivers (all implemented):** smart symbology/classification suggestions;
conversational map interrogation; humanitarian data discovery & fetch assistant; auto-generated
metadata & lineage; print layout generation from natural language; explainability on every agent
action.

**Tier 3 — roadmap-stage differentiators:** semi-automated feature extraction from imagery
(**implemented** — `extract_features_from_imagery`); change detection between time-stamped
layers/images (**implemented**); accessibility/routing in plain language (**implemented** — real
road-network routing via `logistics_tools.py`); feedback loop/correction memory (**not started**);
multi-layer join assistant (**implemented** — `join_by_attribute`).

### 10.3 Phased roadmap status

- **Phase 1 (v0.1–v0.2):** ✅ done and exceeded — 78+ tools (started at 61), dual-layer memory,
  task-planning subagents, 8 providers (started at 3), `QgsTask` async, `QgsAuthManager`. Not done:
  `pytest-qgis` harness.
- **Phase 2 (v0.3):** mostly done — PostGIS querying (keyword-blocklist enforcement, DB-level
  read-only layer added later), print layouts, canvas selection, geometry/topology diagnosis,
  preview-before-apply, scheduled/recurring workflows (shipped 2026-08-16, in-session scope only —
  deliberately no `qgis_process` headless adapter or OS-scheduler registration). Partially done:
  saved-workflow re-editability (persists/restores, but no UI for editing a *completed* step).
- **Phase 3 (v0.4):** mostly done — STAC satellite fetchers (no caching/quota guard originally,
  since added), multimodal visual canvas inspection, change detection. Not started: voice-to-spatial
  commands.
- **Phase 4 (v1.0, vision):** not started — multi-agent spatial swarms, team GeoPackage memory sync
  (needs a concurrency/conflict-resolution model defined first), headless QGIS Server integration,
  feedback loop, multi-layer join assistant (**note: join assistant was actually shipped** as a
  Post-PRD Addition, ahead of this Phase 4 placement).

### 10.4 Notable bug fix chains documented in the feature list (representative examples)

- **Print layout tool** — a real live-testing session in QGIS surfaced a chain of 5 distinct bugs
  in one tool, each caught from an actual failing export: missing PNG/DPI/summary-panel support; a
  blank-rectangle rendering bug (`QgsLayoutItemMap` needs a nonzero placeholder rect via
  `setRect()` before `setExtent()`); a hard crash from a fabricated API call
  (`QgsLayoutItemPicture.ModeRaster` doesn't exist); the model bypassing the tool entirely despite
  fixes 1–3; and a cropped-export bug from capturing whatever partial extent the canvas happened to
  be at, fixed with an optional `zoom_to_layer` parameter.
- **Tool Retrieval Router recall gap** — measured against 9 realistic paraphrased queries, 33%
  never made it into the candidate set the model could choose from at all — fixed via a stable-sort
  tie-break bug fix, a curated alias list, and raising `top_k` from 30 to 40.
- **`zoom_to_layer`/`zoom_to_feature` CRS bug** — a layer's own-CRS extent was passed directly into
  `canvas.setExtent()`, which expects the extent in the *canvas's* CRS, silently landing the view
  near the map's coordinate origin whenever layer CRS ≠ project CRS (the common case for a fetched
  WGS84 boundary on a Web Mercator basemap project).

---

## 11. Known Issues & Bug Tracker

Full detail in [docs/BUG_TRACKER.md](docs/BUG_TRACKER.md) (living document). Summary as of this
document's generation date:

### 11.1 Open bugs

**None currently known.** Every real code defect found during this project's review history was
fixed in the same session it was found, verified via a real test run or direct execution, and
recorded either in `CHANGELOG.md` (pre-2026-08-21) or `docs/BUG_TRACKER.md` (2026-08-21 forward).

### 11.2 Known non-bugs (stable, understood, environment-specific — not regressions)

- `test_is_safe_url_accepts_public_host` (1 known test failure) — this sandbox's DNS/network egress
  can't resolve a public hostname the way a real deployment environment can. Not a code defect.
- 6 known errors in `tests/test_reporting_tools.py` — `PermissionError` on `os.remove()` cleanup for
  `scratch_test_*.csv/.docx/.pdf` files. This sandbox specifically cannot `rm`/unlink files matching
  that pattern once written. Not a code defect.
- **Files on the development sandbox's FUSE-mounted tree cannot be `rm`/unlink'd**, though a
  **same-filesystem `mv`/rename works fine** (only discovered 2026-08-21 while fixing a namespace
  collision bug — a cross-filesystem move still fails, since it falls back to copy+delete and the
  delete half is exactly the blocked unlink operation).

**Current baseline: 691 tests, 1 known failure + 6 known errors, 0 real defects.** Any different
count on a full suite run is real signal to investigate.

### 11.3 Recently fixed (chronological, most recent first)

| ID | Found | Fixed | Severity | Summary |
|---|---|---|---|---|
| BUG-2026-08-21-7 | 2026-08-21 | v1.4.1 | high | 15 leftover function-local `agent`/`ui` imports across 5 test files survived an earlier bulk rewrite; separately, the documented test command was missing `-t .`, silently skipping the `sys.path` bootstrap entirely. Both fixed; 691/691 baseline restored. |
| BUG-2026-08-21-6 | 2026-08-21 | v1.4.1 | high | `cartogen_ai.py` at the repo root collided with the new `cartogen_ai.core` namespace package — a regular module always wins over a namespace portion. Renamed to `plugin_main.py`. |
| BUG-2026-08-21-5 | 2026-08-21 | v1.2.34 | medium | Release zip silently shipped 7 stray repo-root files (test artifacts + a git scratch file) due to exact-name-only exclusion matching. Added pattern-based exclusion. |
| BUG-2026-08-21-4 | 2026-08-21 | v1.2.28 | medium | Gemini provider sent the API key as a query param instead of the `x-goog-api-key` header. |
| BUG-2026-08-21-3 | 2026-08-21 | v1.2.29 | medium | `calculate_area`/`calculate_length` mutated a layer's attribute table without the same confirmation gate `field_calculator` required for the identical class of operation. |
| BUG-2026-08-21-2 | 2026-08-21 | v1.2.33 | low | Route optimization prototype script missing a `scikit-learn` dependency line. |
| BUG-2026-08-21-1 | 2026-08-21 | v1.2.33 | medium | Route optimization prototype script called `ox.graph_from_bbox` with bbox arguments in the wrong order for the installed `osmnx` version. |

Full history before `docs/BUG_TRACKER.md` existed: see `CHANGELOG.md`, every version from v1.0.0
forward.

---

## 12. Project Status — What's Open Right Now

Full detail in [docs/IMPLEMENTATION_TRACKER.md](docs/IMPLEMENTATION_TRACKER.md) (living document —
the single place to check instead of cross-referencing every dated review doc).

### 12.1 Items needing a human decision (not an engineering call)

1. **Destructive-action confirmation gate for 4 humanitarian analysis tools** —
   `calculate_severity_index`, `calculate_damage_exposure_severity`, `calculate_population_in_need`,
   `calculate_presence_gap` write a field in place, the same mutation category as tools that already
   require preview/confirm, but currently don't. Three options laid out (leave as-is since they're
   idempotent; add the gate for consistency; narrow `SECURITY.md`'s stated scope instead) —
   needs a product/UX call on the friction-vs-consistency tradeoff.
2. **`ui/dock_widget.py` (now `src/cartogen_ai/core/ui/dock_widget.py`) class split — execution.**
   Fully planned (`ChatTabWidget`/`TasksTabWidget` extraction), but cannot safely be done from a
   sandbox that can't import or visually verify Qt-dependent code — needs a real QGIS session, not
   a decision from anyone.
3. **Tier restructure licensing path.** The proposed Community ("locked source")/Pro
   (closed)/Enterprise structure in `docs/TIER_RESTRUCTURE_PROPOSAL_2026-08-20.md` is not achievable
   as a simple feature flag on the current GPL v2 codebase. Needs real legal counsel, then a
   business decision — not something to build toward until resolved.

### 12.2 Items blocked on environment, not a decision or a bug

- **Live-QGIS verification pass** — every tool is "correct per the code and test suite," not
  "confirmed working in a real QGIS session." The single largest standing gap across every review
  round. `docs/RELEASE_SMOKE_TEST.md` exists to make this a bounded, ~15-minute human task.
- **`generate_html_dashboard` connectivity requirement** — carried forward, no new information.
- **Repo rename / GitHub collaborator items** — external GitHub actions, not actionable from a
  sandbox.

### 12.3 Deliberately deferred (a stated design choice, not a gap)

- `docs/JIAF_MULTISECTOR_COMPOSITE_SPEC.md` — spec-only; needs a real JIAF Mosaic Method
  human-validation workshop a formula can't substitute for.
- `docs/ROUTE_RISK_AND_NOGO_ZONES_SPEC.md` §3.3 (no-go zones) — prompt-guidance-only by design.

### 12.4 Recently resolved (for traceability)

4 duplicate tool registrations removed (tool count corrected to 131); raster styling gap closed
(`apply_raster_stretch`); provider client bugs fixed (Gemini header auth, Ollama retry logic);
`CONTRIBUTING.md` written; `docs/RELEASE_SMOKE_TEST.md` written and verified accurate; session
token/cost usage visibility added to the chat UI; `ui/attachments.py` extracted from the dock widget
(file-parsing half of the split plan); `docs/route_optimization_prototype.py` smoke-tested with 2
real bugs found and fixed; the full MultiTier namespace-package restructure completed and verified
(see [§3](#3-architecture) and [§11](#11-known-issues--bug-tracker)).

---

## 13. Repository Map & Documentation Index

### 13.1 Full documentation table

| Doc | Covers |
|---|---|
| [docs/USER_GUIDE.md](docs/USER_GUIDE.md) | Chat, Task Manager, memory, file attachments, settings |
| [docs/TOOLS_REFERENCE.md](docs/TOOLS_REFERENCE.md) | All 131 tools, auto-generated from the live registry |
| [docs/PRODUCT_TIERS.md](docs/PRODUCT_TIERS.md) | Editions/pricing tiers, target clients, verticals — shipped vs. roadmap |
| [docs/OPEN_CORE_REPO_STRATEGY.md](docs/OPEN_CORE_REPO_STRATEGY.md) | Decided (not yet built): public repo stays open Community core, Pro/Enterprise built in a separate private repo, one-way sync, license-key-gated distribution |
| [docs/MULTITIER_REPO_ARCHITECTURE_SPEC.md](docs/MULTITIER_REPO_ARCHITECTURE_SPEC.md) | Technical spec: `src/cartogen_ai` namespace package layout, QGIS loading path, sync-workflow history-protection details, distribution channels per edition |
| [docs/PROMPT_REFINEMENT_LAYER_SPEC.md](docs/PROMPT_REFINEMENT_LAYER_SPEC.md) | Optional interactive prompt-refinement step before agent processing (shipped) |
| [docs/ROUTE_OPTIMIZATION_STRATEGY.md](docs/ROUTE_OPTIMIZATION_STRATEGY.md) | Closing the accuracy gap in routing tools, plus a standalone OSMnx/NetworkX prototype |
| [docs/ROUTE_RISK_AND_NOGO_ZONES_SPEC.md](docs/ROUTE_RISK_AND_NOGO_ZONES_SPEC.md) | Roadmap spec: incident trends, route-vs-incident risk scoring, no-go zones |
| [docs/AUTO_REPORTING_RECIPE.md](docs/AUTO_REPORTING_RECIPE.md) | Zero-new-code recipe: scheduled program-update workflow composition |
| [docs/CVA_MARKET_ACCESS_RECIPE.md](docs/CVA_MARKET_ACCESS_RECIPE.md) | Zero-new-code recipe: market-access distance analysis for cash/voucher assistance |
| [docs/JIAF_MULTISECTOR_COMPOSITE_SPEC.md](docs/JIAF_MULTISECTOR_COMPOSITE_SPEC.md) | Roadmap spec: intersectoral severity estimate, grounded in JIAF 2.0's Mosaic Method |
| [SECURITY.md](SECURITY.md) | Threat model, protections, adversarial testing results, known limitations |
| [docs/STATUS_REVIEW_2026-08-20.md](docs/STATUS_REVIEW_2026-08-20.md) | Frozen full-codebase status review |
| [docs/TIER_RESTRUCTURE_PROPOSAL_2026-08-20.md](docs/TIER_RESTRUCTURE_PROPOSAL_2026-08-20.md) | Frozen proposal, not decided/shipped |
| [docs/ENGINEERING_PRODUCT_UX_REVIEW_2026-08-20.md](docs/ENGINEERING_PRODUCT_UX_REVIEW_2026-08-20.md) | Frozen specialist product/engineering/UX review |
| [docs/RELEASE_SMOKE_TEST.md](docs/RELEASE_SMOKE_TEST.md) | ~15-minute manual checklist for a real QGIS session before each release |
| [docs/DESTRUCTIVE_TOOLS_AUDIT_2026-08-21.md](docs/DESTRUCTIVE_TOOLS_AUDIT_2026-08-21.md) | Frozen audit of preview/confirm gate coverage |
| [docs/DOCK_WIDGET_SPLIT_PLAN_2026-08-21.md](docs/DOCK_WIDGET_SPLIT_PLAN_2026-08-21.md) | Frozen plan for the dock widget class split |
| [docs/IMPLEMENTATION_TRACKER.md](docs/IMPLEMENTATION_TRACKER.md) | **Living** — start here for "what's open right now" |
| [docs/BUG_TRACKER.md](docs/BUG_TRACKER.md) | **Living** — in-repo bug tracker |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Codebase conventions: comment discipline, honest status labeling, testing |
| [CLAUDE.md](CLAUDE.md) | AI-coding-agent orientation (reproduced in full in [§9](#9-ai-agent-instructions-claudemd-full-text)) |
| [CHANGELOG.md](CHANGELOG.md) | **Living** — full version history |
| [LICENSE](LICENSE) | GNU GPL v2 |
| [LICENSE_AUDIT.md](LICENSE_AUDIT.md) | Dependency/API license compliance audit |
| [CARTOGEN_AI_PRD.md](CARTOGEN_AI_PRD.md) | Frozen engineering PRD/roadmap |
| [CARTOGEN_AI_FEATURE_LIST.md](CARTOGEN_AI_FEATURE_LIST.md) | Frozen implementation-reality matrix |

### 13.2 Codebase organization

- `src/cartogen_ai/core/agent/` — provider clients (`providers/`), tools (`tools/`), the
  tool-calling loop and dispatcher (`agent.py`), task/memory management.
- `src/cartogen_ai/core/ui/` — the dock widget, settings dialog, canvas highlighting.
- `tests/` — unit tests, runnable outside QGIS.
- `docs/` — user guide, tool reference, specs/proposals, and living trackers (§13.1 above).
- `service/` — a standalone hosted-gateway/monetization prototype for the planned Professional tier.
  Not part of the QGIS plugin itself; excluded from the release zip.
- `branding/` — brand guidelines and logo assets.
- `plugin_main.py`, `__init__.py` — QGIS plugin entry point and main class, at the repo root (see
  [§3](#3-architecture) for why they're not under `src/`).

### 13.3 Support

Internal/commercial use — for issues or questions, contact
[alaa.alshoubaki@gmail.com](mailto:alaa.alshoubaki@gmail.com).

---

*End of consolidated documentation. Individual source docs listed in §13.1 remain the
living/authoritative reference for their own topics.*
