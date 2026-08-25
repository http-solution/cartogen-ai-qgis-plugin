# Pakistan data ingestion: what's loaded, what isn't, and why

The demo project (`pakistan-humanitarian-screening`) is seeded from the
public data bundle in `phase-0/data/`. Two scripts do the seeding, both
idempotent (safe to re-run — each layer is replaced by its own source key)
and both requiring a running `postgis` compose service (they connect via
`docker compose exec`, so they need Docker, unlike everything else changed
in this round):

- `scripts/seed_postgis.py` — administrative boundaries and health
  facilities. Existing, unchanged by this pass.
- `scripts/seed_pakistan_accessibility_layers.py` — everything below.
  Run this after `seed_postgis.py`, against the same project.

## Layers now loaded as real `project_layers` / `project_layer_features` rows

| Layer | Source file | Geometry | Features | Licence |
|---|---|---|---|---|
| Pakistan education access (ADM2) | `extensions/PAK_education_access_long.csv` | ADM2 polygon (joined from `pak_admin_boundaries.geojson.zip`) | 114 districts | CC BY-SA (HeiGIT/HOT) |
| Pakistan hospital access (ADM2) | `extensions/PAK_hospitals_access_long.csv` | ADM2 polygon (same join) | 115 districts | CC BY-SA (HeiGIT/HOT) |
| Pakistan primary healthcare access (ADM2) | `extensions/PAK_primary_healthcare_access_long.csv` | ADM2 polygon (same join) | 107 districts | CC BY-SA (HeiGIT/HOT) |
| Pakistan airports | `extensions/List of airports in Pakistan (no HXL tags)` | Point (`latitude_deg`/`longitude_deg` in the source) | 195 | Public Domain (OurAirports) |
| Pakistan roads (OSM export) | `pakistan/hotosm_pak_roads_polygons_geojson.zip` | Polygon/MultiPolygon (buffered road footprints, not centerlines — that's how HOT exports this dataset) | 5,198 | ODbL / OpenStreetMap contributors |

All feature counts above are from a real, live run of the loader against a
local PostGIS instance (not projected) — see the "Verification" section.

### The accessibility join: source district names vs. boundary district names

`PAK_education_access_long.csv`, `PAK_hospitals_access_long.csv`, and
`PAK_primary_healthcare_access_long.csv` are HeiGIT/HOT's Valhalla-routed
accessibility indicators, one row per district × population type × distance
or time band, at `admin_level` ADM0/ADM1/ADM2 mixed in the same file. Only
the ADM2 rows are used here (matching the resolution of the boundary layer
and the health-facility layer already loaded). Each ADM2 row set is pivoted
into **one polygon feature per district**, with every metric row for that
district preserved losslessly as a `properties.metrics` array — this avoids
loading dozens of duplicate overlapping polygons per district (one per
metric row) and keeps the properties queryable as a whole per district.

The accessibility CSVs identify districts by name only (a HeiGIT-internal
`id` value, not an OCHA COD p-code), and 19 of 133 distinct ADM2-tagged
names in the education file don't exactly match `pak_admin2.geojson`'s
`adm2_name`. Each was checked by hand against the boundary dataset's name
list:

- **15 are exact spelling/formatting variants of a single district** and
  are mapped via an explicit alias table in the script
  (`ADM2_NAME_ALIASES`): Battagram→Batagram, Dera Ismail Khan→D. I. Khan,
  Diamer→Diamir, Islamabad Capital Territory→Islamabad, Jafarabad→
  Jaffarabad, Layyah→Leiah, Mirpurkhas→Mirpur Khas, Naushehro Feroze→
  Naushahro Feroze, Nawabshah→Shaheed Benazir Abad, Qambar Shahdadkot→
  Kambar Shahdad Kot, Qilla Abdullah→Killa Abdullah, Qilla Saifullah→
  Killa Saifullah, Sheikhpura→Sheikhupura, Umerkot→Umer Kot, Vihari→Vehari.
- **4 don't correspond to exactly one ADM2 polygon** and are dropped rather
  than guessed (`ADM2_NAME_UNMAPPABLE`): "Azad Kashmir" is tagged ADM2 in
  the source but is really the whole AJK region (10 separate ADM2 polygons:
  Bagh, Bhimber, Haveli, Jhelum Valley, Kotli, Mirpur, Muzaffarabad, Neelum,
  Poonch, Sudhnoti); "Chitral" was later split into Chitral Lower/Upper;
  "Karachi" is 6 ADM2 polygons (Central/East/Korangi/Malir/South/West);
  "Kohistan" is 3 (Kohistan Lower/Upper, Kolai Palas Kohistan). Attaching a
  single district's worth of accessibility numbers to any one of several
  candidate polygons — or worse, to all of them — would misrepresent the
  data, so these are excluded and logged (`build_layers()` prints the drop
  counts and names to stderr) rather than silently missing.

Net result: every one of the education file's 133 distinct ADM2-tagged
names is accounted for — 114 mapped to a real district polygon (99 exact +
15 aliased), 4 dropped as genuinely ambiguous, 0 unexplained. Hospital
access (115 mapped) and primary healthcare access (107 mapped — this file
has fewer distinct districts to begin with) went through the identical
process against the same alias/unmappable tables.

## Deliberately not loaded as spatial layers

- **Pakistan 3W operational presence** (`pakistan/global-3w-pakistan-
  2023-06-08.csv`) — the source file has exactly five columns (`country
  code, sector, organization, type, 3w date`) and **no administrative or
  coordinate field at all**. It's a national roster, not a geolocated
  dataset. There is nothing here to join against a boundary or plot as a
  point without inventing a location, so it isn't. It's already surfaced
  non-spatially in `demo-data.json` (sector/org-type breakdowns and a
  sample), which is the honest representation of what this file actually
  contains.
- **World Bank Infrastructure Indicators for Pakistan** (`extensions/
  Infrastructure Indicators for Pakistan`) — country-level annual time
  series (`Country Name, Country ISO3, Year, Indicator Name, Indicator
  Code, Value`, e.g. "ICT service exports"). No sub-national breakdown
  exists in this file to attach to a district polygon. Also already
  summarized non-spatially in `demo-data.json`.
- **ACLED political violence events and fatalities**
  (`extensions/pakistan_political_violence_events_and_fatalities_by_month-
  year`) — excluded for two independent reasons, either one of which would
  be sufficient on its own:
  1. **Not spatial either.** The actual data (checked directly — the `Data`
     sheet of the source workbook) is `Country, Month, Year, Events,
     Fatalities`: national monthly totals only, no admin1/admin2 breakdown
     and no coordinates.
  2. **Licensing.** This is ACLED data, and ACLED's Terms of Use (embedded
     in the workbook's own `TOU` sheet, and at
     https://acleddata.com/terms-of-use/) explicitly prohibit "provid[ing],
     permit[ting] or allow[ing] direct access to any of ACLED's original/
     raw data or analysis." Loading this into `project_layer_features`
     would make it queryable and exportable (the app has CSV/GeoJSON/report
     export) through this platform — exactly what that clause forbids. This
     is a genuine legal constraint, not a judgment call to route around;
     using ACLED data here needs either explicit sign-off from someone who
     can agree to ACLED's terms on the organization's behalf, or a
     pre-aggregated/derived indicator that doesn't redistribute ACLED's
     underlying event and fatality records. Neither exists yet, so nothing
     ACLED-derived is loaded. **Flagging this for human review before any
     future attempt to bring conflict/security context data into the
     product — this is the one item in this ingestion pass that needs a
     decision from someone other than an automated agent.**

This closes every item in the "Pakistan 3W presence, accessibility,
hospitals, PHC access, education access, roads/logistics, conflict/security
context" gap list except conflict/security — which turned out, on actually
opening the source file, to be both non-spatial and license-restricted
rather than merely unloaded.

## Verification

Docker isn't reachable from this environment, so `seed_pakistan_
accessibility_layers.py` itself (which shells out to `docker compose exec
postgis psql`) was not run end-to-end here. Instead, the layer-building
logic (`build_layers()` and everything it calls) was imported directly and
its generated SQL applied against a real local PostgreSQL 16 + PostGIS 3
instance (not a mock):

- All 5 layers loaded with the exact feature counts shown in the table
  above (114 / 115 / 107 / 195 / 5,198).
- `ST_IsValid()` is true for every one of the 5,729 loaded geometries — zero
  invalid geometries.
- Geometry types are exactly what's expected per layer (`ST_Point` for
  airports; `ST_Polygon`/`ST_MultiPolygon` for the three accessibility
  layers and roads).
- Re-running the same SQL a second time produced the same feature counts
  (`DELETE 1` / re-`INSERT` per layer, not `DELETE 0` / doubled), confirming
  the replace-by-source-key idempotency actually works, not just reads like
  it should.
- A sample education-access feature's `properties.metrics` was spot-checked
  against the source CSV's raw rows for that district and matches exactly.

See `scripts/test_seed_pakistan_accessibility_layers.py` for a fixture-based,
Docker-free, non-network unit test of the same join/pivot/alias logic
(`python3 -m unittest scripts/test_seed_pakistan_accessibility_layers.py`) —
it exercises `accessibility_layer()` and `airports_layer()` against small
synthetic CSVs and a synthetic boundary set, so it runs in CI without the
real ~30MB data bundle.
