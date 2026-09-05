# Humanitarian Cartography Standards

This document records the compliance standard Baron supplied on 2026-09-03
("Comprehensive Humanitarian Operations and Mapping Standard Framework") and
maps it against what Cartogen AI's tools actually do today, verified against
the live source tree rather than assumed. It is the reference to check new
humanitarian-mapping tool work against going forward, and the basis for the
gap-closing work queued in `docs/MASTER_TASK_REGISTRY.md`.

Companion documents: `docs/HUMANITARIAN_MAPPING_TASK_REFERENCE.md` is a
topic taxonomy (*what* humanitarian mapping work Cartogen AI should cover);
this document is a compliance standard (*how* that work must be done --
data provenance, symbology, layout, metadata). The two are not duplicates.

## A. The standard (verbatim, as supplied)

### I. Geographic Data Foundations

- Exclusively utilize Common Operational Datasets (CODs) containing official
  Place Codes (P-codes) for all administrative boundaries (ADM0 to ADM3+)
  and settlement layers.
- Cross-reference all imported locations against standardized databases or
  gazetteers (e.g., HDX).
- Prohibited: Never use informal or unverified geographic names, and do not
  reuse a retired P-code for a different administrative unit.

### II. Multisector Data Integration

- Integrate layers for specific humanitarian sectors: Water, Sanitation, and
  Hygiene (WASH) infrastructure, Shelter/NFI distribution points, and Health
  facilities.
- Incorporate population datasets including demographic breakdowns and
  Internally Displaced Person (IDP) or refugee camp coordinates.
- Maintain standardized attribution for all multisector data points.

### III. Rapid Needs Assessment and Vulnerability Mapping

- Map vulnerable populations using socioeconomic indicators, food security
  zones, and protection risk areas.
- Include rapid needs assessment data to highlight immediate gaps in service
  delivery.
- Use heat mapping or choropleth techniques to represent severity indices
  consistently across the operational area.

### IV. Network-Aligned Routing and Logistics

- All routing and transit plans must be strictly snapped to established road
  networks or authoritative transport layers using topological routing
  algorithms.
- Prohibited: Do not draw straight lines for route paths; routes must follow
  actual geographical infrastructure and directional flow.
- Logistics overlays must include transit hubs, supply corridors, supply
  chain chokepoints, and warehouse locations using standardized logistics
  symbology.

### V. Project Management and Security Integration

- Map layers must integrate project activity sites and designated
  security/access zones.
- Include risk mapping elements such as access constraints, checkpoints,
  improvised security incidents, and mine/UXO contamination areas using
  authorized humanitarian reporting codes.
- Maintain a consistent visual hierarchy that highlights operational areas
  and risks without obscuring base geographic data.

### VI. Cartographic Design and Visualization

- All graphic elements must be generated from standardized, authoritative
  symbol libraries.
- Maintain consistent visual hierarchy and color-coding across all project
  outputs.
- Prohibited: Strictly avoid free-hand drawing -- no manual circles,
  squares, or irregular geometric shapes. Never use nonstandard graphics
  that resemble incomplete or juvenile sketches.

### VII. Mandatory Map Layout Elements

Every map must contain: a precise, descriptive title; a professional North
arrow; an accurate scale bar suitable for the zoom level; a comprehensive,
legible legend; adequate contrast between features and backgrounds.

### VIII. Metadata and Operational Context

Mandatory metadata block displaying: map subject/context and operational
period; verified data sources and versioning; projection and coordinate
system information; disclaimers regarding data sensitivity and geographic
boundaries.

## B. Gap analysis against the live source tree (2026-09-03)

Each item below was checked directly against the files named, not inferred
from memory or from tool descriptions alone -- consistent with this
project's evidence-before-assertion rule. "Confirmed" means the cited code
was read; "not found" means a targeted search across
`src/cartogen_ai/core/agent/tools/*.py` found no matching implementation,
which is evidence of absence in this codebase, not proof the capability
could never exist.

### I. Geographic Data Foundations -- substantially met

`humanitarian_tools.py`'s `fetch_cod_boundaries` prefers OCHA's COD-AB
dataset on HDX specifically because it carries real P-codes
(`adm{N}_pcode` attributes), and only falls back to `fetch_geoboundaries`
when no COD-AB dataset exists for the country -- with that fallback's
result explicitly labeled "broader country coverage, but no P-codes."
`analysis_tools.py`'s admin-unit-matching tools (`unit_name_field`,
`presence_admin_field`) are built to key off that P-code field.

Gap: nothing in code stops the model from typing an informal place name
elsewhere in a chat response or a manually-added point's label, and there
is no check against reusing a retired P-code -- both are prompt-level
expectations only, not enforced in tool code. Given how load-bearing
P-codes are to this standard, that may be worth a stronger tool-description
nudge, similar to the anti-fabrication language added to `add_point_layer`
for BUG-2026-09-02-6.

### II. Multisector Data Integration -- partial, needs a closer pass

`fetch_worldpop_population` (gridded population, ~100m resolution) and
`fetch_osm_features` (generic Overpass key/value fetch, which can pull WASH
points, health facilities, etc. by OSM tag) both exist. No dedicated
IDP/refugee-camp or shelter/NFI-distribution-point fetch tool was found in
this pass -- `fetch_osm_features` could be pointed at OSM tags for these,
but there's no purpose-built tool or documented tag list for it, and
"standardized attribution" was not checked in this pass. This section needs
a dedicated review before it can be marked either met or unmet with
confidence.

### III. Rapid Needs Assessment and Vulnerability Mapping -- met

`analysis_tools.py`'s `calculate_severity_index` builds a JIAF/INFORM-style
composite index: min-max normalization to 0-1, weighted sum, equal-interval
1-5 severity class, with an explicit design comment that it must not invent
a severity score for a place with no data. `apply_graduated_style` /
`apply_categorized_style` (styling_tools.py) provide the choropleth-style
rendering this section calls for.

### IV. Network-Aligned Routing and Logistics -- mixed; one concrete gap

`calculate_service_area` and `travel_time_matrix` (`logistics_tools.py`)
use QGIS's native network-analysis algorithms
(`native:serviceareafrompoint`, `native:shortestpathpointtolayer`) -- real
road-network-snapped routing, honestly caveated in the module docstring as
best-effort pending live QGIS verification (this plugin's dev environment
has no real QGIS install).

Concrete gap: `optimize_delivery_route` explicitly computes straight-line
(as-the-crow-flies) distances for its nearest-neighbor + 2-opt stop
ordering, and says so plainly in its own tool description. That's an
honest and reasonable design for a lightweight stop-sequencing tool, but
nothing currently stops the model from taking that stop order and drawing
a straight-line "route" layer with it for a final map or report -- which
would directly violate this section's "do not draw straight lines for
route paths" rule. `score_route_incident_risk`'s docstring even names "a
hand-drawn route" as one of the acceptable inputs to that tool, confirming
non-road-snapped route layers are a live possibility today, not a
hypothetical.

Logistics symbology (transit hubs, supply corridors, chokepoints,
warehouses) was not directly checked in this pass.

**Update, 2026-09-04: gap closed.** Baron decided to upgrade rather than
block -- `optimize_delivery_route` now accepts an optional
`road_network_layer` argument. When given, it chains
`native:shortestpathpointtopoint` across each consecutive stop in the
computed visiting order and merges the segments into one road-snapped route
line, added to the project (`agent/tools/logistics_tools.py`'s
`_build_road_snapped_route`). Without `road_network_layer`, the tool now
returns an explicit `warning` in its result telling the caller not to render
the stop order as a route -- so the "nothing stops the model from drawing a
straight line" gap above is closed either way: build a real route, or get
told plainly not to fake one. Same unverified-live caveat as this section's
other network-analysis calls. Covered by
`tests/test_logistics_tools.py`'s `TestOptimizeDeliveryRouteRoadSnapping`/
`TestBuildRoadSnappedRoute` (mocked-QGIS, all passing; 748/0/0/1 baseline
unaffected).

### V. Project Management and Security Integration -- partial

`score_route_incident_risk` (security-incident proximity scoring) and
`add_incident_point`/`add_point_layer`'s `severity`/`category` fields exist.
Gap: those fields are freeform strings, not an authorized/controlled
humanitarian reporting-code vocabulary (e.g. an IMSMA- or ACLED-style event
typology) -- this is the same freeform-input surface that BUG-2026-09-02-6
already had to mitigate against fabrication; adding a real controlled
vocabulary would close both this section's requirement and further reduce
that fabrication surface. Dedicated checkpoint / mine-UXO tooling was not
found in this pass and needs a closer look.

**Update, 2026-09-04: gap closed for the coding-vocabulary half.** Baron
decided to support both named vocabularies rather than pick one.
`add_incident_point`/`add_point_layer` now accept optional
ACLED-style `event_type`/`sub_event_type` and IMSMA/IMAS-style
`hazard_type`/`contamination_status` fields, layered on top of (not
replacing) the pre-existing freeform `severity`/`category` fields. Values
are checked against the real published taxonomies (`ACLED_EVENT_TAXONOMY`,
`IMSMA_HAZARD_TYPES`, `IMSMA_CONTAMINATION_STATUSES` in
`agent/tools/humanitarian_tools.py`) via `_validate_incident_coding` -- an
unrecognized value comes back as a `coding_warnings` entry rather than a
rejected point, so this stays advisory rather than a hard gate. Covered by
`tests/test_humanitarian_incident_coding.py` (15 tests, all passing).
Dedicated checkpoint/mine-UXO *fetch/discovery* tooling (as opposed to this
coding vocabulary) remains unbuilt -- that half of the gap stands.

### VI. Cartographic Design and Visualization -- largely met structurally

No freehand-drawing tool (draw an arbitrary circle/square/polygon by hand)
exists anywhere in the registered tool set, so the "no manual sketches"
prohibition is satisfied by omission -- every point/line/polygon layer goes
through data-driven tools plus `apply_categorized_style` /
`apply_graduated_style`, not ad hoc shape drawing. Not yet confirmed:
whether those renderers draw from a named, authoritative humanitarian
symbol library (e.g. OCHA's) as opposed to QGIS's own default symbol set.

### VII. Mandatory Map Layout Elements -- met, unconditionally

Confirmed directly in `layout_tools.py`'s `create_print_layout`: title,
`QgsLayoutItemLegend`, `QgsLayoutItemScaleBar`, and a north-arrow picture
item are all added unconditionally to every layout, matching this section
essentially as written. (Live on-page fit, especially in portrait
orientation, remains flagged as unverified pending a real QGIS session --
same standing caveat as the rest of this tool.)

### VIII. Metadata and Operational Context -- clear gap

`create_print_layout` currently has: a title label, an *optional* freeform
`body_text` panel (described only as "e.g. priority findings, data
sources"), and the new standing AI-disclaimer footer added for
BUG-2026-09-02-6. There is no mandatory, structured metadata block covering
operational period, verified data sources plus versioning, projection/CRS
information, or a data-sensitivity/boundary disclaimer distinct from the
generic AI-disclaimer. This is the most clearly-scoped, self-contained gap
found in this pass -- but see the maintenance note below on why it hasn't
been implemented in the same slice as this document.

## C. Maintenance note

`create_print_layout`'s portrait-orientation geometry is already flagged
elsewhere in this codebase as tight and unverified after the
BUG-2026-09-02-6 footer was added. Stacking another mandatory layout
element (the Section VIII metadata block) on top of that, blind, without a
live QGIS session to check the result, risks compounding an already-unsure
fit rather than fixing one problem at a time. That work is queued (see
`docs/MASTER_TASK_REGISTRY.md`) to land alongside the live QGIS smoke test
already on the queue, not ahead of it.

~~Sections IV and V's gaps both hinge on a design decision only Baron can
make -- whether `optimize_delivery_route`'s output should be blocked from
feeding a final map/layout without a road-snapped route, or upgraded to
build one; and which controlled vocabulary (if any) to adopt for incident
reporting codes -- so implementation is queued behind that decision rather
than guessed at.~~ **Resolved 2026-09-04** -- both decisions were made
(upgrade; support both vocabularies) and implemented the same session, see
the "Update" notes inline in Sections IV and V above. Struck through rather
than deleted per this repo's own no-silent-rewrite convention.
