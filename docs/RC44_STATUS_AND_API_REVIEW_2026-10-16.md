# rc44: what was implemented, and what the QGIS 4.2.3 reference check found (2026-10-16)

Source of the check: the "QGIS 4.2.3 Developer Reference" companion (PyQGIS 4.2 API pages with signatures, 465 Processing tools, 466 expression
functions). It describes itself as an independent companion built without a QGIS runtime; it targets 4.2.3 while the plugin's CI runs 4.2.2. I used
it as data only (nothing in it was run). Scope of the check: every method NAME the plugin calls, against the 4.2 Python API; argument lists and
return types were not compared except where a live CI test already ran the call. Nothing here is hand-tested.

## 1. What rc44 contains (published as `cartogen-ai-v1.17.0-rc44`, commit b34bd38d)
| Area | Added in rc44 | Evidence |
|---|---|---|
| Symbology (8 tools) | rule-based labels, label callouts and masks, pie/bar diagrams, SVG and font markers, hillshade and contour renderers, symbol library (save, list, apply) | CI live test per tool, read back from real layers; looks not viewed |
| Print layouts (5 tools + export options) | overview (locator) map, guides and grid, atlas, bar/line/pie chart item, elevation-profile item; world file and GeoPDF export | CI live: items created and settings read back; rendering not viewed; GeoPDF not opened elsewhere |
| New layer types (3 tools) | point cloud (COPC/EPT; plain .las/.laz needs the PDAL provider), vector tiles (https XYZ, .mbtiles, .vtpk), 3D Tiles | CI live: refusals plus synthetic sources accepted; no real data opened |
| Elevation (2 tools) | layer elevation settings (raster surface; vector clamping/extrusion), project terrain (flat or DEM) | CI live round trips; effect on a profile or 3D view not checked |
| Processing (160 algorithms) | 154 GRASS (only where GRASS is installed), 6 mesh | each ran once in CI on tiny synthetic data; correctness of results not checked |
| Integration fixes | undo for 9 more tools, privacy gate sees layers inside virtual-layer SQL, advisories for protected layers, task-library links, colour ramps for continuous raster/GRASS/mesh results, animation routing | CI live (undo, advisories); offline (SQL scan, routing, styling maps) |
Totals: 294 tools (+18 over rc43), 427 allow-listed Processing algorithms (+160). Not built: GPS, PDAL algorithms, 3D map layout item.

## 2. What the reference check found (all in code that shipped in rc43 or rc44 or earlier)
A call to a method that does not exist in the QGIS 4.2 Python API fails only when that line runs on a real object. The unit tests used mocks that accept
any method name, one call sat under `contextlib.suppress`, and CI has no map canvas, so none of these ever failed in CI.

| # | Where | Wrong call | Real API | Effect before the fix | Since |
|---|---|---|---|---|---|
| 1 | `zoom_history` (project_ops_tools.py) | `QgsMapCanvas.previousExtentsAvailable()` / `nextExtentsAvailable()` | do not exist (only the signals `zoomLastStatusChanged` / `zoomNextStatusChanged`) | the tool raised AttributeError on a real canvas: **never worked** | rc43 |
| 2 | `diagnose_topology` (vector_tools.py) | `QgsGeometry.isGeomValid()` | `isGeosValid()` | AttributeError on the first geometry: the topology check (also used by the QA gate) failed on every real layer | long-standing |
| 3 | `get_qgis_proxy_dict` (core/proxy.py) | `QgsNetworkAccessManager.fallbackProxySettings()` | `fallbackProxy()` | AttributeError swallowed by `contextlib.suppress`: **proxy detection silently returned "no proxy" for every user** | long-standing |
| 4 | `apply_representation` (representation/applier.py) | `QgsPointDisplacementRenderer.setCircleRadiusSymbol(None)` | no such method (the API has `setCircleRadiusAddition`) | applying the point-displacement representation errored | long-standing |
`QPageLayout.paintRectPixels` (PDF export) looked suspicious but is a real Qt method.

**Consequence for the hand test:** rc44 as published contains all four. In the hand-test sheet, `zoom_history` will fail, and so will the
point-displacement representation, `diagnose_topology` and proxy use behind a corporate proxy; do not count them as new regressions.

## 3. Fixes and the guard (this branch)
* `zoom_history` steps the canvas history and treats an unchanged extent as "nothing to go back to"; `diagnose_topology` uses `isGeosValid`; proxy detection
  uses `fallbackProxy`; the nonexistent displacement call is removed.
* Tests: offline (a `MagicMock(spec=[...])` canvas, which raises on a missing method, replaced the permissive mock) and three CI live tests on real objects
  (`tests/test_api_reference_fixes_live.py`).
* New ratchet `tests/test_pyqgis_call_names.py` with `tests/fixtures/pyqgis_4_2_names.txt` (20,064 API names, 338 KB): any camelCase method name called in
  `src/` that is neither in the QGIS 4.2 API nor on a reviewed Qt list fails the build. It fails on `isGeomValid` if reintroduced (checked).
  Limit: it catches a name that exists nowhere, not a real name called on the wrong object.

## 4. Still unverified
Argument lists and return types of the QGIS calls were not compared with the reference. Everything the CI live job executes is verified by running; code that
needs a canvas, `iface`, a GPS, or a GUI (zoom_history after this fix, set_map_view, go_to_bookmark, annotations) still has no automated test.
A fix needs a release: these four fixes would ship in rc45 (not cut).
