# PLAN-044: Every fetched layer says where it came from (roadmap step C, master list RM-C)

Status: in progress

## Goal
A map made from fetched data can be cited and its licence honoured: each fetch result, the layer it created, the provenance sidecar and the report name the source, its URL, licence, retrieval date and coverage.

## Scope
In: `core/agent/source_record.py` (a table of ten fetch tools, the record, a layer custom property `cartogen/sources`, collection through lineage inputs, one report line); the orchestrator adds `data_source` to the result of a fetch tool on the network-only and two-phase paths and tags the output layer on the main thread; `build_provenance_record` gains `sources`; `generate_report` and `generate_spatial_report` print them.
Out (later): showing a large data set to the user before loading it; reading the licence from the service on each call; fetch tools not in the table (`fetch_osm_features`, `fetch_fts_funding_data`, search tools).

## Honest limits
The licence text is a hand-written table from each service's published terms. It is not read from the service, so every record says `licence_checked: false` and the report line says "not checked against the source". HDX has a licence per data set, so its record says so and does not name one. Coverage is what the call asked for, not what came back. NASA FIRMS, EONET and GDACS entries say "see the terms" because the plugin does not state a licence for them.

## Acceptance
1. A successful result of each tool in the table carries `data_source` with name, url, licence, attribution, retrieved_at, coverage, licence_checked. A failed result carries none. An existing `source` key in a result is not overwritten.
2. The output layer carries the record; fetching again with the same coverage replaces it, a different coverage adds one.
3. `get_provenance_record` / `write_provenance_sidecar` include `sources`, own and inherited through lineage inputs (bounded depth, cycle safe).
4. Both reports print a "Data source:" line per record.

## Guard tests
`tests/test_source_record.py` (offline), `tests/test_source_record_live.py` (CI only; written without QGIS).

## Rollback
Remove the `source_record.attach` call in `agent_orchestrator._execute_tool`; nothing else depends on it.

## Status log
- 2026-11-01: built. Offline tests pass; the live test has not run (CI first run). Not verified with a real fetch in QGIS: hand row added to the ledger.
