# Humanitarian Operational Extensions Catalogue

**Phase:** 0
**Country focus:** Pakistan, with Afghanistan as a current operational-presence comparison
**Analysis date:** 2026-08-23

## 1. Logistics and access

### WFP Global Stations — Logistics Database

- Dataset: https://data.humdata.org/dataset/global-stations
- Provider: WFP
- Licence: CC BY-SA
- Formats: SHP, GeoJSON, metadata TXT
- Includes: transport/logistics stations and related infrastructure fields.
- Recommended use: identify logistics nodes, supply hubs, ports/stations, and proximity to roads/facilities.
- Caveat: confirm station semantics and freshness from the metadata before using as an operational inventory.

### Pakistan roads — HOT/OSM export

- Dataset: https://data.humdata.org/dataset/hotosm_pak_roads
- Provider: HOT/OSM
- Formats: GeoJSON, GeoPackage, SHP, KML
- Recommended use: route/accessibility context and logistics network screening.
- Caveat: road presence does not guarantee passability, condition, security, or current access.

### Airports in Pakistan — OurAirports

- Dataset: https://data.humdata.org/dataset/ourairports-pak
- Provider: OurAirports
- Licence: Public Domain
- Formats: CSV/HXL CSV
- Recommended use: air-access and logistics-node context.
- Caveat: airport presence does not guarantee operational availability, permissions, runway condition, or humanitarian access.

## 2. Humanitarian security and access risk

### Pakistan — Conflict Events, aggregated ACLED

- Dataset: https://data.humdata.org/dataset/pakistan-acled-conflict-data
- Provider: ACLED
- Catalogue licence: Other
- Formats: XLSX aggregated by month/year.
- Includes: political violence, civilian-targeting, and demonstrations summaries.
- Recommended use: temporal security-context charts, country/province screening, and scenario context.
- Caveat: do not present aggregated conflict statistics as a route-safety decision without current local validation. Detailed ACLED event access may require separate registration/permission.

### Pakistan — UCDP conflict events

- Dataset: https://data.humdata.org/dataset/ucdp-data-for-pakistan
- Provider: UCDP
- Recommended use: independent conflict-event comparison and historical context.
- Caveat: review licence, event definitions, date coverage, and spatial precision before using alongside ACLED.

### Security product rule

Security layers should be labelled as:

- historical context;
- reported events;
- uncertainty-aware risk context;
- not a definitive prediction;
- not a substitute for current security advice or duty-of-care procedures.

Avoid exposing exact sensitive locations or creating a public map that could increase risk to affected people, staff, or facilities.

## 3. IT infrastructure and communications context

### Pakistan — World Bank Infrastructure Indicators

- Dataset: https://data.humdata.org/dataset/world-bank-infrastructure-indicators-for-pakistan
- Provider: World Bank Group
- Licence: CC BY
- Format: CSV
- Includes country-level indicators such as:
  - mobile cellular subscriptions;
  - fixed broadband;
  - individuals using the Internet;
  - secure Internet servers;
  - telecommunications investment;
  - roads, vehicles, air transport, and other infrastructure indicators.
- Recommended use: country context, programme planning, digital-access baseline, and comparison across years.
- Caveat: these are national indicators, not a local telecom coverage map.

### Direct Pakistan telecom coverage layer

The Phase 0 search did not identify a verified, openly downloadable Pakistan-specific mobile-tower/coverage raster on HDX suitable for immediate use. Do not imply that World Bank indicators provide local coverage.

Potential later sources to evaluate:

- telecom regulator/open data;
- approved operator coverage maps;
- OpenStreetMap communications features;
- humanitarian connectivity assessments;
- locally approved crowdsourced coverage surveys.

These require source, privacy, security, and licensing review before inclusion.

## 4. Coverage and service-access maps

### Pakistan Accessibility Indicators — HOT/Valhalla

- Dataset: https://data.humdata.org/dataset/pakistan-accessibility-indicators
- Provider: HOT/Valhalla
- Licence: CC BY-SA
- Formats: GeoPackage and CSV.
- Available examples:
  - education access;
  - hospital access;
  - primary healthcare access.
- Recommended use: service catchments, travel-time accessibility, health/education coverage screening, and facility prioritization.
- Caveat: accessibility depends on the routing network, assumed speeds, source facilities, and model date. It is not a live road-status or security layer.

### Afghanistan — current operational presence and capacity

- Dataset: https://data.humdata.org/dataset/afghanistan-operational-presence
- Provider: OCHA/HDX
- Licence: CC BY-IGO
- Current resources include January–March 2026 operational presence and capacity files.
- Recommended use: test the platform against a more current 3W-style structure and compare presence versus capacity fields.
- Caveat: do not mix Afghanistan and Pakistan data into a single analysis without a clear cross-country purpose and compatible administrative schema.

## 5. Recommended Phase 0 extension pack

Add these to the Pakistan demo:

1. Pakistan ACLED monthly political-violence summary;
2. Pakistan World Bank infrastructure indicators;
3. Pakistan education accessibility CSV;
4. Pakistan hospital accessibility CSV;
5. Pakistan primary-healthcare accessibility CSV;
6. Pakistan airports CSV;
7. WFP Global Stations GeoJSON reference;
8. current Afghanistan operational presence/capacity as a separate comparison case.

Downloaded local extension files are in `web-platform/phase-0/data/extensions/` and are reproducible with `scripts/build_operational_extensions.py`. Validation completed: 8 resources downloaded; infrastructure CSV 1,488 rows; education accessibility 2,426 rows; hospital accessibility 7,716 rows; primary-healthcare accessibility 6,846 rows; airports 195 rows; Afghanistan presence 10,098 rows; Afghanistan capacity 7,094 rows; ACLED workbook archive valid.

## 6. Structured demonstration workflows

### Workflow A — Logistics access screen

Question:

> Which facilities or population areas are near logistics stations and accessible through the available road network?

Layers:

- facilities;
- roads;
- airports/stations;
- boundaries;
- population;
- accessibility indicators.

Output:

- access-screen map;
- facility/hub proximity table;
- source-date panel;
- assumptions and limitations.

### Workflow B — Security context for operations

Question:

> Which areas have recent or historical reported conflict-event concentration near planned operational activity?

Layers:

- aggregated ACLED data;
- 3W presence;
- roads/facilities;
- boundaries.

Output:

- historical context map/chart;
- temporal trend;
- no-go/route recommendation excluded unless approved current security data exists;
- explicit uncertainty and duty-of-care warning.

### Workflow C — Digital connectivity context

Question:

> Which programme areas have weak national or subnational digital-access context that may affect web mapping and reporting workflows?

Layers/data:

- World Bank infrastructure indicators;
- approved local connectivity data if available;
- population and facilities.

Output:

- connectivity-context dashboard;
- low-bandwidth design recommendation;
- offline/sync requirement flag;
- no false local coverage inference from national indicators.

### Workflow D — Humanitarian service coverage

Question:

> Which areas combine high population/needs context with poor modeled access to hospitals, primary healthcare, or education and low reported partner presence?

Layers:

- population;
- HNO context;
- accessibility indicators;
- healthsites;
- 3W presence;
- boundaries.

Output:

- screening map;
- ranked review table;
- data freshness and compatibility warnings;
- human-review checkpoint.

## 7. Priority recommendation

For Phase 0, prioritize:

1. **Accessibility indicators** — strongest direct coverage-map value;
2. **WFP stations, roads, and airports** — logistics experience;
3. **ACLED aggregated security context** — carefully bounded operational context;
4. **World Bank infrastructure indicators** — IT/digital context, not local coverage;
5. **Afghanistan current 3W** — a separate test of newer operational-presence data.

Do not add a telecom tower/coverage map until a source with clear permission, geographic meaning, update date, and security review is found.

## 8. Data governance

- Preserve source URL, provider, licence, metadata date, and resource date.
- Keep raw source data separate from derived outputs.
- Do not publish sensitive security or humanitarian operational details without review.
- Do not claim current access from historical or modeled layers.
- Show uncertainty and date freshness on every coverage/security product.
- Keep security analysis for authorized users and private workspaces.
- Maintain attribution for OCHA, WFP, HOT/OSM, ACLED, UCDP, World Bank, and other providers.
