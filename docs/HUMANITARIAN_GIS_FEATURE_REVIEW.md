# Cartogen AI — Humanitarian Crisis Management & Fund Allocation Feature Review

**Reviewer role:** Humanitarian field GIS analyst / IMO perspective (OCHA / DG ECHO / REACH / WFP / UNHCR analytical conventions)
**Scope:** Which existing tools already serve crisis management and fund-allocation decision-making, and what's genuinely missing.
**Status:** Revision 2 (2026-08-14), superseding the original pass. Every Tier-1 and buildable Tier-2 item identified in Revision 1 has since been built and independently verified against real code, hand-computed math, and (where the claim was external) live data — not re-stated from memory here. This revision re-assesses from the current 125-tool baseline and identifies what's newly worth doing next. **Update (2026-08-16):** both items this revision flagged as "newly worth doing" are now shipped — see the status notes under sections A and B.

---

## 0. What changed since Revision 1

Nine new tools shipped (116 → 125), plus a provenance addition to two existing ones:

| Item | Tool(s) | Status |
|---|---|---|
| Composite severity/needs index (JIAF/INFORM-style) | `calculate_severity_index` | Shipped, math hand-verified |
| Population beyond service-area reach | `population_access_gap` | Shipped, composed from existing `calculate_service_area` + `estimate_population_exposure` |
| Geoprivacy safeguard | `obfuscate_sensitive_points` (jitter/grid_snap/admin_unit_snap) | Shipped, jitter distribution independently Monte Carlo-verified as genuinely uniform-area |
| 3W/4W operational-presence loading + severity-vs-presence gap overlay | `load_3w_data`, `calculate_presence_gap` | Shipped; unmatched-vs-confirmed-zero-presence distinction verified by hand-trace |
| Reliable P-code join key | `fetch_hdx_admin_boundaries` (OCHA COD-AB via HDX) | Shipped as a different, correct fix — geoBoundaries itself was confirmed (live, across 5 countries) to publish no P-codes at all, so the original "capture the field" framing was wrong; this pulls from HDX COD-AB instead, which does carry them |
| Non-GIS-audience output | `generate_html_dashboard` (Leaflet/Folium) | Shipped; the "no server dependency" framing from Revision 1 was itself corrected — viewing needs internet access for basemap/library CDN tiles, generating does not |
| Sector coverage reporting preset | `generate_sector_coverage_report` | Shipped |
| Humanitarian cluster symbology | OCHA/IASC cluster color presets in `apply_categorized_style`/`apply_graduated_style` | Shipped, honestly scoped as a common convention, not a claimed official OCHA hex standard (none exists) |
| Baseline building footprints | `fetch_building_footprints` (Microsoft Global ML Building Footprints) | Shipped as a reframed, better-scoped answer to the PRD's deferred "imagery feature extraction via vision models" item — pre-computed vetted polygons instead of asking a vision LLM to output precise coordinates, a known-unreliable pattern for work where geometric accuracy matters |
| Report traceability | `generate_report`/`generate_spatial_report` gain optional `source_layers` → provenance/lineage section | Shipped, built on lineage data the plugin already tracked but never surfaced |

All of the above were independently re-derived during review, not accepted from commit messages: the tile-quadkey math behind `fetch_building_footprints` was cross-checked against the real `mercantile` library across 8 coordinate pairs (all matched exactly); the severity-index and presence-gap math was hand-traced against constructed examples; the jitter distribution was Monte Carlo-tested; the P-code and building-footprints license claims were checked against live sources. One documentation gap surfaced in that process (`LICENSE_AUDIT.md` not updated for the two new dependencies) and was fixed same-day.

This document itself (the original Revision 1) had gone stale in the repo — it still described the items above as open gaps after they'd been closed. That's corrected here.

---

## 1. Current state assessment

The tool coverage for crisis management and fund-allocation decision-making is now substantially complete relative to what a field IMO would ask for at the analysis stage: severity classification, population exposure, network-based accessibility, facility siting, operational-presence gap analysis, geoprivacy, and non-technical-audience output are all real, tested capabilities — not placeholders. Nothing in this revision found a false or overstated claim among the shipped tools.

What's below is not "still broken" — it's the next layer of value once the base analytical toolkit is this complete.

---

## 2. What's newly worth doing

### A. No population-in-need (PiN) figure — the actual number allocation decisions are quoted in

`calculate_severity_index` ranks admin units and classifies them 1–5. It does not answer the question every HRP (Humanitarian Response Plan), donor brief, and allocation committee actually quotes: **how many people** does that severity translate to — "4.5 million people in need in District X," not just "District X is severity class 5." Right now getting that number requires manually chaining `calculate_severity_index` (with `output_field` to write scores back), selecting high-severity features, and running `estimate_population_exposure` on the selection — several steps, and easy to get subtly wrong (e.g., double-counting a unit split across two selections, or forgetting to exclude the units `calculate_severity_index` itself already flagged as excluded-for-missing-data).

This is the same shape of gap `population_access_gap` closed for accessibility: two already-correct tools that nobody had chained into the one composite number that matters operationally. A `calculate_population_in_need` (or an optional `population_raster_layer` parameter added directly to `calculate_severity_index`) that returns total population per severity class — reusing `_compute_severity_index`'s existing, verified math and `estimate_population_exposure`'s existing zonal-statistics path — would close it with the same low-risk, thin-composite pattern already established and verified working four times over in this codebase.

**Shipped (2026-08-16):** `calculate_population_in_need` — a new standalone tool (not a parameter bolted onto `calculate_severity_index`, to match the existing composite-tool precedent of `population_access_gap`/`calculate_presence_gap`). Computes severity internally via `_compute_severity_index`, then calls `estimate_population_exposure` directly for its zonal-statistics side effect and reads `pop_sum` back per-feature by fid (not via that tool's own `totals` dict, which keys off the layer's first field rather than `unit_name_field`). Returns `population_in_need` for the high-severity classes plus a per-class breakdown; units missing indicator data or population coverage are excluded from the total, never imputed as zero. See `CHANGELOG.md`.

### B. `calculate_presence_gap` has no `output_field` — its results can't be styled or put on a dashboard

`calculate_severity_index` can write its score back onto the layer (`output_field`), which is what makes it stylable via `apply_graduated_style` and mappable via `generate_html_dashboard`. `calculate_presence_gap` has no equivalent — its gap/covered/unmatched classification only comes back as JSON, with no way to render it spatially. Given `generate_html_dashboard` is explicitly positioned as the deliverable for a fund-allocation committee, and presence-gap is exactly the kind of finding that audience wants to see on a map (not read out of a JSON blob), this is a small, mechanical gap rather than a new design problem — the same `_write_scores_to_layer`-style helper `calculate_severity_index` already has would carry over directly.

**Shipped (2026-08-15):** `calculate_presence_gap` gained an `output_field` parameter, writing each high-severity unit's gap/covered/unmatched status back to the layer via `_write_presence_gap_status_to_layer`.

### C. Still open from Revision 1, correctly not attempted

Scheduled/recurring monitoring workflows (re-running severity/presence analysis periodically and diffing) were a PRD-level gap (Phase 2, not specific to this review) — **shipped 2026-08-16** as `run_monitoring_workflow`/`schedule_recurring_workflow` (in-session `QTimer` scope only; see `CHANGELOG.md` and `QGIS_AI_Agent_PRD.md` §6 Phase 2). Building-footprint-based **damage** classification (as opposed to baseline footprints, which are now covered) remains appropriately deferred — `fetch_building_footprints` is explicit that it's a periodic baseline dataset, not live post-event extraction, and `calculate_raster_change_detection` is the closest existing tool for change/damage signal. Neither is misrepresented in current docs.

---

## 3. Recommendation

Build (A) first — it's the highest-leverage remaining item for the stated fund-allocation use case, for the same reason `calculate_severity_index` itself was Revision 1's top priority: it's the number the decision actually gets made on, not an input to it. (B) is a small follow-on worth bundling with it rather than its own review cycle. Nothing else in the current toolkit rises to the same priority.

**Both items shipped as of 2026-08-16** (see status notes above). No further gap identified by this revision remains open; a future revision would need to re-baseline from the current tool count to find the next layer of value.
