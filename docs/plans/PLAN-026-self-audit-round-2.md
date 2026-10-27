# PLAN-026: self-audit round 2 (units, stale state, test design, evidence)

Status: in progress

## Goal
PLAN-024 asked "does any tool crash or hang?". Round 2 asks the questions a crash test cannot: does a tool give the wrong NUMBER, in the wrong UNIT, from the wrong STATE, and was the thing we measured the thing we meant? It starts from the three defects the owner's hand runs of 1.18.2 and 1.18.3 found (a buffer applied in degrees, a damage score with its sign inverted, a CSV that could never load as a table), names each as a class, and sweeps the whole code base for the same class instead of fixing only the instance.

## Scope
Defect classes swept, with the method and the result:

| # | Class | How it was swept | Found | Status |
|---|---|---|---|---|
| A | Distance, radius, tolerance or cell size taken in the layer's CRS units while the user means metres (the route-risk buffer, C9) | Static scan of every function using buffer, DISTANCE, TOLERANCE, distance(); then every tool parameter whose name or description is a length | `find_nearest_features` said "distance in meters" but wrote degrees on EPSG:4326; `obfuscate_sensitive_points` (jitter radius, grid cell size), `hotspot_analysis` radius, `simplify_geometry` tolerance and `interpolate_surface` cell size accepted 1000 on a latitude/longitude layer with no warning | fixed: `distance_m` added to the nearest-feature result; a shared guard `degrees_value_problem` refuses a value of 1 degree or more for a lat/lon layer and says how to convert; live and offline tests |
| B | A signed quantity ranked as if larger meant worse (damage score, D7) | Read every min-max or ranking path that takes a raw field | the damage tool was the only one fed by a difference raster; the other severity tools take fields chosen by the user and have an explicit `invert_indicators` | fixed in PR 453 |
| C | State left on the layer by an earlier run is read as this run's result | Read every use of QgsZonalStatistics and of fixed output field names | `calculate_damage_exposure_severity` added `chg_mean` to the admin layer and on a second run read the OLD column (QGIS wrote `chg_mean_2`); after an upgrade the stale signed values would have scored the districts | fixed: each run uses a prefix not yet on the layer and reads that column; live and offline tests. Left open: the zonal columns stay on the layer (a file-based admin layer keeps them) |
| D | A tool whose own instructions cannot be followed (the CSV, D5) | Read the message each tool returns against what its description says | `load_tabular_data_as_layer`: "omit the coordinate arguments to load a table" returned the suggestion again | fixed in PR 449 (`as_table`) |
| E | Test design faults that look like tool faults | Re-derived each expected value of the runbook from the fixtures | B5 cap bound every area, C6 had no candidate sites, C8 had one origin-destination pair, D8 loaded a table instead of points | fixtures and runbook corrected (PR 454) |
| F | Task matcher sends a request to a task whose tools cannot do it | Ran the matcher on every source-named prompt of the runbook | UCDP, GDACS, HDX-search prompts matched "Map ..." tasks | fixed in PR 454 |
| G | Error handling that hides faults | AST count of every `except Exception` handler and every `contextlib.suppress(Exception)` | 514 broad handlers, 0 that swallow with a bare `pass`; 88 log or re-raise, the rest return an error dict; 121 `suppress(Exception)` sites, kept as the documented "best effort, never raises" idiom | recorded as the baseline; no change |
| H | Lint beyond the enforced rule set | `ruff --select S,B,BLE,PLW,PERF,RUF,SIM` | 504 blind-except (the same handlers as G), 24 unused `noqa`, 10 try-except-in-loop; no security (S) or bugbear (B) finding | recorded; the 24 unused `noqa` are a clean-up for a quiet release |

Out, with reason: the elevation-profile render that is intermittently empty in CI (#379) needs a real QGIS to debug; three model-behaviour rows (D3, D4, S5) need the per-prompt log; a numeric known-answer test for every one of the 296 tools is the PLAN-023 programme, not this plan.

## Acceptance
1. Offline suite, ruff, `tools/ledger_guard.py` pass.
2. CI live passes, including `test_nearest_distance_metres_live` and the second-run test in `test_damage_direction_live`.
3. Hand (owner): `find nearest hospital to each village` on a lat/lon layer shows `distance_m` in metres; `blur the points by 1000` on a lat/lon layer is refused with the conversion; run the damage score twice and get the same ranking.

## Guard tests
tests/test_layer_checks_degrees.py::TestDegreesValueProblem::test_a_metre_sized_number_on_a_latlon_layer_is_refused_with_the_conversion
tests/test_nearest_distance_metres_live.py::TestNearestInMetres::test_latlon_layers_get_distance_m_close_to_the_real_distance
tests/test_free_zonal_prefix.py::TestFreeZonalPrefix::test_a_taken_prefix_moves_on
tests/test_damage_direction_live.py::TestDamageDirection::test_a_second_run_does_not_read_the_first_runs_stale_field

## Rollback
Each fix is its own commit; revert it. A released fix that misbehaves gets a patch release.

## Status log
- 2026-10-26: plan written; sweeps A to H run. Fixes for A and C written with offline tests; the live tests were written without a local QGIS, so CI's first run is their first execution. Not hand-verified.
- 2026-10-27: PR 455 merged (live CI green). Version 1.18.4 prepared together with the GDACS retry (PLAN-025); not hand-verified.
