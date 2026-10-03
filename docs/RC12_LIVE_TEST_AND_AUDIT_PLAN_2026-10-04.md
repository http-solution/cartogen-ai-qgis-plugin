# rc12 live test and audit plan

**Date:** 2026-10-04. A dated plan, not a result: nothing below has been run by hand yet. Record results in a new dated doc and on the
linked issues; do not edit this one. An issue is closed only on a hand-verified pass.

**Build under test:** the `cartogen-ai-v1.16.0-rc12` GitHub pre-release built from `main` (the commit is in the release notes).
Install the **attached zip** (Plugins > Manage and Install Plugins > Install from ZIP), not "Source code (zip)". Restart QGIS, then
confirm Settings shows version `1.16.0-rc12` and the installed folder contains `engineering_tools.py` and `project_tidy_tools.py`.

**Data:** the Yemen/Sanaa project used in the rc10/rc11 smoke tests (roads with `oneway` F/T/B and `speed_kmh`, health facilities,
`yem_ppp_2020` WorldPop, an HDX admin layer). Save the project before starting; several checks need a saved project.

## A. Install and start-up (no issue; gate for everything else)
1. Panel opens at start-up; API key still present. 2. No Python traceback in the QGIS log on load. 3. Settings > "What gets kept
and shown" unchanged.

## B. Checks for fixes made after the rc11 smoke test (rc12)
| # | Prompt / action | Expected | Issue |
|---|---|---|---|
| B1 | "Add a point at 4902068.0, 1799912.0." with a 3857 project | Asks which CRS, places nothing | #119 |
| B2 | Repeat the same service-area request three times | One origin layer; no new origin/result sets | #121 |
| B3 | "Which health facilities are beyond one hour's travel from <point>?" | Green/red styled layer is kept; no model re-style | #122 |
| B4 | Send a tall confirmation card, then scroll up while it works | View does not jump back; bubbles show clock times | #124, #125 |
| B5 | Reply "yes" to a destructive confirmation | A hint, not a model call; one live card only | #88, #125 |
| B6 | Paste "template: access_map" | No analysis starts | #130 |
| B7 | Service-area from a point beside a one-way street | Result differs from the two-way result | #132 |
| B8 | Download admin boundaries twice | One layer, labelled, pale fill | #127 |
| B9 | "Population within the one-hour service area" | Concave-hull headline plus road-buffer and convex-hull (upper bound) figures | #123 |
| B10 | Open an old project; ask "tidy the project layers" (report), then apply | Lists duplicates/black raster/scratch layers; apply hides extra copies, restyles the raster, saves scratch layers (needs a saved project); deletes nothing | #120, #128 |
| B11 | "Fastest route from A to B" on the roads | Estimated time, labelled estimate, speed basis, route length; not called "fastest" if shortest | #131 |
| B12 | Access-map print layout (PNG and PDF) | Legend lists the reach polygon; body panel sized to its text; thin pale graticule | #129 |
| B13 | HTML dashboard with basemap "none" | Markers and layer control draw (open it in a browser) | #84 |

## C. #75 claim footnote (new behaviour, needs a real model)
Ask a data question that invites background detail, for example "What population lives within one hour of this point, and what
region is that in?" after a service-area run. **Pass:** figures that came from tools carry no note; any place name, million-plus total,
file size or terrain wording the tools did not return is listed in a "Not from a tool result in this conversation" footnote; the answer text
is unchanged. **Fail to record:** a note on a figure that did come from a tool (false positive), or an invented claim with no note (miss).
Write down each case with the exact wording; the heuristic is limited to three claim shapes.

## D. Previously unverified items
C2, C3, C4, C12 (the original carry-over checks), C13 (clean profile install) and C14 (upgrade from the previous zip), plus the
sandbox refusal checks of C7.

## E. Engineering hydrology tools (new; see `HYDROLOGY_ENGINEERING_TOOLS_2026-10-04.md`)
H1. Prompt: `determine watershed area, steam length, h, slope, return period 20 year, intensity, tc, and peak flow at this location
32° 1'47.39"N, 35°48'21.00"E`. **Expected:** the task is recognised as engineering hydrology (not "Map conflict intensity"); the
DMS point is converted to 32.0298305556, 35.8058333333; the reply asks for a DEM, a local IDF source and a runoff coefficient and does
**not** state an area, flow length, H, slope, Tc, intensity or discharge.
H2. Give explicit numbers with a call to the calculator without an intensity (area 0.5 km², length 1.2 km, elevations 910 and 850 m, 20
years). **Expected:** Tc ≈ 14.5 min is returned with a request for the IDF value at that duration. H3. Give an intensity at the wrong
duration. **Expected:** an error naming the computed Tc. H4. Give a cited intensity of 55 mm/h at a duration of 14.5 min, with C = 0.4. **Expected:** Q ≈ 3.06 m³/s
labelled preliminary. H5. Try an area of 0.9 km². **Expected:** the FHWA-limit warning.
**Known limit:** the plugin does not delineate basins; a basin must come from elsewhere.

## F. Audit scope
The external architectural audit (32 findings) is tracked in #169, one issue per finding (#137-#168). They are confirmed in the code by reading,
not by execution. For the audit round, in priority order:
1. **Execution policy and thread boundaries:** #137 (allowlisted `gdal:rastercalculator`), #138 (snapshots off the main thread), #147
   (turn not bound to its project).
2. **Data ownership:** #143, #144 (edit sessions, unchecked writes), #145, #146 (isolated-script results), #149, #150 (egress gate
   and lineage gaps), #151 (PostGIS).
3. **Measurement correctness:** #141 (SI units), #142 (mixed CRS), #148 (bounding-box nearest neighbour in
   `classify_facilities_by_access`), and #152-#155.
4. **Native provider contracts:** #139, #140, #156, #157.
5. **Packaging, layout, lifecycle:** #158-#168.
Reproduce each with a real-QGIS fixture before fixing; the acceptance line in each issue says what to test.

## G. Known open items going in
#75 (needs the live check in C), and every issue in the earlier sweep that is still awaiting a hand re-test. The QGIS 4.2.2 audit's
live-test gating finding concerns a file that is not in this repository.

## H. Recording
For each row record: build, date, pass/fail, the exact prompt, what was seen, and screenshots or log lines. Close an issue only on a pass.
