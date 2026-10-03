# Hydrology engineering tools (watershed / peak flow)

**Date:** 2026-10-04. Dated record of what was integrated and what it does not do; supersede with a new doc rather than editing.

## Origin

The tools were written in the owner's local copy of 1.16.0-rc12 after a live request,

> determine watershed area, steam length, h, slope, return period 20 year, intensity, tc, and peak flow at this location 32° 1'47.39"N, 35°48'21.00"E

was answered without the inputs those numbers depend on. In that session the task matcher picked "Map conflict intensity" from the word "intensity", the router offered unrelated incident tools, and nothing converted the DMS coordinate in code, defined `H`, separated the longest hydraulic flow path from total stream length, tied the rainfall intensity to `Tc`, or refused to guess. The local author's write-up is not reproduced here; this integration re-read the code and rewrote it for this repository rather than copying files.

## What is in the repository

| Piece | Where |
|---|---|
| `parse_dms_location`, `assess_watershed_hydrology_request`, `calculate_rational_watershed_peak_flow` | `src/cartogen_ai/core/agent/tools/engineering_tools.py` |
| Task contract `36.01` "Engineering hydrology and drainage" with slots `dem_source`, `idf_source`, `runoff_coefficient` (no defaults, always asked) | `core/agent/task_register.json` (derived fields from `tools/derive_task_io.py`), `task_matcher.py`, `task_register.py` |
| Router aliases | `core/services/tool_router.py` |
| Prompt rule 53 | `core/agent/prompts.py` |
| Operation type READ for all three | `core/agent/tool_operations.py` |
| Tests | `tests/test_engineering_tools.py` |

## What the tools do

1. `parse_dms_location` converts DMS text to WGS84 decimal degrees in code. For the reported coordinate: latitude 32.0298305556, longitude 35.8058333333 (EPSG:4326). It rejects minutes or seconds of 60 or more, a latitude past 90° or a longitude past 180° (including `90°30'N`), a missing hemisphere, and two components of the same axis.
2. `assess_watershed_hydrology_request` returns `INPUT_REQUIRED` until a DEM source, a local IDF source and a runoff coefficient are explicit, and lists the GIS measurements needed (snap the outlet, condition the DEM, delineate, measure area in a projected CRS, the longest hydraulic flow path, elevations in one datum). It states that this plugin does not do the GIS phase.
3. `calculate_rational_watershed_peak_flow` computes `H`, slope, Kirpich `Tc = 0.0195 L^0.77 S^-0.385` (L in m, S in m/m, minutes) and the Rational Method `Q = 0.278 C i A` (i in mm/h, A in km², Q in m³/s). Called without an intensity it returns `Tc` and asks for the IDF value at that duration. With an intensity it requires a cited source, a duration within 10% of `Tc` (at least a minute), and `C` between 0 and 1. It warns at 0.8 km² (the FHWA limit it quotes) and above 0.453 km² (the calibration range it quotes). Results are labelled `PRELIMINARY_REQUIRES_LOCAL_ENGINEERING_REVIEW`.

## What it does NOT do

- **It does not delineate a watershed**, build a flow path, sample a DEM or read an IDF curve. The GIS phase needs a loaded DEM and a hydrology provider and is not implemented. No part of it has been run in a live QGIS session.
- It does not produce a design value from a coordinate and a return period, by design.
- The equations and limits are the standard published ones as cited by the local author (FHWA HDS-2 and HDS-4; USDA-NRCS NEH 630 chapter 15). I did not re-fetch those documents during the integration, so the quoted limits (80 ha, 112 acres) are unverified here.

## Changes made during integration

- The latitude/longitude limit now compares the whole value; the first version accepted `90°30'N`.
- A Tc-only call (no intensity) is supported, so the model does not have to guess a duration before the first IDF lookup.
- Router alias `tc` removed: aliases match as substrings of the query, so it would have boosted these tools on any query containing "tc" ("match", "batch", "catchment").
- The three tools are classified READ; the register entry gets its derived `prod` value from the repository's derivation tool.

## Why the three failing tests in the local copy failed

Run against the local tree: `test_every_registered_tool_is_classified` (the three tools had no operation type) and the two `tests.test_file_io` register-derivation tests (task 36.01 had `prod: []` where `derive_task_io.py` derives `[".csv"]`). Both are resolved by the steps above. A fourth reported failure, the matcher finding every task from its own title, did not fail in that run.

## Live test (still owed)

See `docs/RC12_LIVE_TEST_AND_AUDIT_PLAN_2026-10-04.md`, section E.
