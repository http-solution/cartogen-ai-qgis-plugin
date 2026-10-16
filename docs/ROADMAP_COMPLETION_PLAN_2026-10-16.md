# Completion plan for the open roadmap items (2026-10-16)

Supersedes nothing: `docs/ROADMAP_QGIS_COVERAGE_2026-10-14.md` stays the record of what was agreed. This note orders the work that is still open
after M0, the first parts of M1 to M7, and the S1 to S4 showcase fixes. It was written at the owner's request ("plan the rest and start completing
all of them"). State below is as of `main` at 252 tools.

## Rules every package follows (unchanged from the roadmap)

1. Pure validation first (Qt-free module, unit-tested offline), then the QGIS part, then a **live test that reads the result back from real QGIS objects** (CI image 4.2.2).
2. Golden routing request(s) for each new ability, coverage rows moved from missing to covered, `build_qgis_coverage.py --write-baseline` in the same PR.
3. Nothing that runs free-form code, reads a user-given URL, or writes outside the project and export folders. Overwriting a file always goes through the existing confirmation.
4. Each package is one PR, merged only on green CI (offline suite, lint, live QGIS job). Honest labels: **CI-checked** is not **hand-tested**.
5. After every three or four packages a release candidate is cut (rc43 next, with M4 and M5 included).

## Work packages, in order

| # | Package | What it adds | Notes / risk |
|---|---|---|---|
| **A** | M3 editing leftovers | Layer filter (definition query) with a screen on the text; move, rotate and scale features; merge selected features; split features by a line; undo/redo of manual edits; change a field's type; start/stop editing, save/discard. | Subset strings are provider SQL: refuse `;`, comments and the denied expression functions. Field type change = rebuild the field, shown in a preview first. |
| **B** | M2 leftovers | Zoom last/next; rename group; layer metadata (title, abstract, keywords); snapping settings; relations; temporal controller range per layer; annotation layer items. | Decorations and anything needing the map canvas cannot be exercised in CI (no canvas): offered with the same honest label as `set_map_view`. 3D only if the CI image has the 3D module (probe first). |
| **C** | M1 leftovers | PostGIS table as a layer (the CI job has a PostGIS service already); virtual layers (SQL over layers, screened); QLR load/save; offline package (`native:package`); NetCDF / ECW through the existing add-by-path tool where the driver exists. | Credentials: only through the QGIS Auth Manager, never typed into chat or stored. A format whose driver is missing in the image is reported as unavailable, not faked. |
| **D** | M7 raster and terrain | Warp/reproject, resample, polygonize, rasterize, proximity, fill no-data, sieve, terrain indices (roughness, TPI, TRI), the ~70 related Processing algorithms. | Output is always a temporary raster in the export folder (the existing raster-output handling); each algorithm must pass the per-process live smoke or is listed with its error. |
| **E** | M6 leftovers | The 77 file-writing algorithms with outputs forced to temporary layers (never a user path); the geometry-quality fixers driven as check-then-fix; select by expression (in-place handling like select by location); aggregate (its list parameter). | The raise-message algorithms are **not** added: they only raise messages in a model and have no use in a chat. |
| **F** | M4 leftovers | Rule-based labels, callouts, masks; diagrams (pie, bar); SVG and font markers; hillshade and contour renderers for rasters; saving symbols to the style library. | Symbol layers other than simple ones are the largest piece; start with SVG markers from local files only. |
| **G** | M5 leftovers | Overview map; guides and grid; reports (one page per feature, via the atlas); world-file and GeoPDF export; chart, 3D map and elevation-profile items where the module exists. | HTML frames stay refused. |
| **H** | M8 new layer types | Probe first (a live test that lists the providers and layer types this QGIS can open), then: point cloud, mesh, vector tiles, 3D tiles, elevation controller, GPS — each only where the probe says it works. | The 34 algorithms waiting on these are added after their layer type loads. |
| **I** | M9 GRASS | The registry already lists 307 GRASS algorithms; probe whether GRASS actually runs in the CI image, then allow-list under the same rule and per-process smoke. | If GRASS is not installed in the image, the package ends with "optional, only when installed" and an honest note. |
| **J** | Prove the showcase services | A live-network test module (S1 DEM download, S3 web research, S4 news, GDELT, Google News, DuckDuckGo) run in CI as non-blocking, so each service is labelled **reached from CI** or **not reachable**, instead of "unverified". | A service that rate-limits or changes its response is reported as such, never mocked into a pass. |

## What this plan does not do

- No HTML frames, no URL pictures, no free Python, no raise-message algorithms (reasons above).
- It cannot hand-test anything. Every package ends **CI-checked**; the owner's hand tests (smoke rows 16 to 18, JIAF blockers) stay the owner's.
- The rc42 release is separate: its zip is built; the GitHub release step needs a repository permission fix (HTTP 403 on release creation).

## Order of execution

A, then C, B, D, E, F, G, J, H, I. A and C first because opening data and editing it are what a QGIS user does all day; J early because it turns "unverified" into a measured statement; H and I last because they depend on what the image provides.
