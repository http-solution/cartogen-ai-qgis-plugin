# Cartogen AI Workspace — interface audit

**Reviewed:** `web-platform/phase-1/index.html` (single file, 42 KB) against `phase-1/README.md`,
`server.js`, and the Phase 0 prototype and architecture spike.
**Date:** 24 August 2026 · **Reviewer:** design pass, pre-build

---

## 1. The headline problem

The README lists roughly seventy acceptance items as complete. The interface implements
about half of them. The AI-first rewrite ("Ground-up AI-first workspace uses chat-left,
stored-data map-centre, and tools/jobs-right layout") replaced the earlier build and
silently dropped surfaces that are still fully implemented in `server.js`.

**Implemented in the API, absent from the interface:**

| Capability | API | UI |
|---|---|---|
| Print preview, paper/orientation, title, author | `POST /api/projects/:id/exports` | missing |
| Download HTML | `GET /api/exports/:id/html` | missing |
| Download PDF | `GET /api/exports/:id/pdf` | missing |
| Export history | `GET /api/projects/:id/exports` | missing |
| Classification / sensitivity label | stored, rendered on covers | missing |
| Attribute table, filter, filtered export | layer GeoJSON | missing |
| Style presets, opacity, dynamic legend | `normalizeExportStyle` | missing |
| North arrow, scale bar | export path | missing |
| Planning-context document upload | `POST /api/projects/:id/documents` | missing |
| Job retry | `POST /api/analysis-jobs/:id/retry` | missing |
| Result-layer link from a completed job | job output | missing |
| Feature lineage read-back | `feature_lineage_events` | missing |
| Freshness and boundary-compatibility warnings | layer metadata | missing |

Every one of these is checked off in the README. The acceptance list should be re-scored
against the shipping interface before it goes in front of a design partner — a demo that
cannot produce the PDF the README promises is a worse outcome than a shorter list.

---

## 2. Defects — things that are wrong, not just missing

**A. Basemap attribution does not follow the basemap.** *(licensing, not polish)*
`index.html` renders a static `<div class="map-attribution">© OpenStreetMap contributors</div>`
and hides Leaflet's own attribution control. Switching to Carto Voyager or Esri World
Street Map leaves the OpenStreetMap credit in place and never shows Carto's or Esri's.
Given `PROVENANCE_REGISTER.md` — "Do not remove licence notices from dependencies" — this
is a compliance defect. Fix: keep Leaflet's attribution control, or drive the custom
element from the active basemap's attribution string.

**B. Jobs never refresh.** `loadJobs()` runs only on project load, after queueing, and after
plan approval. Queue a buffer and the row reads `queued` indefinitely; the worker completes
it and nothing in the browser notices. There is no polling, no SSE, no completion toast.
This is the single largest gap between what the system does and what the user believes.

**C. A stray map click destroys unsaved edits.** `state.map.on('click', () => clearInspector())`
wipes `#editProperties`, `#editGeometry` and the preview with no confirmation. The edit
workflow is otherwise careful (hash guard, HMAC preview token, explicit apply) and then
throws the work away on a misclick.

**D. Every layer renders identically.** `styleForLayer(layer)` ignores its argument and
returns the same teal fill for all layers; `pointStyle()` is one amber dot. Five layers on
the map are indistinguishable, and there is no legend to disambiguate them.

**E. First toggle hijacks the viewport.** `toggleLayer` calls `fitLayer` on first load, so
adding a second layer yanks the map away from wherever the user was.

**F. Double-queue is possible.** `queueAnalysis()` never disables `#queueButton`; two clicks
create two jobs.

**G. The popup duplicates the inspector and says nothing.** `bindPopup` is re-bound on every
feature click and its content is the literal string `Stored feature`.

**H. Dead code.** `syncScheduleOperation()` is empty and still wired to a change listener.
`fillLayerSelects()` writes to `#scheduleSourceLayer` and `#scheduleOverlayLayer`, which do
not exist. `loadIdentity()` has identical branches for authenticated and unauthenticated,
so the header never reports auth state — it just prints the mode.

**I. Leaflet loads from unpkg.** For humanitarian deployments that are offline, air-gapped,
or behind a restrictive egress policy — exactly the environments in the pilot charter — a
CDN dependency is a hard failure and a supply-chain surface. Vendor it.

**J. Leaflet is never told the layout changed.** No `invalidateSize()` on resize or when the
grid reflows at the 1000 px and 760 px breakpoints; the map renders into a stale size.

---

## 3. Structure and information architecture

**Three fixed columns, no collapse.** `grid-template-columns: 360px minmax(0,1fr) 300px`.
On a 1440 px laptop the map — the product — gets 780 px, and nothing can be folded away.

**Seven always-open sections in a 300 px column.** Basemap, Project layers, Dataset
discovery, Feature inspection, Spatial analysis, Jobs, Schedules, all expanded, one
scrollbar. Finding the buffer distance means scrolling past a dataset search. There are no
tabs, no accordion, no grouping.

**The Phase 0 navigation was lost.** The prototype had Projects, Map, Data, Analysis,
Reports, Activity, Admin. Phase 1 has a `<select>`. Restoring that IA is the single highest
-leverage structural change.

**No search of any kind.** No geocoder, no layer filter, no way to find one of 4,849
facilities. This is the defining Google Maps affordance and it is absent.

**No tabular surface.** GIS is half map and half table. There is no attribute table, so
nothing can be sorted, filtered, or exported as a selection.

---

## 4. The AI surface

The plan card lists step titles and one Approve button. The architecture spike specifies
that the plan must show **tools, inputs, assumptions, and expected outputs** before the
user confirms. As built, the user is approving four sentences.

- No Revise and no Reject — approval is the only path forward.
- Assumptions that would invalidate the result (straight-line distance standing in for
  travel time; 2017 population on 2023 boundaries) are never surfaced at the point of
  approval.
- Once approved, the resulting task and job IDs are printed as text with no link to the
  job, the result layer, or the map.
- No streaming, no timestamps, no per-run status, no way to reopen a previous run.
- The provider is configured but never shown; `/api/ai/providers` exists and the header
  ignores it. When the deterministic fallback planner answers instead of Gemini, the user
  cannot tell.

---

## 5. Trust, provenance and safety — the differentiators, invisible

Phase 0 argues that Cartogen's edge is provenance and honesty about data quality. None of
it reaches the screen.

- Layer rows show a feature count and a licence. Not `source_retrieved_at`, not
  `source_modified_at`, not vintage.
- The documented population/boundary incompatibility — the most important caveat in the
  Pakistan bundle — appears in `PAKISTAN_BUNDLE_PROFILE.md` and nowhere in the product.
- `feature_lineage_events` records before/after hashes for every edit. There is no UI
  that reads them.
- The classification label is stored and printed on exports, and is invisible while
  working. For humanitarian data handling, a persistent sensitivity banner is table stakes.
- Derived layers are not visually distinguished from source layers.

---

## 6. Visual and interaction craft

- **Type**: Inter/system-ui at 13 px with 10–11 px secondary text throughout. Dense, but
  the small sizes are used for information the user actually needs (freshness, counts).
- **Colour**: one accent (`#40c7a2`) doing brand, primary action, success, and every map
  fill at once. There is no separation between system colour and data colour, so a teal
  polygon means nothing in particular.
- **Feedback**: six independent `.notice` divs in six panels. No consolidated status area,
  no toasts, no undo, anywhere.
- **Selection**: a clicked feature is not highlighted on the map.
- **Loading**: plain "Loading…" strings, no skeletons; a slow layer looks like a hang.
- **Empty states**: "No conversation yet. Start with an objective, not a tool command." is
  good writing. Most others just state absence without offering the next action.
- **Accessibility**: `aria-live` is on some notices but not on the chat thread. Focus is
  never moved to new content. `.btn:disabled { cursor: wait }` is wrong for buttons that
  are disabled rather than pending. Keyboard shortcuts do not exist.
- **Responsive**: the 760 px layout stacks to a 420 px map with both panels full height and
  no collapse — unusable on a phone, and field staff have phones.
- **Single theme only.** Dark chrome is right for a mapping tool, but response work happens
  in daylight; a light chrome variant should be planned, not retrofitted.

---

## 7. What the redesign does about it

Mockup: `cartogen-workspace-redesign.html`. Open the **Design notes** toggle in the header
for numbered callouts on the design itself. In short:

1. **Mode rail** restores Ask / Layers / Data / Analysis / Reports / Activity — one dense
   panel at a time, both side panels collapsible so the map can go near-full-bleed.
2. **Omnibox** — one field over places, project layers, catalogue datasets and commands.
3. **Sensitivity stripe and chip** in the chrome, always visible.
4. **The plan as an object** — tool, inputs, assumptions, expected output per step;
   approve, revise or discard; live run state pinned to the map.
5. **Trust stripe** — a three-pixel state bar on every layer, dataset, schedule and export:
   current, aging, stale, unreviewed. One device, used consistently, carrying the thing the
   product claims to be about.
6. **Legend and per-layer styling**, generated from the layer list and shared with exports.
7. **Map furniture** — scale bar, coordinate readout, extent zoom, measure, print;
   basemap thumbnails with attribution that follows the basemap.
8. **Bottom dock** — attribute table with filter and filtered export, live jobs with retry
   and result links, lineage log.
9. **One context drawer** — result, attributes, provenance and the pending edit diff,
   held until applied or discarded.
10. **Reports** — paper, orientation, title, sensitivity, warnings, four-page preview,
    HTML and PDF, export history.

---

## 8. Suggested order of work

**Before any design-partner session**

1. Attribution follows the basemap *(licensing)*
2. Job polling and completion state *(the demo breaks without it)*
3. Rebuild the Reports surface *(README claims it)*
4. Freshness and compatibility warnings on layers *(the differentiator)*
5. Stop clearing the inspector on map click *(data loss)*

**The redesign proper**

6. Mode rail and collapsible panels
7. Per-layer styling and the legend
8. Attribute table dock
9. Plan card with tools, inputs, assumptions; revise and reject
10. Omnibox

**Then**

11. Vendor Leaflet; drop the CDN
12. Sensitivity banner and lineage viewer
13. Light chrome variant, keyboard shortcuts, mobile layout
