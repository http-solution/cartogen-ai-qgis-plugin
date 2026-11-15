# PLAN-046: Data discovery ranking (roadmap step E, first slice; master list RM-E)

Status: in progress

## Goal
`search_hdx_datasets` shows which data set to use and why: each result has a score and plain reasons about its licence, how recently it changed, and whether it lists the country asked for and has a usable file. Best first.

## Scope
In (built): `core/agent/dataset_ranking.py` (pure scoring: licence 0 to 40, freshness 0 to 40, coverage 0 to 20, each with a stated reason); `search_hdx_datasets` fetches up to three times the asked-for rows (max 50), ranks, keeps the best `limit`, gains an optional `country` parameter and the fields `licence`, `months_since_change`, `score`, `why`.
Out (not built, needs decisions, see below): loading a STAC scene as a raster, the validation step, a one-prompt report, ranking for sources other than HDX (geoBoundaries, WorldPop and Overpass have no competing candidates to rank).

## Honest limits
The score uses only what the HDX record says. The file is not opened, the licence text is not checked, "changed N months ago" is the record's `metadata_modified` (a metadata edit counts as a change), and "lists the country" is the group list. The weights (40/40/20, freshness steps at 1, 3 and 6 years) are my choice, not measured on real searches; they are constants at the top of the module.

## Decisions needed from the owner for the rest of step E
1. **STAC scene load:** `search_stac_satellite_imagery` returns scene metadata but nothing loads a scene as a raster. Loading reads a remote file of unknown size; it needs a size ceiling (like the download-size setting) and a choice of bands. Proposed: one tool that loads one named asset of one scene through the existing download-size confirmation.
2. **Validation step:** validated against what? Options: against a user-supplied reference layer (confusion matrix on points), or only against internal checks (extent, cloud cover, date gap). The first needs reference data from the user.
3. **One-prompt report:** a task template that chains discovery, fetch, analysis and `write_workflow_report`; depends on 1 and 2 for the imagery case.

## Acceptance (built slice)
1. An open, recent data set listing the country outranks an old one with no licence stated; each result carries three reasons.
2. A data set with no licence, a "not open" licence or an unknown date is reported as such, never scored as if known.
3. Ties keep the search engine's order; the input is not modified; malformed records do not raise.

## Guard tests
`tests/test_dataset_ranking.py` (offline, includes the tool with a mocked HDX reply).

## Rollback
Revert the `search_hdx_datasets` body to the plain query; `dataset_ranking.py` stands alone.

## Status log
- 2026-11-02: first slice built. Not run against the live HDX API (this sandbox cannot reach it), so the real field names (`license_title`, `metadata_modified`, `groups`) are taken from CKAN's documented package schema and from the fields the tool already read; a hand row is on the ledger.
