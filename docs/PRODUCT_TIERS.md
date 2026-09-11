# Cartogen AI — Editions & Business Model

**Status:** Product/business positioning document. Distinct from `docs/archive/CARTOGEN_AI_PRD.md` (engineering
requirements) and `docs/archive/CARTOGEN_AI_FEATURE_LIST.md` (implementation reality matrix) — this document
exists to keep the *business* framing (pricing tiers, target clients, verticals) equally honest about
what's actually shipped versus what's planned, since those two things drift apart easily otherwise.

**Last updated:** 2026-08-31. Every "Shipped today" claim below was checked against the live codebase
(131-tool registry, `agent/`, `ui/`) at that date, not carried forward from an earlier draft. (Was
stamped "125-tool registry" through 2026-08-15 -- stale; the registry has been 131 since the
duplicate-registration cleanup noted in `docs/IMPLEMENTATION_TRACKER.md` §4.)

**Tool-count correction, 2026-09-12:** the registry has grown to 165 tools since 2026-08-31 (see
`docs/TOOLS_REFERENCE.md` for the current, auto-generated count) -- this note fixes only the
number, not a full re-verification of every other claim in this document against the current
codebase, which hasn't been done as part of this pass.

---

## The Open Core model

Cartogen AI is structured as three tiers, aimed at progressively larger/more institutional users:

1. **Community** (free, GPL v2) — the field responder and independent consultant.
2. **Professional** (~$20/month, "Cloud Connect Gateway") — the regional GIS analyst / SME.
3. **Enterprise** (custom SLA) — the institutional partner (major crisis-response networks, defense,
   large public-sector agencies).

**Only the Community tier exists today.** Everything this plugin currently does — all 165 tools, every
provider integration, every security protection in `SECURITY.md` — is Community-tier functionality,
shipped under GPL v2, with no backend service, no billing system, no accounts, and no per-tier feature
gating anywhere in the code. Professional and Enterprise below describe target packaging for
capabilities that would need to be built; none of their headline features (a hosted gateway, RBAC,
SSO, SharePoint/Power BI push) exist in the repository as of this writing. Where a described capability
overlaps with something already planned in `docs/archive/CARTOGEN_AI_PRD.md`'s roadmap, that's cross-referenced
below.

**Where the code for Professional/Enterprise will actually live:** this repo stays the single,
public, GPL v2 Community codebase — it does not become a multi-edition codebase with tier-gating
logic inside it. Professional and Enterprise are planned to be built in a *separate, private* repo
that consumes this one as an upstream core, not forked from or merged into it. See
`docs/archive/OPEN_CORE_REPO_STRATEGY.md` for the decided (not yet built) repo/sync/distribution plan —
that document also resolves the licensing tension flagged just below.

> **2026-08-20 — proposal under consideration, not yet decided or merged:**
> `docs/archive/TIER_RESTRUCTURE_PROPOSAL_2026-08-20.md` sketches a different split — **Community** (77 of
> 134 tools, connectivity capped to Local LLM + a Cartogen-operated API gateway, "open source"
> branded but source **locked**), **Pro** (full 134-tool registry, same connectivity cap, **closed**
> source), and **Enterprise** (full 134-tool registry, all connectivity options including direct BYOK
> to OpenRouter/Gemini/Claude/OpenAI, closed source). It replaces the Professional tier below and
> reframes Enterprise around connectivity rather than the RBAC/SSO/private-enclave features described
> in §3 below (those remain a separate, additive, still-entirely-unbuilt axis). **The Community/Pro
> "locked"/"closed" source framing is a real departure from this project's current GPL v2 license
> (see `LICENSE`, and `version=`/`license=` in `metadata.txt`) and needs a licensing decision before
> it's actionable — see the proposal doc §3, which flags this explicitly and is not a substitute for
> real legal counsel.** Grounded in `service/`'s already-partially-built gateway prototype. That
> document is a draft for a decision, not a settled fact — this file still reflects what's actually
> shipped (Community only, GPL v2, everything below) until a direction is picked and merged in.

---

## 1. Community Tier — Field Responder & Independent Consultant (free)

**Who they are:** Field officers, emergency responders, and freelance GIS consultants operating in
austere or off-grid environments.

**What's actually shipped and matches this persona:**

- **Fully offline execution via Ollama.** `agent/providers/ollama.py` talks to a local REST endpoint;
  no API key, no outbound request to any cloud provider required. Combined with the plugin's own
  security posture (`SECURITY.md`), a user on Ollama can run geometry diagnostics, spatial queries, and
  most of the tool registry without a single packet leaving the machine — the one honest caveat is that
  tools which are *inherently* network-dependent (HDX/OSM/geoBoundaries fetches, web search, satellite
  imagery search) still need connectivity when actually invoked; offline-first means "the AI reasoning
  loop itself needs no cloud," not "every tool works with no network ever."
- **GPL v2, free to use and modify** (`LICENSE`), no account or license key of any kind.
- **The full 165-tool registry**, not a limited/gated subset — including the humanitarian-specific
  tooling (severity indexing, geoprivacy obfuscation, 3W/4W presence-gap analysis) this document's
  vertical framing leans on.
- **Bring-your-own API key** for OpenRouter, Gemini, OpenAI, or Claude when a user *does* have
  connectivity and wants a cloud model — again, no gateway, no proxy, no plugin-side billing; the key
  goes straight from the user's own account to the provider.

**What's described in the original framing but not accurate as stated:** none — the Community tier as
described matches the shipped product closely. The one correction worth making is scope: "run geometry
diagnostics without sending a single packet over the internet" is true for the reasoning loop and
local-geometry tools, not a blanket claim about every tool in the registry.

---

## 2. Professional Tier — Regional GIS Analyst & SME (target: ~$20/month) — **ROADMAP, NOT SHIPPED**

**Who they are:** GIS specialists and data analysts at regional NGO/government hubs or mid-sized
engineering/logistics firms, who want cloud-model power without managing their own API keys or rate
limits.

**What this tier's value proposition requires, and its actual status:**

| Claimed capability | Status |
|---|---|
| "Cloud Connect Gateway" — frictionless cloud LLM access without the user managing their own API key/rate limits | **Not built.** No gateway, proxy, or plugin-hosted credential-sharing service exists anywhere in `agent/providers/`. Today, a user who wants a cloud model must obtain and paste in their own API key (`ui/settings_dialog.py`) — exactly the friction this tier is meant to remove. Building this means standing up and operating a real backend service (auth, per-user usage metering, a proxy to each LLM provider, billing) — a materially different engineering effort than anything in the current single-user desktop plugin. |
| Automated A3/A4 SitRep generation | **Shipped**, via `create_print_layout` + `generate_report`. Already Community-tier functionality, not something that needs gating behind a paid tier as currently built. |
| Pull humanitarian data from HDX/OSM | **Shipped** (`search_hdx_datasets`, `fetch_osm_features`, `fetch_geoboundaries`, `fetch_hdx_admin_boundaries`). Also already Community-tier. |
| Extract structured data from PDF/Word attachments into charts | **Shipped** (`extract_pdf_tables`, `extract_word_tables`, `aggregate_data`, `generate_chart`). Also already Community-tier. |

**The real gap for this tier is narrow but non-trivial: everything *except* the gateway itself is
already built and already free.** As shipped today, there is no functional reason a Community-tier user
would need to pay $20/month — the actual paid value would have to come entirely from "we manage the
API key/billing relationship for you," which means the Cloud Connect Gateway is not an enhancement to
the plugin but a prerequisite for this tier having any paid value proposition at all.

**Where this connects to the existing PRD roadmap:** `docs/archive/CARTOGEN_AI_PRD.md` §5.1 already flags "live,
synced data connections" (PostgreSQL, Google Sheets, CSV) as a portable idea from the Atlas competitive
review, scoped for Phase 2. A hosted gateway is a related but distinct piece of infrastructure (model
access, not data access) and isn't currently represented in that roadmap — worth adding explicitly if
this tier is prioritized.

---

## 3. Enterprise Tier — Institutional Partner (custom SLA) — **ROADMAP, NOT SHIPPED**

**Who they are:** Operations directors/IT leads at major crisis-response networks, defense
organizations, or large public-sector agencies (e.g. USAID, UNHCR, IOM-scale institutions).

| Claimed capability | Status |
|---|---|
| Private data enclaves, zero-retention policies | **Not built.** There is no hosted data-storage layer of any kind today — the plugin runs entirely client-side against the user's own QGIS project and local/cloud provider calls made directly from their machine. "Zero retention" is currently true only in the trivial sense that there's no plugin-side backend to retain anything on; a real zero-retention *policy* implies a hosted service with a stated data-handling contract, which doesn't exist yet. |
| RBAC (Role-Based Access Control) | **Not built.** No user/role/permission model anywhere in the codebase — every installation is single-user by construction (`QgsSettings`/`QgsAuthManager`-backed local config, no concept of "users" at all). |
| SSO/SAML integration | **Not built.** No auth layer exists to integrate SSO into — this would need to be built alongside whatever backend service RBAC and the Professional-tier gateway also depend on, not as an independent add-on. |
| Push generated maps/metadata to SharePoint Document Sets, Power BI dashboards | **Not built.** No Microsoft 365/Graph API integration exists in `agent/tools/` or anywhere else in the codebase. The closest existing capability is local export (`export_layer`, `generate_report`, `generate_html_dashboard`) — genuinely useful, but manual, not an automated push to a corporate ecosystem. |
| Fail-closed, secure database querying | **Shipped**, and already documented in depth in `SECURITY.md` §2: `execute_read_only_sql` enforces read-only at both a keyword-blocklist layer and a real DB-level `READ ONLY` transaction that fails closed if the guarantee can't be confirmed. This is a genuine, already-strong selling point for the defense/intelligence vertical below — it just isn't Enterprise-gated today, it's available to every Community-tier user. |
| Offline-first architecture | **Shipped** (see Community tier above) — also not currently gated, and arguably a stronger differentiator for defense/disconnected-ops buyers than anything Enterprise-specific listed here. |

**Bottom line for this tier:** the two capabilities enterprise buyers in this space actually care about
most on security grounds (fail-closed SQL, offline execution) are real and already shipped — but
they're not fenced behind anything, so there's currently no product mechanism to sell them as an
Enterprise differentiator. Everything that *would* need to be Enterprise-exclusive (RBAC, SSO, private
enclaves, M365 push) requires backend infrastructure that doesn't exist. This tier is the largest gap
between the business framing and the current codebase of the three.

**Where this connects to the existing PRD roadmap:** `docs/archive/CARTOGEN_AI_PRD.md` §6 Phase 4 already lists
"Team GeoPackage memory synchronization" (explicitly flagged as needing a concurrency/conflict-resolution
model before implementation) and "Headless QGIS Server AI agent integration" — both are Enterprise-shaped
capabilities in spirit (multi-user, server-side) but neither was previously connected to a concrete
business tier or the RBAC/SSO/M365 requirements listed here.

---

## 4. Industry verticals — accuracy check

| Vertical | Real, shipped differentiators | Aspirational (not shipped) |
|---|---|---|
| **Humanitarian & crisis response** | Native HDX, OSM Overpass, geoBoundaries, HDX COD-AB (P-codes), OCHA FTS, WorldPop integrations; `calculate_severity_index`, `calculate_presence_gap`, `obfuscate_sensitive_points`, `load_3w_data` — a genuinely deep, verified tool set for this vertical specifically (see `docs/archive/HUMANITARIAN_GIS_FEATURE_REVIEW.md`). This is the strongest, most accurate claim in the whole positioning document. | None identified — this vertical's claims hold up well against the actual code. |
| **Defense & intelligence** | Offline-first (Ollama) execution; fail-closed read-only SQL enforcement (`SECURITY.md` §2); an AST-based execution sandbox for model-generated PyQGIS (`SECURITY.md` §1) with a documented, adversarially-tested threat model — a real, differentiated security story. | The framing implies this is an *Enterprise-tier* selling point, but as noted above these protections are actually available in the free Community tier today. Nothing about the current security architecture is defense-specific (no classification handling, no air-gapped deployment tooling, no compliance certifications) — it's general-purpose defense-in-depth, valuable to this vertical but not built *for* it. |
| **Local government & urban planning** | `zonal_statistics`, `estimate_population_exposure` (WorldPop), `create_print_layout`, the full raster/vector geoprocessing suite. | No municipal-specific tooling (zoning-code-aware analysis, permit workflow integration, cadastral-specific tools) exists — the fit is via general-purpose GIS capability, not purpose-built features for this vertical. |

---

## 5. Summary for anyone reading this to make a decision

If this document is being used to write marketing copy, brief a sales conversation, or plan near-term
engineering work, the load-bearing fact is: **today, Cartogen AI is a single tier.** It is a strong,
independently-verified Community-tier product — the humanitarian vertical claims in particular are
unusually well-substantiated for a plugin at this stage. Professional and Enterprise are a real,
reasonable target architecture, but Professional's entire paid value proposition rests on one unbuilt
piece (the gateway), and Enterprise's rests on several (RBAC, SSO, private enclaves, M365 integration) —
none of which share much engineering surface with the current single-user desktop plugin. Positioning
copy aimed at Professional/Enterprise buyers should describe these as an intended direction, not
present-tense capability, until that backend work exists.
