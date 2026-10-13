---
description: A dated snapshot of what has and has not been verified, and what is left before a stable 1.16.0. The trackers are the live record.
---
<div class="callout warn"><strong>A snapshot, not a live feed</strong>
Written for build {{version}} on {{build_date}}. The <a href="@project/tracker">implementation tracker</a>, the <a href="@project/bugs">bug tracker</a> and the <a href="@project/changelog">changelog</a> are the living record; where this page and they differ, they win.
</div>

## Where the project is

Cartogen AI is a **release-candidate series** for 1.16.0 (current build {{version}}); the last stable release is v1.15.6. Each release states whether it was checked by CI only or also by hand.

| Checked by | State |
|---|---|
| **Offline test suite** ({{tests}} test functions) | Passing on every merged change, on Python 3.10 and 3.11 and Windows, plus `ruff` and `mypy`. |
| **QGIS 4.2.2 live tests in CI** | Passing, including the widget, network, chunking, raster and PostGIS tests. |
| **A person in desktop QGIS** | **Partial.** The last full hand run was rc22 (2026-10-09). The rc37 pack was run on 2026-10-13: of 23 rows, 17 passed, 2 were inconclusive, 2 were not recorded and 2 optional rows were skipped. Rows for rc23 to rc36 and most of the 179 older rows have **not** been hand-run. |

## What the last hand test changed

Found in the rc37 run and fixed in the following candidates:

- **rc38**: `run_allowlisted_processing_algorithm` had failed on every model call since rc24 (a decorator had been left on a helper function), and a false "step did not run" note appeared after incident searches.
- **rc39**: the follow-up that told the model to "generate a representative sample dataset" when no layer existed was removed, after the model put four invented incidents on the map.

These fixes are CI-checked; they have **not** been re-run by hand.

## Before a stable 1.16.0

1. **Hand-test the current candidate**: install gate; the incident prompt must add no invented layer; the Processing-tool follow-up; **Stop heard during a real long job** (still unproven); then the 16 categories and the older rows.
2. **Upgrade gate**: a clean-profile install and an in-place upgrade from v1.15.6.
3. **plugins.qgis.org**: upload and pass its security scan.
4. **Open issues** (46 at the last count): each closes only on a hand-verified pass of its own row, with evidence. Six items sit inside closed issues and need a reopen-or-file decision (DEM vertical unit assumed metres; score writes in `analysis_tools`; raster-unit validation in zonal tools; reprojecting points into the admin CRS; running tasks not invalidated at unload; the wheel not built in a clean environment).
5. **JIAF validation blockers**: a real country's Flags export and a real filled Annex 4 file are needed to close two blockers, or stable ships with them still shown in every result.
6. **Version and notes**: switch to `1.16.0`, remove the pre-release wording, run the release workflow, promote to "Latest".

## Known gaps, stated plainly

- **Invented records by another route.** The wording that invited fabrication is gone, but nothing stops the model adding made-up points with a tool such as `add_point_layer`.
- **Stop on a long job** has been tested with fakes and live tests, not on a large real project; the speed-up from the responsiveness work has not been measured.
- **Python Processing algorithms** (`gdal:*`, `qgis:*`) stay on the main thread by decision; a CI investigation could not reproduce the old crash on a worker thread, but nothing proves it is safe.
- **A route request** used 9 model calls for 5 stops, over the 4-call guideline.
- **Credentialed integrations** (Kobo/ODK, ACLED, GloFAS/CHIRPS, Logistics Cluster, LandScan) are deferred; ACLED and Liveuamap are not searched by the incident tool.
- **The hosted gateway** and the "Cartogen API" provider are a stub. No hosted service exists.
- **GDPR**: the repository carries a code-level review and a DPIA screening worksheet; there is no legal sign-off and no built-in redaction. See [What leaves your machine](@security/privacy).

## Principles that govern this record

Statuses are written in the code and docs as **shipped**, **roadmap** or **unverified**; frozen historical documents are never edited after the fact (a newer dated document supersedes them); and a judgement call is flagged with a recommendation, not decided silently. See [Contributing](@development/contributing).
