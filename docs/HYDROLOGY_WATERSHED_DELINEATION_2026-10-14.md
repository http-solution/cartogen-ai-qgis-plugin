# Watershed delineation (showcase S1), 2026-10-14

This supersedes the "does not delineate a basin" limit in `docs/HYDROLOGY_ENGINEERING_TOOLS_2026-10-04.md`. That document is a dated record and is not edited; read it for the original finding.

## What was wrong

The owner's request "determine watershed area, stream length, H, slope, return period 20 year, intensity, Tc and peak flow at this location 32°01'47.39"N, 35°48'21.00"E" failed in a live demonstration. Reading the code:

- task 36.01 stopped with three blocking questions (DEM, IDF curve, runoff coefficient) before doing anything;
- no tool could measure a basin, a flow path or H from a DEM, so area, length and H could not exist, and the 2026-10-04 tools correctly refused to invent them.

## What it does now

1. `parse_dms_location` turns the coordinate into WGS84 decimals in code.
2. `fetch_dem` (existing) downloads Copernicus GLO-30 (about 30 m, a surface model) around the point if no DEM covers it.
3. `delineate_watershed` (new) reads the DEM and, with the D8 method in `watershed_delineation.py`, returns the basin area, the longest hydraulic flow path, H (original DEM, upstream end minus outlet), the main-channel slope and the Kirpich Tc. It adds the basin, flow path and outlet to the project. The outlet is moved onto the derived channel within a snap distance (default 300 m) and the move is reported.
4. It does **not** invent the two design inputs. Its reply asks once for the local IDF intensity at Tc (with source) and a runoff coefficient C, and shows textbook C ranges that are never applied.
5. `calculate_rational_watershed_peak_flow` (existing) computes the discharge from the measured numbers and the user's two inputs, and still refuses a guessed intensity or C.

Task 36.01 no longer blocks up front: the DEM is automatic, and the two design inputs are asked after the measurements, when the user can see what they are for.

## Method and limits (also in every reply)

Priority-flood depression filling (Barnes et al. 2014), D8 steepest-descent directions, flow accumulation, snapping to the highest accumulation, upstream traversal for the basin, greatest flow distance for the longest path. Limits: D8 on a 30 m surface model that includes buildings and trees; constant cell size over the window; a basin touching the window edge may be truncated (flagged); windows over 400 000 cells are refused so the GUI does not freeze; the Rational Method limit (0.8 km2) and Kirpich's calibration area (0.453 km2) are flagged when exceeded.

## Verification status

- `tests/test_watershed_delineation.py` (13 tests): the numerical core on synthetic terrain with known answers (two valleys and a ridge, a spurious pit, snapping, refusals).
- `tests/test_watershed_tools.py`: outlet parsing, design-input wording, warnings, routing of the reported query.
- `tests/test_watershed_tools_live.py`: the QGIS tool on a synthetic GeoTIFF in real EPSG:4326 at the reported coordinate. Written without a QGIS install; its first CI run is its first execution.
- **Not verified:** a real Copernicus DEM at the reported location, in a running QGIS session. The first real use is the first such check, and the owner should compare the numbers with the earlier report from the city-planning engineer.
