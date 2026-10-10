# rc23 hand-verification sheet

Zip: the rc23 build made from the current `main` (the file name and SHA-256 are given when it is sent; an earlier rc23 zip, `b9c30d74...`, contained only the hand-test fixes and is superseded). Tracks issue #233. Use a fresh QGIS profile and the rc22 fixtures. Nothing below has been hand-tested by the developer; every row is yours to mark.

**Data and destination.** Every prompt goes to the model provider you configured, together with what the agent reads to answer it (layer and field names, counts, tool results, which can include coordinates). Run these rows only on the synthetic fixtures, with a provider you are authorised to send them to, and write the provider and model at the top of your results. If an egress card names a layer you did not expect, cancel it and report it. Nothing here authorises sending real or sensitive data anywhere. See `docs/RELEASE_LIVE_TEST_SCENARIOS.md`, section 1a.

Mark each row **PASS / FAIL / NOT RUN**, and for a FAIL write what you saw. Keep a screenshot of the chat and the result for each. Rows come from the rc22 matrix (`docs/RC22_RESULT_MATRIX_2026-10-09.csv`); the prompt and expectation are copied verbatim.

| Row | Prompt (type it exactly) | Expected | Result | Notes / evidence file |
|---|---|---|---|---|
| N3 | NEW CHAT. Export smoke_points to CSV at a path where a non-empty file already exists: "Export smoke_points to CSV at outputs/smoke_points.csv". Then Cancel. Repeat and Apply. Then export the same file again straight away. | A confirmation card first; Cancel leaves the file untouched; Apply replaces it; the immediate re-export of the file Cartogen just wrote is silent |  |  |
| N8 | NEW CHAT. "Create a print layout titled Smoke Test Layout for the current map view and export it as a PDF to outputs/smoke_layout.pdf." | Title and file path exactly as asked |  |  |
| N9 | NEW CHAT. "Create a plan: buffer smoke_points by 250 meters, clip the buffers to smoke_boundary, export the result to a GeoPackage at outputs/plan_rc18.gpkg and store a project memory note that the buffer distance was 250 meters." | A local four-step plan (no "web mapping" task); all four steps run; no "No data was retrieved" warning on the plan |  |  |
| H4 | Slope on a DEM in a US-foot projected CRS (e.g. EPSG:2263) vs the same DEM in metres | Slope values agree within rounding (A11) |  |  |
| D5 | `slope_analysis` on a DEM stored in feet: pass `dem_vertical_unit` "ft" | The result states the unit it used (#154) |  |  |
| F3 | Rotate the map canvas to about 30 degrees (View > Rotate map, or the rotation box in the status bar). Ask for a print layout of the current view; export the PDF | The layout's map is rotated and the north arrow is rotated with it, pointing to the top of the page's true north. It is not upright at 0 degrees (#165) |  |  |
| V1 | NEW CHAT. "Show the severity on the map for smoke_admin." (field `severity_smoke`) | Offered or applied through the severity look: five classes yellow to dark red, District_2 and District_3 the darkest, District_1 the palest; legend text a person can read (not `severity_smoke 0.0 - 0.2` only); nothing written into the data |  |  |
| J5 | "Show the JIAF severity on the map." | District_1 orange "3 Severe", District_2 darkest "5 Catastrophic", **District_3 grey "not assessed"**, a legend with the phase names; no unit left invisible |  |  |
| J16 | "Make a map of the JIAF severity for the report." | A layout with the phase legend, title that says what it shows, the not-endorsed note, nothing cut off |  |  |
| T2 | "Import the INFORM risk file <path to smoke_inform.csv> onto smoke_admin by admin_name and show the risk." | Districts in five INFORM classes, District_2 the darkest ("Very high" 6.5 to 10 would hold 7.1); legend shows the class names |  |  |
| V4 | "Rank the three districts in smoke_admin using need and population, both higher is worse, equal weights." then "show the ranking on the map" | Ranked list with the method named; the top-ranked unit drawn dark, the rest muted |  |  |
| J4 | "Calculate the preliminary JIAF figures from <path> and put them on smoke_admin, matching on admin_name." | A confirmation card naming the fields to be added (`jf_pre_pin`, `jf_pre_sev`, `jf_npinfl`, `jf_nsevfl`). Cancel: nothing added. Repeat and Apply: fields added. Reply: District_2 phase 5 with the immediate-notice wording; District_3 has **no** severity and its PiN is a lower bound; national 3,020 |  |  |
| H5 | Export a layer in a projected CRS to GeoJSON, open it in a web viewer or QGIS | It lands in the right place; the file has WGS84 coordinates and no `crs` member (A12) |  |  |
| T4 | "Calculate the average of smoke_dem for each district in smoke_admin and show it on the map." | `zs_` fields added; districts coloured light to dark by the mean elevation; the reply says what the number is (metres only if the DEM unit is known) |  |  |
| F2 | Same layer, manual breaks inside the range (`[8, 11]`) | Three classes with sensible labels, legend matches the map |  |  |
| T6 | "Cluster smoke_image into four groups." | A new raster with four **distinct colours** labelled Class 1 to Class 4, not grey shades; the reply says they are statistical clusters, not land-cover names |  |  |
| V7 | Open Help. | "What's new" shows rc18 with the NEW marks; the humanitarian tools are listed by workflow; the tool and task counts are plausible (they are read from the registries) |  |  |

## Checks that go beyond the original rows

1. **N3 overwrite:** create `outputs/<name>.csv` with a non-empty sentinel first. After the request, the overwrite card must appear and the sentinel must be unchanged until you confirm.
2. **N8/N9 path:** the reply must name an ABSOLUTE path, and the file must exist at that path (unsaved project: in the QGIS profile `cartogen_ai/exports` folder; saved project: next to the `.qgz`).
3. **H4/D5:** export a slope raster; open the `.tif` in QGIS and check it loads and has the right CRS.
4. **F3:** rotate the canvas 30 degrees, create a layout; the layout map and north arrow must show 30 degrees.
5. **V1/J5/J16:** the request must NOT ask "Which hazard specifically?" (drought / heat).
6. **H5/T4:** open a fresh project after a project with a pending plan. A plain "Yes" must not resume the old plan.

Report back: the filled table plus any FAIL screenshots. Row results go into issue #233.
