# Cartogen AI — Tier Restructure Proposal (2026-08-20)

**Status: PROPOSAL ONLY. Nothing in this document is built.** Requested directly by the user to
replace the Community/Professional/Enterprise framing in `docs/PRODUCT_TIERS.md` (2026-08-15) with
a new two/three-way split built around a Cartogen-operated model gateway. This doc is deliberately
kept separate from `PRODUCT_TIERS.md` rather than overwriting it, because `PRODUCT_TIERS.md`'s own
stated job is to track *shipped reality* — this is a draft for a decision, not yet a settled fact
about the product. Once a direction is picked, the relevant parts should be merged into
`PRODUCT_TIERS.md` and this file retired or marked historical.

**Correction addendum (2026-08-31, later pass):** this document's "134 tools" figure (used
throughout, including the proposed 77/57 Community/Pro split and the "verified against the
live 134-tool registry" claim in §6) is now stale -- the registry is **131 tools** as of
2026-08-31 (see `docs/TOOLS_REFERENCE.md`, auto-generated from the live registry). Per this
project's frozen-doc convention (`CONTRIBUTING.md` §2), the body below is left exactly as
originally written rather than silently rewritten to match current reality -- the 77/57 split
was this proposal's own reasoning at the time, not a fact to retroactively correct. See
`docs/IMPLEMENTATION_TRACKER.md` §1.3 for what's actually still open on this proposal.

## 0. Reading the request — now a 3-way split with a source-availability axis added

The request has evolved across three rounds of this proposal. Restating the latest instruction in
full, since it changes the shape of the whole document, not just a detail:

> "Community opensource but the source is locked, Local LLM and Cartogen API, limited features —
> make a balance of the features that will make the user shift to Pro or Enterprise. Pro: closed
> code, full features, Local LLM and Cartogen API. Enterprise: full features, full connectivity.
> Total 3 versions."

Two things changed from the previous draft:

1. **Connectivity structure is confirmed and unchanged**: Community and Pro are both capped to
   **Local LLM + Cartogen API gateway only**; Enterprise alone gets **full connectivity**,
   including direct BYOK to OpenRouter/Gemini/Claude/OpenAI. This matches the previous round's
   resolution (§3 below) — no change needed there.
2. **A new axis appears that this proposal never addressed before: source-code availability.**
   Community is described as "open source but the source is locked" and Pro as "closed code."
   Previously this document assumed all three tiers ship from the same GPL v2 source, differing
   only by which tools/providers are enabled at runtime — the same mechanism `build_cartogen_ai.py`
   already uses to produce two differently-branded builds from one tree. **"Locked" or "closed"
   source is a materially different, and materially harder, requirement: it means the source is
   not distributed at all, or distributed under terms that prevent recipients from redistributing
   or modifying it — not a runtime feature flag.** This has real licensing implications for the
   *current* shipped product, covered in §3 below before the tier table, because it's the one part
   of this request most likely to need a decision from someone other than an engineer before any
   of the rest is actionable.

## 1. Why gate connectivity this way (the business logic, made explicit)

Funneling both paid-adjacent tiers through Cartogen's own gateway is a coherent, common Open-Core
SaaS pattern: it keeps usage on infrastructure Cartogen controls and can meter/monetize (even a
free Community quota through the gateway is still Cartogen's infrastructure, not a cost-free pass-
through to OpenRouter et al.), while Local LLM stays available as the genuinely-free, genuinely-
offline option for users who don't want to pay for any cloud inference at all. Direct BYOK to the
four commercial APIs bypasses Cartogen's gateway entirely — no metering, no revenue capture, no
usage visibility — which is exactly the kind of capability that makes sense to reserve for a
top/self-hosted tier aimed at institutions who'd rather manage their own provider relationships
than route sensitive prompts through a third party's proxy at all.

## 2. Grounding: what already exists toward the Cartogen API gateway

Not starting from zero. `service/` in this repo is an already-scaffolded, partially-built
prototype for exactly this:

- `service/gateway/` — a [LiteLLM Proxy](https://github.com/BerriAI/litellm) config. Sits in front
  of real provider keys and issues a **virtual API key per client**, each with its own budget/rate
  limit — the mechanism a tiered gateway needs.
- `service/website/` — a small Express app: pricing page, Stripe Checkout, a webhook that turns a
  completed payment into a LiteLLM virtual key.
- `service/data/` — a placeholder JSON file standing in for a real customer↔key database.

Its own README is explicit about what's still missing before this is real, in order:
persisting the customer↔key mapping in a real database (not JSON), emailing the key instead of
showing it on a webpage, mapping Stripe price IDs to per-tier budgets/rate limits (currently one
flat plan — would need at least a Community-quota plan and a Pro plan), handling subscription
update/cancellation to change or revoke keys, adding auth to the website itself, and — the item
that matters most for this proposal — **"pointing the actual QGIS plugin at this gateway as a
provider option,"** which doesn't exist: there is no `agent/providers/cartogen.py` today, only
`openrouter.py`, `gemini.py`, `openai.py`, `claude.py`, `ollama.py`.

This means "Cartogen API (pending completion of API gateway)" isn't a hypothetical — it's a real,
identifiable, partially-built piece of work with a known punch list. Worth cross-referencing this
proposal against `service/README.md` directly when scoping the engineering work in §6.

## 3. Proposed tier structure

**Licensing note — this needs a decision before anything below is actionable, and it's not an
engineering decision.** (Not legal advice — flagging what the license terms say, not recommending
what to do about it; get real counsel before finalizing.) Today, this whole repository is
distributed under **GNU GPL v2** — stated in `README.md`, `metadata.txt`, and `LICENSE`, and
pushed to a public GitHub repository (`repository=` in `metadata.txt`). GPL v2 is copyleft: it
requires that anyone who receives a distributed copy (source or compiled) also receives, or can
obtain, the corresponding source, and it grants them the right to further copy, modify, and
redistribute that source. **A tier that is "open source" in name but has its source "locked," and
a tier that is explicitly "closed code," are not things you can build by taking the current GPL v2
codebase and adding a feature flag** — that combination isn't legally coherent under the license
this project is under today. There's also a QGIS-specific wrinkle worth naming, not resolving
here: QGIS itself is GPL v2+, and the QGIS plugin ecosystem's long-standing norm (similar to
WordPress plugins) treats plugins that link against `qgis.core`/PyQGIS as combined works expected
to ship under a GPL-compatible license — whether a closed-source Pro/Enterprise build of *this*
plugin is distributable at all is a real open question this document can't answer. Concretely,
this means one of a few different paths has to be chosen, not assumed:

- **Re-license away from GPL v2 entirely** — drop the "open source" framing for Community too,
  and market it as free-to-use, source-available-or-not, under different terms.
- **Split the codebase**: keep a genuinely GPL v2 "core" (the base agent loop, QGIS integration
  shell) public and modifiable, while specific tool modules or the Cartogen provider client ship
  only as compiled/obfuscated artifacts under a separate, proprietary license and are never pushed
  to the public repo — the common "open core" pattern, and the one that most naturally supports
  "Community: open source but locked" language (the parts that *are* published stay real GPL v2;
  the locked parts were never published in the first place).
- **Keep everything GPL v2, drop "locked"/"closed" language** — ship all three tiers from the same
  open source, and gate purely on runtime feature flags/tier license as this document's earlier
  drafts assumed. Legally simplest, but doesn't match what was asked for here.

The tier table below describes the *product* shape requested (tool set, connectivity, and intended
source-distribution posture per tier) — it does not resolve which of the above paths gets there,
because that's not a call this document can make.

| | **Community** (free) | **Pro** (paid) | **Enterprise** (paid, top tier) |
|---|---|---|---|
| Price | Free | Paid, tier TBD | Highest tier — custom/institutional pricing |
| Source availability | "Open source" branding, but **locked** — not freely redistributable/modifiable as distributed (see licensing note above) | **Closed** — proprietary, no source distributed | Closed — proprietary, no source distributed |
| Tool set | Limited, deliberately balanced to create upgrade pressure (see §4) | Full 134-tool registry | Full 134-tool registry, all features |
| Local LLM (Ollama) | Yes | Yes | Yes |
| Cartogen API gateway | Yes (capped quota/rate-limited) | Yes (higher quota) | Yes |
| Direct BYOK: OpenRouter/Gemini/Claude/OpenAI | **No** | **No** | **Yes** |
| Who it's for | Individual/field users trying the product, casual GIS tasks | Paying individual/small-team users who want the full toolkit but are fine routing through Cartogen's gateway | Institutions with existing provider contracts, data-residency constraints, or who want direct control over which model backend handles their prompts |

This replaces the old Community/Professional/Enterprise framing from `PRODUCT_TIERS.md`
(2026-08-15) in one structural way worth calling out: previously, *Professional* was pitched as
"Community plus a convenience gateway," with Community keeping full direct BYOK. Under this new
structure, direct BYOK moves *up* to become Enterprise's differentiator, and the gateway becomes
the default path for both lower tiers instead of an add-on. That's a real reversal of which
capability is the "premium" one, worth being deliberate about since it changes the pitch to
existing users (see §7).

**Relationship to `PRODUCT_TIERS.md`'s existing Enterprise section:** that document's current draft
Enterprise tier (2026-08-15) is built around RBAC, SSO/SAML, private data enclaves, and SharePoint/
Power BI push — organizational/compliance features, not connectivity. Nothing in that list conflicts
with the connectivity-based Enterprise tier proposed here; they're additive; a real Enterprise
offering plausibly ends up being *both* — full tool set, all connectivity options including direct
BYOK, *and* the RBAC/SSO/private-enclave layer once that's built. This proposal only speaks to the
connectivity/tool-set axis; the RBAC/SSO/enclave axis from the existing document is untouched and
still entirely unbuilt (see that document's own status table).

## 4. Proposed Community vs. Pro tool split

This round's instruction changes the design goal for this split: not "how much can Community keep
without feeling crippled" (the previous draft's litmus test), but **"balance the features so
Community stays useful enough to hook someone, while the gap to Pro is the thing that makes them
pay."** Two different tests, and this section is revised around the second one.

The core structural call carries over unchanged: this project's two strongest, most-differentiated
capability areas (humanitarian data/logistics and predictive/decision-support analysis — see
`docs/HUMANITARIAN_GIS_FEATURE_REVIEW.md`) stay Pro-exclusive, since those are exactly the
features an individual/casual user is least likely to need and an institutional/paying user is
most likely to want. What's new this round: two additional, deliberate moves designed specifically
as upgrade triggers rather than category-boundary consequences —

- **`generate_chart` moves to Pro.** In the previous draft this was Community's only
  insight-generating tool (everything else in Community is raw geoprocessing/export). Removing it
  means a free-tier user who wants to turn their analysis into a chart hits a wall at exactly the
  moment they'd value the product most — a sharper, more specific upgrade trigger than a generic
  "more tools" pitch.
- **`geocode_batch` moves to Pro; `geocode_and_enrich` (single-address) stays Community.** A
  scale-based split: one-off geocoding stays free, bulk/batch geocoding — the version someone
  processing a real caseload or dataset actually needs — is paid. This is a common, well-understood
  freemium lever (single vs. bulk) rather than an arbitrary feature cut.

**Community (proposed: 77 of 134 tools, recomputed from the previous script-verified 79 after the
two moves above)** — everyday GIS copilot:

- **Task & Memory Management** — all 5 (`create_plan`, `set_task_preview`, `store_global_memory`,
  `store_project_memory`, `update_task`). Core UX, not a feature to gate.
- **Vector & Geoprocessing** — 43 of 44, all except `obfuscate_sensitive_points` (moved to Pro —
  tied to protection-sensitive humanitarian point data, an institutional use case, not
  general-purpose).
- **Raster** — the common/lightweight ops: `calculate_ndvi`, `calculate_ndwi`, `calculate_ndre`,
  `hillshade`, `slope_analysis`, `aspect_analysis`, `raster_clip`, `mosaic_rasters`,
  `band_composite`, `histogram_equalization`.
- **Styling & Labeling** — all 8 except `hotspot_analysis` (a spatial-statistics/density-analysis
  tool that only lives in this category by cartographic convention, not a styling operation).
- **Export & Reporting** — the basics: `export_to_csv`, `export_layer`, `print_map` (plus their
  currently-duplicate aliases `generate_csv`/`export_attribute_table`/`generate_map_image` — see
  `docs/STATUS_REVIEW_2026-08-20.md` §3/§7 on removing those duplicates regardless of tiering).
- **Project Management** — both (`load_project`, `save_project`).
- **System, Search & Scripting** — `search_web`, `geocode_and_enrich` (single-address; batch moves
  to Pro, see above).
- **Reporting & Document Analysis** — none (moved entirely to Pro, see above).
- **Humanitarian Data (HDX / OSM / geoBoundaries)** — `add_point_layer` only (a generic
  point-layer tool that happens to live in this category; the actual HDX/OSM/geoBoundaries/FTS/
  WorldPop fetchers move to Pro).

**Pro-exclusive (proposed: 57 of 134 tools)** — the institutional/humanitarian/advanced toolkit:

- **Humanitarian Data (HDX / OSM / geoBoundaries)** (8 of 9) — `add_incident_point`, `fetch_building_footprints`,
  `fetch_fts_funding_data`, `fetch_geoboundaries`, `fetch_hdx_admin_boundaries`,
  `fetch_osm_features`, `fetch_worldpop_population`, `search_hdx_datasets`.
- **Humanitarian Logistics** — all 7 (hub siting, service areas, travel-time matrices, VRP-lite
  routing, route risk scoring).
- **Data Analysis & Prediction** — all 6 (severity/needs indices, presence-gap, population-in-need,
  damage exposure, incident-trend forecasting, generic trend forecasting).
- **AI Imagery Feature Extraction** — `extract_features_from_imagery` (compute-heavy, needs the
  optional `torch`/`ultralytics` dependency group).
- **Satellite Imagery & Vision** — all 3.
- **Monitoring & Scheduling** — all 4 (recurring workflows — an operational/automation feature
  that fits a paid tier's "keep running after you close the laptop" value naturally).
- **Database & Workflows** — all 3 (SQL queries, workflow presets — technical/institutional).
- **Raster** (9 of 19 — the heavier/advanced ops) — `weighted_overlay_analysis`,
  `interpolate_surface`, `zonal_statistics`, `elevation_profile`, `georeference_image`,
  `estimate_population_exposure`, `pan_sharpening`, `supervised_classification`,
  `unsupervised_classification`.
- **Print Layouts** — `create_print_layout` (professional sitrep/report composition).
- **Export & Reporting** (3 of 9 — the "deliverable" tools, as opposed to Community's basic
  export/CSV tools above) — `generate_html_dashboard`, `generate_report`, `generate_spatial_report`.
- **Reporting & Document Analysis** (6 of 6, all) — `generate_chart`, `aggregate_data`,
  `extract_pdf_tables`, `extract_word_tables`, `generate_sector_coverage_report`, `load_3w_data`.
- **System, Search & Scripting** (4 of 6) — `execute_pyqgis_script` (highest support/risk surface
  in the registry — see `SECURITY.md` §1's own framing of it as "arbitrary-file-I/O-capable, with
  the interpreter-escape and process/network vectors specifically closed," not a fully contained
  sandbox), `gemini_grounded_search`, `openai_grounded_search`, `geocode_batch` (bulk geocoding —
  see the scale-based split above).

Every category label and tool name above was pulled and cross-checked directly against the live
`docs/TOOLS_REFERENCE.md` (script-parsed, not hand-counted) to confirm the 77/57 split sums to 134
with no tool missing, duplicated, or misfiled between the two tiers — including catching and fixing
two labeling issues from the previous draft: "Professional deliverables" and "Advanced Raster" /
"Advanced scripting/search" were subcategory names this document invented, not real categories —
those tools actually belong to the real `Export & Reporting`, `Raster`, and `System, Search &
Scripting` categories respectively (same categories Community also draws from), now labeled to
match `TOOLS_REFERENCE.md` exactly so this split stays traceable against the live registry.

This is a first-pass proposal, not a final cut — the exact line is a product/pricing decision, not
something the codebase dictates. Two specific calls worth a second look before committing:

- `obfuscate_sensitive_points` in Pro is defensible on "institutional use case" grounds, but it's
  also a Do No Harm safety feature — gating basic protection for sensitive point data behind a
  paywall is worth a deliberate, not accidental, decision.
- `execute_pyqgis_script` in Pro removes Community users' only escape hatch for anything not
  covered by a named tool. That's consistent with treating it as the highest-support-cost tool in
  the registry, but it does mean Community is a closed set with no scripting fallback.

## 5. What this proposal does *not* change

- **Local LLM stays free and unrestricted in both new tiers.** No connectivity gating applies to
  Ollama — matches the existing Community tier's strongest defense/off-grid differentiator
  (`PRODUCT_TIERS.md` §1), unchanged here.
- **Security posture is tier-independent.** Nothing above touches `SECURITY.md`'s protections —
  the sandbox, SSRF guard, read-only SQL enforcement, and destructive-action confirmation gate
  apply identically regardless of tier, since none of them are currently wired to any tier concept
  (there is no tier concept in the code at all yet — see §6).

## 6. Engineering gap: what needs to be built for this to be real

Nothing in the current codebase enforces any tier distinction — every installation today is a
single, unrestricted build (`PRODUCT_TIERS.md`'s own "no per-tier feature gating anywhere in the
code" is still accurate as of this proposal). Making the structure above real requires:

1. **Finish `service/`'s punch list** (§2) — real DB, per-tier Stripe price → LiteLLM
   budget/rate-limit mapping (at minimum: a Community free-quota plan and a Pro plan), subscription
   lifecycle handling, website auth.
2. **Add `agent/providers/cartogen.py`** — a new provider client pointing at the gateway's virtual-
   key endpoint, following the existing `agent/providers/base.py` interface every other provider
   client implements.
3. **Add a tier/license concept to the plugin itself** — currently doesn't exist in any form.
   `agent/auth.py` stores API keys via `QgsAuthManager`; there's no concept of "which tier is this
   installation" anywhere. This needs: a way to activate/store a Cartogen account tier client-side,
   and a gating check in `agent/tools/registry.py` (or `ToolRouter`) that filters `TOOLS_SCHEMA`
   down to the active tier's allowed set before it ever reaches the model — the same mechanism
   `ToolRouter.filter_relevant_tools` already uses to narrow 134 tools to a candidate set could
   plausibly be extended to filter by tier first, then by relevance, rather than building a
   parallel gating system.
4. **Connectivity gating in the settings UI** — `ui/settings_dialog.py` currently lets any user
   paste any provider's key. A Community/Pro build needs to either hide the direct-BYOK provider
   options entirely or gray them out with an upsell message pointing at Enterprise.
5. **Resolve the licensing question from §3 first** — everything below assumes an answer to it.
   If the "open core" path is chosen: identify exactly which modules become the closed, unpublished
   part (candidates: the Pro/Enterprise-exclusive tool modules listed in §4, and any future
   `agent/providers/cartogen.py`), and set up a build process that produces a public GPL v2
   "core" repo and a separate, never-published private repo/package for the closed modules —
   materially different from `build_cartogen_ai.py`'s current job (which only re-brands identical,
   fully-open source into two trees; it doesn't currently remove or hide anything).
6. **Build the actual closed-source distribution mechanism** — "closed code" means Pro/Enterprise
   users receive something that isn't readable/modifiable Python source the way Community's GPL
   tree is today. Realistic options: ship as compiled bytecode (`.pyc`)/Cython extension modules
   instead of `.py` files, or distribute Pro/Enterprise as a hosted/gated download rather than a
   public plugin-repo listing. This is new engineering surface with no existing precedent in this
   repo — `build_cartogen_ai.py`'s dual-tree output is two full, readable source trees, not a
   closed build.
7. **Decide how the Enterprise tier is distributed** — a separate build/branch or a separate
   plugin listing, distinct from the closed-source packaging in item 6 above (which applies to
   Pro and Enterprise alike, per §3's proposed source-availability row).

None of this is started. This is a scoping list, not a claim of partial completion. **Item 5 (the
licensing decision) blocks items 6 and 3 in practice — there's no point building a tier-filter or a
closed-source packaging pipeline before knowing which of §3's three licensing paths this project is
actually taking.**

## 7. Migration consideration (flagged, not decided)

Every existing Community user today has unrestricted access to all 134 tools, direct BYOK to four
providers, *and* a fully public, modifiable, redistributable GPL v2 source tree — that's the
entire current product. Shipping the structure above as described would be a real reduction on
**two axes at once** for anyone already using it, not just a new tier added alongside the old one:
fewer tools/no direct BYOK (as before), *and* — if the "open core" or "re-license" paths from §3
are chosen — a source tree that's less open than what they have today, which for a GPL v2 project
carries its own expectation-management weight beyond ordinary feature changes. Whether existing
users get grandfathered into the new Pro tier free, given a migration window, offered a "your
existing GPL v2 copy keeps working as-is, only new releases follow the new model" carve-out, or
simply see Community redefined going forward is a product/business/legal decision this document
isn't making — flagging it explicitly so it isn't decided by default via silence.

## 8. Recommendation if a decision is needed now

**The licensing question in §3 is the actual first blocker, not an engineering one — get real
counsel on it before any of the rest below is worth spending engineering time on.** Once that's
resolved: build the tool-tier gating mechanism (§6.3) generically enough that the exact tool list
per tier is a config/data change, not a code change — the specific 77/57 split in §4 is a
reasonable first cut, verified against the live 134-tool registry by script (not hand-counted),
but will very likely move once real usage data exists. Don't build the Stripe/billing plumbing
(§6.1) or the closed-source packaging pipeline (§6.6) until the tool-gating mechanism and the
gateway provider client (§6.2) both exist and have been tested with a fake/free tier first —
billing and closed-source packaging are the two highest-cost-to-get-wrong pieces and the least
useful to have working early.
