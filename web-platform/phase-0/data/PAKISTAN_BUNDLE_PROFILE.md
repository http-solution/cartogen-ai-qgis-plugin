# Pakistan Phase 0 Bundle — Structured Dataset Profile

## Bundle purpose

Create a versatile, public-data humanitarian demonstration for Cartogen AI Workspace using one country context with complementary operational, geographic, population, facility, transport, needs, and hazard layers.

## Source matrix

| Role | Source | Format | Main use | Key caveat |
|---|---|---|---|---|
| Presence | OCHA Global 3W | XLSX | Who is doing what and where | Operational resource is historical to 2023 |
| Geography | OCHA/COD Pakistan boundaries | GeoJSON ZIP | Admin0–admin levels and joins | Boundary version must be recorded |
| Population | OCHA/COD Pakistan ADM2 population | CSV | Population context and denominators | 2017 vintage; source notes it is not compatible with the newer boundary layer without a crosswalk |
| Facilities | Healthsites Pakistan | CSV | Health facility points and accessibility context | Completeness and operating status vary |
| Transport | HOT/OSM Pakistan roads | GeoJSON ZIP | Route/accessibility context | Road completeness and condition are not guaranteed |
| Needs | Pakistan Humanitarian Needs Overview | XLSX | HNO contextual indicators | Resource is a 2021 snapshot |
| Hazard | Pakistan flood event, 29 Aug 2025 | GeoTIFF ZIP | Flood-exposure demonstration | Event-specific hazard footprint, not a general risk layer |

## Cross-layer analyses for the prototype

### Analysis A — Partner presence by administrative area

- Filter the global 3W records to Pakistan.
- Normalize organization and sector names.
- Aggregate distinct organizations by sector and admin area after a reviewed join.
- Display counts separately from raw record totals.

### Analysis B — Health access context

- Load Healthsites points.
- Validate coordinate fields and missing names.
- Overlay with administrative boundaries and roads.
- Produce facility counts by area.
- Flag areas with population but low facility count as a screening result, not a definitive gap.

### Analysis C — Population and presence comparison

- Join ADM2 population to administrative boundaries.
- Compare population denominators with distinct 3W organizations by sector.
- Calculate an exploratory people-per-presence indicator.
- Label it as an indicator, not a service-coverage measure.

### Analysis D — Flood exposure demonstration

- Load the 2025 flood raster only as an event layer.
- Overlay population/admin areas and facilities.
- Produce an exposure-screening map.
- Display event date and source age prominently.

### Analysis E — Humanitarian access

- Overlay roads, facilities, admin areas, and selected population/needs context.
- Use road network only for exploratory access context until route network quality is verified.
- Avoid claiming travel time without a validated routing model and road-speed assumptions.

## Data-quality controls

- Preserve raw source values and normalized fields separately.
- Normalize mixed date formats before sorting.
- Validate ISO3 and administrative p-codes.
- Maintain a source freshness panel.
- Record missing coordinates and invalid geometries.
- Preserve organization aliases.
- Flag duplicate 3W rows.
- Show source limitations beside every derived indicator.
- Do not combine incompatible administrative vintages silently.

## Recommended Phase 0 user story

> For Pakistan, show areas where reported partner presence is low relative to population context, health-facility availability is limited, road access is sparse, and a selected flood event intersects the area. Let the user inspect every source, date, assumption, and limitation before exporting a review map.

This user story is intentionally a screening workflow. It does not determine humanitarian priority automatically.

## Output package

The prototype should produce:

- an interactive map;
- an area summary table;
- sector and organization filters;
- source freshness badges;
- data-quality warnings;
- AI-generated but reviewable analysis plan;
- exportable CSV/GeoJSON/report summary;
- provenance record listing every input and processing step.

## Ethical and operational controls

- Use public/non-sensitive data only for Phase 0.
- Do not include beneficiary-level data.
- Do not infer absence of assistance from absent 3W records.
- Do not expose suppressed Protection information.
- Do not present event-specific flood exposure as current general risk.
- Require human review before any decision-facing export.
