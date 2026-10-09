# rc22 live smoke test: triage and fixes (2026-10-09)

Source: the owner's hand run of the rc22 zip (SHA-256 `44bd1742...8414c`) on QGIS 4.2.3 with Gemini (`gemini-flash-latest`), saved as
`docs/RC22_LIVE_SMOKE_REPORT_2026-10-09.md` and `docs/RC22_RESULT_MATRIX_2026-10-09.csv` (screenshots and logs stay with the owner).
Result: 120 rows tracked, **32 PASS, 33 FAIL, 6 INCONCLUSIVE, 49 NOT RUN** (most NOT RUN: provider credits ran out, the Yemen fixture and the
PostGIS server were not available, and the readability rows need a human colleague). Nothing in this file is hand-tested by the fixer: the
fixes below have offline tests and, where marked, a live QGIS 4.2.2 Docker run.

## What the run confirmed works (rc22 audit fixes, live)
H3 equalisation keeps every valid cell (low pixels map to 1, NoData 0); H4/D5 foot-unit slope identical to the metre grid; H5 fresh-project GeoJSON is
WGS84 with no `crs` member; H10 the 80M-value size guard; H2 Stop then a new request; F1 out-of-range manual break rejected; F4/F5/F6/N1/N2/N4/N7/R4/R5/T7/V5/K2/K5.
H8: 225 zonal rows and the three `zs_` fields, Stop acknowledged (the dedicated background worker itself was not exercised because the model chose another tool).

## Defects found in the plugin code, now fixed
| Rows | Finding | Cause | Fix |
|---|---|---|---|
| N3, N8, N9, H4 | Replies said a CSV/PDF/GeoPackage/raster was exported to `outputs/...`, but the file was absent and no overwrite card appeared | A relative `output_path` was used verbatim, so it resolved against the QGIS process working directory, not the project; the overwrite check looked there too | `tools/_paths.py::resolve_output_path` anchors relative paths to the project folder (profile export folder when unsaved) in every tool that takes an `output_path`; the result reports the absolute path |
| H4, D5 | A slope/other raster result could not be exported (the vector exporter failed on it) | `export_layer` was vector-only | `export_layer` now writes a GeoTIFF for a raster layer (live-tested) |
| F3 | A canvas rotated 30 degrees gave a layout map and north arrow at 0 | The layout map ignored the canvas rotation | The layout map takes the canvas rotation (arrow is linked, so it follows) |
| V1, J5, J16 (T2) | "Show the severity on the map" and "Show the INFORM risk on the map" asked "Which hazard specifically?" (drought / extreme heat) | The task matcher chose "Map drought severity" / "Map extreme-heat risk" on the shared words map + severity/risk | A task that names one specific hazard is only a candidate when the request names that hazard |
| T2, V4, J4 | After "Apply edit", the display step of the request (show on the map) never ran | Apply runs the tool with no model turn; only requests with an explicit sequence or two verbs resumed | A confirmed data-writing tool plus a show/map/style request now resumes the rest of the request |
| H5 (first try), T4, J4, V4, A4/A5 | An earlier project's plan, pending Apply or intent resurfaced in a fresh project and a plain "Yes" resumed it | The agent is cached across projects; only the chat history was reloaded on a project change | A project change also drops the plan, pending previews, carried-over tools, grounding and last tool call |
| F2 | An explicit "pale yellow to dark red" ramp was ignored (Viridis) | `apply_graduated_style` had no colour parameters | New optional `color_from` / `color_to` (plain colour words or hex) |
| T6 | "Cluster smoke_image into four groups" was answered with "unavailable" although `unsupervised_classification` exists | "cluster" did not reach the image-classification task | The matcher maps cluster/clustering/k-means to that task |
| V7 | Help explained "(new)" marks although no tool carried one | The sentence was unconditional | It is shown only when a mark is shown |

## Still open after this round (not fixed; see issues)
* **Model behaviour, not code.** Invented or wrong facts in replies (J9 District_4, J15 wrong preliminary 1200, T4 overall mean, J3 Syria/Damascus instead of the
  stated Smokeland, T3 claimed class colours that were not applied, T6 invented Damascus). These need the response guard / model choice, not a one-line fix.
  Related existing issue: #75 (fabricated tool output).
* **Reply wording requirements** (V3, V8, J1, J4, J6, J7, J10, J14, V2/J6 class-boundary wording, J8 dollar suffix): prompt-level; some may be a quality bar for
  the chosen model (a flash model). Re-test with the model the release is recommended for.
* **Legend lists layers hidden under opaque polygons** (V6, J16, F3): the legend filters by visibility and map extent, not by being covered. Existing issue #165.
* **A4/A8 preview invents a CSV deliverable** for an imagery/footprint request; **R2/A1 hub-siting Yes produced no calculation**; **J13 invented paths then hit the tool limit**; **T3 UNOSAT points left single-symbol and below the admin layer**.
* **N5/A8** a 54.1 MB tile stopped at the 50 MB confirmation gate: the gate worked; the download decision is the owner's.
* **Not run** (credits, fixtures, humans): R7, N6, A2, A3, H1, H6, H7, H9, F7, D1-D4, D6-D14, V9, V10, T5, T8, K1, K3, K4, P1-P20, and the install/restart gates.
