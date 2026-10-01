# -*- coding: utf-8 -*-
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
    "gdal:rastercalculator",
    "gdal:cliprasterbymasklayer",
    "gdal:contraststretch",
    "gdal:merge",
    "gdal:pansharpening",
    "saga:kmeansclassificationforgrid",
    "saga:supervisedclassificationforgrids",
    "qgis:zonalstatistics",
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
    "native:statisticsbycategories",  # count/sum/mean per category
    "native:dbscanclustering",        # density clusters of points (incidents, facilities)
    "native:kmeansclustering",        # k clusters of points (service-region sketches)
    "native:rastersampling",          # sample a raster (e.g. population) at points
    "native:zonalstatisticsfb",       # zonal statistics, feature-based (qgis:zonalstatistics is the older form)
    "native:reclassifybytable",       # reclassify a raster by a value table (suitability classes)
    "native:cellstatistics",          # per-cell statistics across several rasters
})
ALLOWED_ALGORITHM_IDS = frozenset(set(ALLOWED_ALGORITHM_IDS) | set(ANALYSIS_EXTENSIONS))

# Algorithms whose OUTPUT is a RASTER FILE, not a vector sink. "memory:" is not a valid raster destination, and a raster
# result comes back as a file path, not a layer: before 2026-10-01 these ran and the tool reported "no new layer output".
RASTER_OUTPUT_ALGORITHM_IDS = frozenset({
    "native:hillshade", "native:slope", "native:aspect",
    "gdal:rastercalculator", "gdal:cliprasterbymasklayer", "gdal:contraststretch", "gdal:merge", "gdal:pansharpening",
    "saga:kmeansclassificationforgrid", "saga:supervisedclassificationforgrids",
    "qgis:idwinterpolation", "qgis:tininterpolation", "qgis:heatmapkerneldensityestimation",
    "native:reclassifybytable", "native:cellstatistics",
})

