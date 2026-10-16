"""The allow-list for run_allowlisted_processing_algorithm (point 19's
"larger question" -- docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md
-- a real Tier 2 slice of the tiered allow-list model the proposal
describes: declarative tools / allow-listed Processing algorithms /
approved internal functions / PyQGIS as a rare, isolated last resort).

Every id below is derived from this codebase's own existing
processing.run() call sites (grep -rn 'processing\\.run' across
agent/tools/*.py, including each shared helper's callers --
vector_tools._run_and_add's ~18 callers, raster_tools._run_raster_and_add's
13 callers) -- not a new judgment call about what's "safe," just making
the trust boundary this codebase already operates under explicit and
reusable. This list is a snapshot as of 2026-09-11; if a future tool adds
a new processing.run() call, add its algorithm id here too, or
run_allowlisted_processing_algorithm and that new tool will silently
diverge from what this codebase actually trusts."""

ALLOWED_ALGORITHM_IDS = frozenset({
    # vector_tools.py (native:buffer, plus ~18 _run_and_add callers)
    "native:buffer",
    "native:clip",
    "native:intersection",
    "native:union",
    "native:symmetricaldifference",
    "native:difference",
    "native:convexhull",
    "native:voronoipolygons",
    "native:delaunaytriangulation",
    "native:joinbynearest",
    "native:multiparttosingleparts",
    "native:simplifygeometries",
    "native:mergevectorlayers",
    "native:joinattributesbylocation",
    "native:joinattributestable",
    "native:centroids",
    "native:reprojectlayer",
    "native:fixgeometries",
    "native:dissolve",
    "native:selectbylocation",
    # logistics_tools.py (network analysis)
    "native:shortestpathpointtopoint",
    "native:shortestpathpointtolayer",
    "native:serviceareafrompoint",
    # raster_tools.py (native: + gdal: + saga: + qgis: interpolation)
    "native:hillshade",
    "native:slope",
    "native:aspect",
    "gdal:cliprasterbymasklayer",
    "gdal:merge",
    "gdal:pansharp",
    "qgis:idwinterpolation",
    "qgis:tininterpolation",
    # styling_tools.py
    "qgis:heatmapkerneldensityestimation",
})

# 2026-10-01 (visualization/analysis gap analysis): in-memory analysis algorithms QGIS ships that the project's tools
# did not expose. Each is a single OUTPUT-sink algorithm with no expression, script or file-path parameter, so the tool's
# "no code runs" property still holds; expression-taking algorithms (extractbyexpression, aggregate, refactorfields) were
# left OUT on purpose. This is a trust-boundary change: it is flagged in the PR for the owner. Every id is checked against
# the real QGIS processing registry by tests/test_output_style_live.py, so a wrong id fails CI instead of the model.
ANALYSIS_EXTENSIONS = frozenset({
    "native:countpointsinpolygon",    # facilities (or incidents) per admin area: the basic coverage-gap table
    "native:creategrid",              # rectangle/hex grid for density and exposure aggregation
    "native:extractbylocation",       # features within/intersecting another layer, as a new layer
    "qgis:statisticsbycategories",  # count/sum/mean per category
    "native:dbscanclustering",        # density clusters of points (incidents, facilities)
    "native:kmeansclustering",        # k clusters of points (service-region sketches)
    "native:rastersampling",          # sample a raster (e.g. population) at points
    "native:zonalstatisticsfb",       # zonal statistics, feature-based (qgis:zonalstatistics is the older form)
    "native:reclassifybytable",       # reclassify a raster by a value table (suitability classes)
    "native:cellstatistics",          # per-cell statistics across several rasters
})
ALLOWED_ALGORITHM_IDS = frozenset(set(ALLOWED_ALGORITHM_IDS) | set(ANALYSIS_EXTENSIONS))


# M6a (roadmap 2026-10-14): the geometry family. Rule, applied mechanically to docs/qgis_coverage/processing_matrix.csv (772 algorithms
# dumped from the real QGIS 4.2.2 registry): disposition CANDIDATE, wave '2A geometry', and every parameter is one of source / sink /
# number / distance / area / boolean / enum / field / extent / point. No expression, string, file, raster, band or multi-layer parameter,
# so "no code runs" and "output is memory only" both still hold. The 10 geometry candidates that failed the rule stay off (extract M/Z,
# specific vertices, line intersections with a string, the three multi-layer overlays, set Z/M from raster, eliminate selected). An id stays
# here only while tests/test_processing_allowlist_all_live.py runs it successfully in real QGIS; a failing one is moved to NOT_YET with
# the reason in tests/_processing_live_rows.py (GEOMETRY_REJECTED) and removed from this set.
# First live run (2026-10-14, QGIS 4.2.2): 73 of 78 ran; native:concavehull hung (60 s timeout) and native:transect / native:transectfixeddistance
# crashed the process (SIGSEGV), so those three are NOT here. A second run: qgis:variabledistancebuffer and
# qgis:rectanglesovalsdiamondsvariable (Python algorithms) raised a traceback on polygon, line and point input even with a numeric field.
GEOMETRY_FAMILY = {
    "native:affinetransform": "Affine transform",
    "native:antimeridiansplit": "Geodesic line split at antimeridian",
    "native:approximatemedialaxis": "Approximate medial axis",
    "native:boundary": "Boundary",
    "native:boundingboxes": "Bounding boxes",
    "native:bufferbym": "Variable width buffer (by M value)",
    "native:checkvalidity": "Check validity",
    "native:collect": "Collect geometries",
    "native:concavehullbyfeature": "Concave hull (by feature)",
    "native:convertgeometrytype": "Convert geometry type",
    "native:converttocurves": "Convert to curved geometries",
    "native:coveragesimplify": "Simplify coverage",
    "native:coverageunion": "Dissolve coverage",
    "native:coveragevalidate": "Validate coverage",
    "native:deleteholes": "Delete holes",
    "native:densifygeometries": "Densify by count",
    "native:densifygeometriesgivenaninterval": "Densify by interval",
    "native:dropmzvalues": "Drop M/Z values",
    "native:explodelines": "Explode lines",
    "native:exportaddgeometrycolumns": "Add geometry attributes",
    "native:extendlines": "Extend lines",
    "native:extractbyextent": "Extract/clip by extent",
    "native:extractvertices": "Extract vertices",
    "native:extrude": "Extrude",
    "native:filterverticesbym": "Filter vertices by M value",
    "native:filterverticesbyz": "Filter vertices by Z value",
    "native:forceccw": "Force polygons counter-clockwise",
    "native:forcecw": "Force polygons clockwise",
    "native:forcerhr": "Force right-hand-rule",
    "native:interpolatepoint": "Interpolate point on line",
    "native:keepnbiggestparts": "Keep N biggest parts",
    "native:linesubstring": "Line substring",
    "native:mergelines": "Merge lines",
    "native:minimumboundinggeometry": "Minimum bounding geometry",
    "native:minimumenclosingcircle": "Minimum enclosing circles",
    "native:multiringconstantbuffer": "Multi-ring buffer (constant distance)",
    "native:offsetline": "Offset lines",
    "native:orientedminimumboundingbox": "Oriented minimum bounding box",
    "native:orthogonalize": "Orthogonalize",
    "native:pointonsurface": "Point on surface",
    "native:pointsalonglines": "Points along geometry",
    "native:poleofinaccessibility": "Pole of inaccessibility",
    "native:polygonize": "Polygonize",
    "native:polygonstolines": "Polygons to lines",
    "native:projectpointcartesian": "Project points (Cartesian)",
    "native:promotetomulti": "Promote to multipart",
    "native:rectanglesovalsdiamonds": "Rectangles, ovals, diamonds",
    "native:removeduplicatevertices": "Remove duplicate vertices",
    "native:removenullgeometries": "Remove null geometries",
    "native:removepartsbyarea": "Remove parts by area",
    "native:removepartsbylength": "Remove parts by length",
    "native:reverselinedirection": "Reverse line direction",
    "native:rotatefeatures": "Rotate",
    "native:roundness": "Roundness",
    "native:segmentizebymaxangle": "Segmentize by maximum angle",
    "native:segmentizebymaxdistance": "Segmentize by maximum distance",
    "native:setmvalue": "Set M value",
    "native:setzvalue": "Set Z value",
    "native:singlesidedbuffer": "Single sided buffer",
    "native:smoothgeometry": "Smooth",
    "native:snapgeometries": "Snap geometries to layer",
    "native:snappointstogrid": "Snap points to grid",
    "native:splitlinesbylength": "Split lines by maximum length",
    "native:splitwithlines": "Split with lines",
    "native:subdivide": "Subdivide",
    "native:swapxy": "Swap X and Y coordinates",
    "native:taperedbuffer": "Tapered buffers",
    "native:tightconcavehullofpolygons": "Fill gaps between polygons",
    "native:translategeometry": "Translate",
    "native:wedgebuffers": "Create wedge buffers",
    "qgis:knearestconcavehull": "Concave hull (k-nearest neighbor)",
    "qgis:linestopolygons": "Lines to polygons",
    "qgis:pointsdisplacement": "Points displacement",
}
ALLOWED_ALGORITHM_IDS = frozenset(set(ALLOWED_ALGORITHM_IDS) | set(GEOMETRY_FAMILY))

# M6b (roadmap 2026-10-14): the table family, same mechanical rule as M6a applied to wave '2B table and selection' (36 candidates). 11
# pass it. The rest stay off because they carry a string, crs or `vector` (in-place) parameter: add/rename field, add X/Y, assign or define
# projection, create index, truncate, random/attribute selection, select within distance, save selected, execute SQL, refactor, etc.
# Each id stays only while tests/test_processing_geometry_family_live.py runs it successfully in real QGIS.
TABLE_FAMILY = {
    "native:deleteduplicategeometries": "Delete duplicate geometries",
    "native:dropgeometries": "Drop geometries",
    "native:extractwithindistance": "Extract within distance",
    "native:filterbygeometry": "Filter by geometry type",
    "native:deletecolumn": "Drop field(s)",
    "native:retainfields": "Retain fields",
    "native:removeduplicatesbyattribute": "Delete duplicates by attribute",
    "native:randomextract": "Random extract",
    "native:randomextractwithinsubsets": "Random extract within subsets",
    "native:joinbylocationsummary": "Join attributes by location (summary)",
    "native:detectvectorchanges": "Detect dataset changes",
}
ALLOWED_ALGORITHM_IDS = frozenset(set(ALLOWED_ALGORITHM_IDS) | set(TABLE_FAMILY))
# M6c: wave '2C analysis and creation' plus the geometry-check algorithms of '2E' and qgis:texttofloat, same rule. Left off on purpose: the
# native:fixgeometry* algorithms (they need the error layer a matching check produces, so a plain request cannot drive them), the Nominatim
# geocoder (network), native:filter (model-only, no output sink) and the four algorithms M6a already rejected.
ANALYSIS_FAMILY = {
    "native:arrayoffsetlines": "Array of offset (parallel) lines",
    "native:arraytranslatedfeatures": "Array of translated features",
    "native:checkgeometryangle": "Small angles",
    "native:checkgeometryarea": "Small polygons",
    "native:checkgeometrydangle": "Dangle-end lines",
    "native:checkgeometrydegeneratepolygon": "Degenerate polygons",
    "native:checkgeometryduplicate": "Duplicated geometries",
    "native:checkgeometryduplicatenodes": "Duplicated vertices",
    "native:checkgeometryfollowboundaries": "Polygons exceeding boundaries",
    "native:checkgeometryhole": "Holes",
    "native:checkgeometrylineintersection": "Lines intersecting each other",
    "native:checkgeometrylinelayerintersection": "Lines intersecting other layer",
    "native:checkgeometrymissingvertex": "Missing vertices along borders",
    "native:checkgeometrymultipart": "Strictly multipart",
    "native:checkgeometryoverlap": "Overlaps",
    "native:checkgeometrysegmentlength": "Small segments",
    "native:checkgeometryselfcontact": "Self-contacts",
    "native:checkgeometryselfintersection": "Self-intersections",
    "native:checkgeometrysliverpolygon": "Sliver polygons",
    "native:climbalongline": "Climb along line",
    "native:distancematrix": "Distance matrix",
    "native:distancetonearesthub": "Distance to nearest hub",
    "native:extenttolayer": "Create layer from extent",
    "native:hublines": "Join by lines (hub lines)",
    "native:meancoordinates": "Mean coordinate(s)",
    "native:pointtolayer": "Create layer from point",
    "native:randompointsinpolygons": "Random points in polygons",
    "native:randompointsonlines": "Random points on lines",
    "native:shortestline": "Shortest line between features",
    "qgis:distancetonearesthublinetohub": "Distance to nearest hub (line to hub)",
    "qgis:distancetonearesthubpoints": "Distance to nearest hub (points)",
    "qgis:randompointsalongline": "Random points along line",
    "qgis:randompointsinlayerbounds": "Random points in layer bounds",
    "qgis:texttofloat": "Text to float",
    "qgis:topologicalcoloring": "Topological coloring",
}
ALLOWED_ALGORITHM_IDS = frozenset(set(ALLOWED_ALGORITHM_IDS) | set(ANALYSIS_FAMILY))

# M6d: algorithms that take a QGIS expression and write a new layer. Every string parameter of these goes through the expression screen
# (parameter_violation), so env(), file functions and eval() are refused exactly as in field_calculator and the other expression tools.
# Left off: native:selectbyexpression (changes the user's own selection, needs the in-place handling), native:aggregate (its
# `aggregates` parameter is a list of objects), native:fieldcalculator (the dedicated tool already covers it), the raise* algorithms
# (they only raise messages) and the raster-calculator forms (M7, own grammar).
EXPRESSION_FAMILY = {
    "native:extractbyexpression": "Extract by expression",
    "native:geometrybyexpression": "Geometry by expression",
    "native:orderbyexpression": "Order by expression",
    "native:addautoincrementalfield": "Add autoincremental field",
    "qgis:randompointsinsidepolygons": "Random points inside polygons",
}
EXPRESSION_ALGORITHM_IDS = frozenset(EXPRESSION_FAMILY)
ALLOWED_ALGORITHM_IDS = frozenset(set(ALLOWED_ALGORITHM_IDS) | set(EXPRESSION_FAMILY))
# M7 (completion plan, package D): the raster family. Rule applied to docs/qgis_coverage/processing_matrix.csv: disposition CANDIDATE, wave
# '2D raster', minus seven that must not run through a generic tool (see RASTER_EXCLUDED). The parameters are layers (rasters, vector
# sources, lists of rasters), band numbers, numbers, enums, CRS, extents and destinations; the free-form text parameters (EXTRA, and the
# OPTIONS / CREATION_OPTIONS of the GDAL tools, which are raw command-line text) are refused by parameter_violation. Outputs are
# temporary rasters or memory tables, never a user path. As for the geometry family, an id stays here only while
# tests/test_processing_geometry_family_live.py runs it successfully in real QGIS; a failing one is moved to GEOMETRY_NOT_YET with the
# error and removed from this set.
RASTER_EXCLUDED = {
    "gdal:assignprojection": "rewrites the input file's projection in place",
    "gdal:extractprojection": "writes .prj / .wld files next to the input",
    "gdal:overviews": "adds pyramids to the input file in place",
    "native:alignrasters": "needs a structured list parameter, not a plain value",
    "native:rasterize": "takes a map theme and renders the canvas",
    "native:zonalstatistics": "edits the vector layer in place",
    "qgis:rastercalculator": "free-form formula: use the raster_calculator tool",
}
RASTER_FAMILY = {
    "gdal:aspect": "Aspect",
    "gdal:buildvirtualraster": "Build virtual raster",
    "gdal:cliprasterbyextent": "Clip raster by extent",
    "gdal:fillnodata": "Fill NoData",
    "gdal:gridaverage": "Grid (Moving average)",
    "gdal:griddatametrics": "Grid (Data metrics)",
    "gdal:gridinversedistance": "Grid (Inverse distance to a power)",
    "gdal:gridinversedistancenearestneighbor": "Grid (IDW with nearest neighbor searching)",
    "gdal:gridlinear": "Grid (Linear)",
    "gdal:gridnearestneighbor": "Grid (Nearest neighbor)",
    "gdal:hillshade": "Hillshade",
    "gdal:nearblack": "Near black",
    "gdal:pcttorgb": "PCT to RGB",
    "gdal:proximity": "Proximity (raster distance)",
    "gdal:rearrange_bands": "Rearrange bands",
    "gdal:rgbtopct": "RGB to PCT",
    "gdal:roughness": "Roughness",
    "gdal:sieve": "Sieve",
    "gdal:slope": "Slope",
    "gdal:tpitopographicpositionindex": "Topographic Position Index (TPI)",
    "gdal:translate": "Translate (convert format)",
    "gdal:triterrainruggednessindex": "Terrain Ruggedness Index (TRI)",
    "gdal:viewshed": "Viewshed",
    "gdal:warpreproject": "Warp (reproject)",
    "native:alignsingleraster": "Align raster",
    "native:cellstackpercentile": "Cell stack percentile",
    "native:cellstackpercentrankfromrasterlayer": "Cell stack percentrank from raster layer",
    "native:cellstackpercentrankfromvalue": "Cell stack percent rank from value",
    "native:createconstantrasterlayer": "Create constant raster layer",
    "native:createrandombinomialrasterlayer": "Create random raster layer (binomial distribution)",
    "native:createrandomexponentialrasterlayer": "Create random raster layer (exponential distribution)",
    "native:createrandomgammarasterlayer": "Create random raster layer (gamma distribution)",
    "native:createrandomgeometricrasterlayer": "Create random raster layer (geometric distribution)",
    "native:createrandomnegativebinomialrasterlayer": "Create random raster layer (negative binomial distribution)",
    "native:createrandomnormalrasterlayer": "Create random raster layer (normal distribution)",
    "native:createrandompoissonrasterlayer": "Create random raster layer (poisson distribution)",
    "native:createrandomuniformrasterlayer": "Create random raster layer (uniform distribution)",
    "native:dtmslopebasedfilter": "DTM filter (slope-based)",
    "native:equaltofrequency": "Equal to frequency",
    "native:fillnodata": "Fill NoData cells",
    "native:fillsinkswangliu": "Fill sinks (Wang & Liu)",
    "native:fuzzifyrastergaussianmembership": "Fuzzify raster (gaussian membership)",
    "native:fuzzifyrasterlargemembership": "Fuzzify raster (large membership)",
    "native:fuzzifyrasterlinearmembership": "Fuzzify raster (linear membership)",
    "native:fuzzifyrasternearmembership": "Fuzzify raster (near membership)",
    "native:fuzzifyrasterpowermembership": "Fuzzify raster (power membership)",
    "native:fuzzifyrastersmallmembership": "Fuzzify raster (small membership)",
    "native:greaterthanfrequency": "Greater than frequency",
    "native:highestpositioninrasterstack": "Highest position in raster stack",
    "native:lessthanfrequency": "Less than frequency",
    "native:lowestpositioninrasterstack": "Lowest position in raster stack",
    "native:rasterbooleanand": "Raster boolean AND",
    "native:rasterfeaturepreservingsmoothing": "Feature preserving DEM smoothing",
    "native:rastergaussianblur": "Gaussian blur",
    "native:rasterlayerproperties": "Raster layer properties",
    "native:rasterlayerzonalstats": "Raster layer zonal statistics",
    "native:rasterlogicalor": "Raster boolean OR",
    "native:rasterminmax": "Raster minimum/maximum",
    "native:rasterrank": "Raster rank",
    "native:reclassifybylayer": "Reclassify by layer",
    "native:rescaleraster": "Rescale raster",
    "native:roundrastervalues": "Round raster",
    "native:ruggednessindex": "Ruggedness index",
    "native:totalcurvature": "Total curvature",
    "native:zonalhistogram": "Zonal histogram",
    "native:zonalminmaxpoint": "Zonal minimum/maximum point",
}
RASTER_ALGORITHM_IDS = frozenset(RASTER_FAMILY)
ALLOWED_ALGORITHM_IDS = frozenset(set(ALLOWED_ALGORITHM_IDS) | set(RASTER_FAMILY))
RASTER_FORBIDDEN_PARAM_KEYS = frozenset({"OPTIONS", "CREATION_OPTIONS"})
# M6 leftovers (completion plan, package E): the table, analysis, geometry and rasterize algorithms the first M6 waves did not take. Rule as
# for the other families (matrix CANDIDATE, outputs memory or temporary file, no file/path/connection parameter, nothing that edits the
# user's own layer or project), checked per algorithm by the live probe. Left off ON PURPOSE, with the reason:
#   * the 10 fixgeometry* and 4 checkgeometry* (contained, gap, point-covered, point-in-polygon) algorithms need an ERRORS layer produced by
#     a matching check, i.e. a check-then-fix workflow, not a single call: they want a dedicated tool;
#   * truncatetable, randomselection(+subsets), selectbyattribute, selectwithindistance, eliminateselectedpolygons, createspatialindex,
#     createattributeindex, definecurrentprojection, setlayerencoding, rename/update/copy/set layer metadata, addhistorymetadata,
#     setprojectvariable, loadlayer, renamelayer: change the user's own layer, selection or project;
#   * batchnominatimgeocoder and the importinto*/export to database algorithms: network or database writes;
#   * calculateexpression, stringconcatenation, condition, filter, executesql, refactorfields (mapping object), alignrasters, explodehstorefield,
#     flattenrelationships, extractlabels, transferannotationsfrommain: expression / structured-parameter / map-state algorithms;
#   * concavehull, transect, transectfixeddistance, variabledistancebuffer, rectanglesovalsdiamondsvariable: rejected by the first M6a live runs
#     (GEOMETRY_REJECTED).
MIXED_FAMILY = {
    "native:addfieldtoattributestable": "Add field to attributes table",
    "native:adduniquevalueindexfield": "Add unique value index field",
    "native:addxyfields": "Add X/Y fields to layer",
    "native:assignprojection": "Assign projection",
    "native:bookmarkstolayer": "Convert spatial bookmarks to layer",
    "native:extractbyattribute": "Extract by attribute",
    "native:findprojection": "Find projection",
    "native:renametablefield": "Rename field",
    "native:saveselectedfeatures": "Extract selected features",
    "native:splitfeaturesbycharacter": "Split features by character",
    "native:createpointslayerfromtable": "Create points layer from table",
    "native:angletonearest": "Align points to features",
    "native:calculatevectoroverlaps": "Overlap analysis",
    "native:extractnetworkendpoints": "Extract network end points",
    "native:linedensity": "Line density",
    "native:heatmapkerneldensityestimation": "Heatmap (Kernel Density Estimation)",
    "native:pixelstopoints": "Raster pixels to points",
    "native:pixelstopolygons": "Raster pixels to polygons",
    "native:generatepointspixelcentroidsinsidepolygons": "Generate points (pixel centroids) inside polygons",
    "qgis:generatepointspixelcentroidsalongline": "Generate points (pixel centroids) along line",
    "native:randompointsinextent": "Random points in extent",
    "qgis:regularpoints": "Regular points",
    "native:serviceareafromlayer": "Service area (from layer)",
    "native:shortestpathlayertopoint": "Shortest path (layer to point)",
    "native:stdbscanclustering": "ST-DBSCAN clustering",
    "native:sumlinelengths": "Sum line lengths",
    "native:validatenetwork": "Validate network",
    "native:extractmvalues": "Extract M values",
    "native:extractzvalues": "Extract Z values",
    "native:extractspecificvertices": "Extract specific vertices",
    "native:lineintersections": "Line intersections",
    "native:multidifference": "Difference (multiple)",
    "native:multiintersection": "Intersection (multiple)",
    "native:multiunion": "Union (multiple)",
    "native:setmfromraster": "Set M value from raster",
    "native:setzfromraster": "Drape (set Z value from raster)",
    "native:polygonfromlayerextent": "Extract layer extent",
    "gdal:rasterize": "Rasterize (vector to raster)",
}
MIXED_ALGORITHM_IDS = frozenset(MIXED_FAMILY)
ALLOWED_ALGORITHM_IDS = frozenset(set(ALLOWED_ALGORITHM_IDS) | set(MIXED_FAMILY))
FAMILY_NAMES = {**GEOMETRY_FAMILY, **TABLE_FAMILY, **ANALYSIS_FAMILY, **EXPRESSION_FAMILY, **RASTER_FAMILY, **MIXED_FAMILY}

# Algorithms whose OUTPUT is a RASTER FILE, not a vector sink. "memory:" is not a valid raster destination, and a raster
# result comes back as a file path, not a layer: before 2026-10-01 these ran and the tool reported "no new layer output".
RASTER_OUTPUT_ALGORITHM_IDS = frozenset({
    "native:hillshade", "native:slope", "native:aspect",
    "gdal:cliprasterbymasklayer", "gdal:merge", "gdal:pansharp",
    "qgis:idwinterpolation", "qgis:tininterpolation", "qgis:heatmapkerneldensityestimation",
    "native:reclassifybytable", "native:cellstatistics",
})


# GitHub #163 (audit F27): algorithms that change an EXISTING layer instead of making a new one. The generic tool must not rename such
# a result (it is the user's own layer) or call it "a new layer": it reports what changed instead. qgis:zonalstatistics (which writes
# new fields into its input) is no longer offered here; native:zonalstatisticsfb makes a new layer.
MUTATES_INPUT_ALGORITHM_IDS = frozenset({"native:selectbylocation"})


# GitHub #137 (audit F01): "gdal:rastercalculator" was on this list, and the generic tool passed its FORMULA through untouched.
# gdal_calc evaluates that string with Python's eval(), so a model-controlled formula ran arbitrary Python outside the
# execute_pyqgis_script sandbox. The dedicated tools (weighted overlay, NDVI, change detection) still call it, but with formulas
# this plugin writes itself. The generic tool no longer offers it, and refuses the two parameter names that carry free-form
# code or command-line text for ANY algorithm.
FORBIDDEN_PARAM_KEYS = frozenset({"FORMULA", "EXTRA"})


def expression_violation(alg_id, params):
    """The screen's message when an expression-taking algorithm is given a string that calls a denied function, else None. Pure."""
    if alg_id not in EXPRESSION_ALGORITHM_IDS:
        return None
    from ...validators.expression_screen import screen_expression
    for value in (params or {}).values():
        if isinstance(value, str):
            blocked = screen_expression(value)
            if blocked:
                return blocked
    return None


def parameter_violation(alg_id, params):
    """A reason string when `params` carries something the generic tool must not pass to Processing, else None. Pure.

    Refused: a FORMULA / EXTRA parameter (free-form expression or raw backend arguments), matched case-insensitively, and any
    nested object value (the tool only ever accepts flat, JSON-primitive parameters)."""
    blocked = expression_violation(alg_id, params)
    if blocked:
        return blocked
    for key, value in (params or {}).items():
        if (alg_id in RASTER_ALGORITHM_IDS or alg_id.startswith("gdal:")) and str(key).upper() in RASTER_FORBIDDEN_PARAM_KEYS:
            return (f"parameter '{key}' is not accepted: it carries raw GDAL creation options, which this tool does not pass to '{alg_id}'. "
                    "Leave it out; the output is a temporary raster.")
        if str(key).upper() in FORBIDDEN_PARAM_KEYS:
            return (f"parameter '{key}' is not accepted: it carries a free-form expression or raw backend arguments, which "
                    f"this tool does not pass to '{alg_id}'. Use a dedicated tool, or execute_pyqgis_script (sandboxed).")
        if isinstance(value, dict):
            return f"parameter '{key}' must be a plain value or a list of plain values, not an object."
    return None

