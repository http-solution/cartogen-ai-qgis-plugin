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
