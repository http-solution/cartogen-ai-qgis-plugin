# OCHA/HDX 3W Dataset Structured Analysis

**Analysis date:** 2026-08-23
**Dataset:** OCHA Global Humanitarian Operational Presence Who, What, Where (3W) Portal
**Source organization:** OCHA Field Information Services Section (FISS)
**Catalogue page:** https://data.humdata.org/dataset/ocha-global-humanitarian-operational-presence-who-what-where-3w-portal
**HDX API record:** https://data.humdata.org/api/3/action/package_show?id=ocha-global-humanitarian-operational-presence-who-what-where-3w-portal
**Resource analyzed:** `global-3w-2023-06-08.xlsx`
**Resource URL:** https://data.humdata.org/dataset/a5bed1d4-1906-4ddd-b6ee-7821043e7875/resource/121d6cbe-92ff-4059-841f-26d8a8887ac9/download/global-3w-2023-06-08.xlsx

## 1. Publication and freshness

- HDX metadata created: 2020-06-25.
- HDX metadata modified: 2026-07-22.
- Resource created/modified: 2023-06-08.
- Dataset description states raw global 3W data were visualized as of 08 June 2023.
- Operational `3w date` values normalize to 2019-06-01 through 2023-05-01.
- The catalogue record is current in 2026, but the analyzed operational resource is not current operational intelligence. Treat it as historical/baseline evidence unless a newer country-level source is identified.

## 2. Structure

- Rows analyzed: 11,306 data rows.
- Columns: `country code`, `sector`, `organization`, `type`, `3w date`.
- Countries represented: 55.
- Sectors represented: 31.
- Organization names represented: 4,885 distinct strings.
- Exact duplicate rows: 161, approximately 1.4% of rows.
- HXL header row is present and useful for automated ingestion.

## 3. Organization type composition

| Type | Rows | Share |
|---|---:|---:|
| NNGO | 5,013 | 44.3% |
| INGO | 3,887 | 34.4% |
| Other | 1,278 | 11.3% |
| UN | 1,054 | 9.3% |
| Undefined | 74 | 0.7% |

The dataset is strongly populated by national and international NGO presence records. It is therefore suitable for an operational-presence analysis, but not by itself a measure of service quality, funding, beneficiary reach, or unmet need.

## 4. Leading sectors

| Sector | Rows | Share |
|---|---:|---:|
| Food Security | 2,012 | 17.8% |
| Health | 1,597 | 14.1% |
| Protection | 1,348 | 11.9% |
| WASH | 1,156 | 10.2% |
| Education | 939 | 8.3% |
| Nutrition | 757 | 6.7% |
| Shelter | 717 | 6.3% |
| Other | 604 | 5.3% |
| GBV | 376 | 3.3% |
| Child Pro | 354 | 3.1% |

The largest initial Cartogen humanitarian workflow opportunity is not simply counting organizations. It is joining presence with population, needs, facilities, severity, and access data to identify coverage gaps.

## 5. Leading country-sector concentrations

The largest country-sector row groups in this resource were:

- Ukraine — Food Security: 417;
- Philippines — Food Security: 266;
- Ukraine — Shelter: 177;
- Pakistan — SHL: 160;
- Indonesia — Health: 136;
- Ukraine — Health: 131;
- Pakistan — FSC: 127;
- Kenya — Other: 125;
- Mali — Health: 122;
- Pakistan — WSH: 112.

These are operational-presence row concentrations, not rankings of humanitarian need or impact.

## 6. Data-quality findings

### Date typing

The `3w date` field is mixed-format text/date content. It must be normalized before sorting or freshness analysis. A naive lexical sort produces an incorrect date range.

### Duplicate records

161 exact duplicate rows were found. Deduplicate using the full normalized key:

```text
country code + sector + organization + type + normalized 3w date
```

Before deleting duplicates in a production pipeline, verify whether repeated rows represent separate source submissions or accidental duplication.

### Organization names

The dataset notes that language variations and national offices are intentionally preserved. Do not treat raw organization strings as canonical organizations without a normalization table.

### Suppressed protection data

The dataset description states that some organizations working in Protection have been suppressed. Protection analysis must therefore include an explicit coverage limitation.

### Coverage semantics

A 3W presence row means an organization reported presence in a country/sector context. It does not necessarily provide:

- exact facility location;
- activity volume;
- beneficiary count;
- funding amount;
- quality or outcome;
- current operational status after the data applicability date.

## 7. Recommended Cartogen analysis workflow

### Step 1 — Ingest

- download via the HDX API record;
- store source URL, resource name, metadata timestamps, and retrieval timestamp;
- preserve the original file;
- parse HXL headers and data header separately.

### Step 2 — Normalize

- normalize `3w date` to ISO date;
- standardize country codes to ISO3 validation;
- trim and case-normalize organization/type/sector values;
- preserve the original raw values;
- flag duplicate candidate records;
- maintain an organization alias table.

### Step 3 — Aggregate presence

Create summaries by:

- country and sector;
- organization type and sector;
- country and organization;
- sector and organization;
- date and country/sector where time-series resources are available.

Use distinct organizations, not raw row count, for presence counts.

### Step 4 — Join decision layers

For a real coverage-gap analysis, join the 3W result with approved sources for:

- population/affected population;
- administrative boundaries;
- needs/severity;
- facilities and service capacity;
- access/travel time;
- displacement or vulnerability;
- funding or project data where appropriate.

### Step 5 — Produce outputs

- operational presence map;
- organization-type map;
- sector coverage map;
- potential gap map;
- data-freshness panel;
- source/provenance panel;
- limitations and uncertainty note;
- CSV/GeoPackage/report export.

## 8. Cartogen product implications

This dataset is a strong Phase 0 demonstration source for:

- OCHA/HDX ingestion;
- HXL-aware spreadsheet parsing;
- humanitarian sector filtering;
- organization normalization;
- 3W/4W dashboards;
- data-freshness warnings;
- coverage-gap workflows.

It is not sufficient alone for a beneficiary-level or district-level unmet-needs map because it lacks the spatial and needs layers required for that inference.

## 9. Recommended next analysis

Use the public 3W resource as the presence layer, then add one approved humanitarian need/population layer and one facilities/access layer. The next structured demonstration should answer:

> Which administrative areas have high humanitarian need, low reported partner presence, and poor access to relevant services — and how fresh is each input?

The output must show the difference between:

- reported presence;
- estimated need;
- inferred gap;
- data age;
- uncertainty.

## 10. Source and ethical notes

- Use only public/non-sensitive data for demonstrations unless the data owner approves otherwise.
- Do not infer absence of assistance from absence of a 3W row without qualification.
- Do not expose suppressed or sensitive protection information.
- Preserve OCHA/HDX attribution and source links in any derived product.
- Record retrieval date and source-resource date in every report.
