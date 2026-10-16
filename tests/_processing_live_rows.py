"""Minimal live run parameters for the allow-listed Processing algorithms (pure data, no QGIS import).

Why: the allow-list is 42 algorithm ids but only a handful were ever run in real QGIS, so a wrong parameter name or a destination
the wrapper mishandles would only show up in a user's session. Each id is either in LIVE_ROWS (run by
tests/test_processing_allowlist_all_live.py) or in NOT_YET with the reason, and tests/test_processing_live_rows.py (offline) fails
for an id in neither, so a new allow-list entry cannot skip this. The rows were written without a QGIS install: CI's first run is
their first execution, and a failing row means a wrong row until shown otherwise. Layer names: pts (4 points), polys (2 squares),
polys2 (1 square overlapping both), hub (1 point)."""

SQUARE = "POLYGON((0 0,1 0,1 1,0 1,0 0))"

LIVE_ROWS = {
    "native:buffer": {"INPUT": "pts", "DISTANCE": 0.01},
    "native:centroids": {"INPUT": "polys"},
    "native:convexhull": {"INPUT": "polys"},
    "native:fixgeometries": {"INPUT": "polys"},
    "native:simplifygeometries": {"INPUT": "polys", "TOLERANCE": 0.001},
    "native:dissolve": {"INPUT": "polys"},
    "native:multiparttosingleparts": {"INPUT": "polys"},
    "native:clip": {"INPUT": "polys", "OVERLAY": "polys2"},
    "native:difference": {"INPUT": "polys", "OVERLAY": "polys2"},
    "native:intersection": {"INPUT": "polys", "OVERLAY": "polys2"},
    "native:union": {"INPUT": "polys", "OVERLAY": "polys2"},
    "native:symmetricaldifference": {"INPUT": "polys", "OVERLAY": "polys2"},
    "native:reprojectlayer": {"INPUT": "polys", "TARGET_CRS": "EPSG:3857"},
    "native:delaunaytriangulation": {"INPUT": "pts"},
    "native:voronoipolygons": {"INPUT": "pts"},
    "native:countpointsinpolygon": {"POLYGONS": "polys", "POINTS": "pts"},
    "native:kmeansclustering": {"INPUT": "pts", "CLUSTERS": 2},
    "native:dbscanclustering": {"INPUT": "pts", "MIN_SIZE": 2, "EPS": 5.0},
    "native:joinbynearest": {"INPUT": "hub", "INPUT_2": "pts", "NEIGHBORS": 1},
}

NOT_YET = {
    "gdal:cliprasterbymasklayer": "needs a raster fixture",
    "gdal:merge": "needs two raster fixtures and a file destination",
    "gdal:pansharp": "needs a multi-band raster fixture",
    "native:aspect": "needs a raster fixture",
    "native:slope": "needs a raster fixture",
    "native:hillshade": "needs a raster fixture",
    "native:cellstatistics": "needs raster fixtures",
    "native:reclassifybytable": "needs a raster fixture and a table parameter",
    "native:rastersampling": "needs a raster fixture",
    "native:zonalstatisticsfb": "needs a raster fixture",
    "qgis:heatmapkerneldensityestimation": "needs a raster destination; run once the raster fixture helper exists",
    "qgis:idwinterpolation": "interpolation data is a packed string parameter",
    "qgis:tininterpolation": "interpolation data is a packed string parameter",
    "native:creategrid": "EXTENT parameter format to be confirmed against the live registry",
    "native:extractbylocation": "PREDICATE is a list parameter; resolver behaviour to be confirmed",
    "native:selectbylocation": "mutates its input and takes a list parameter",
    "native:joinattributesbylocation": "PREDICATE is a list parameter",
    "native:joinattributestable": "needs a table fixture",
    "native:mergevectorlayers": "LAYERS is a list parameter",
    "native:serviceareafrompoint": "needs a road network fixture",
    "native:shortestpathpointtolayer": "needs a road network fixture",
    "native:shortestpathpointtopoint": "needs a road network fixture",
    "qgis:statisticsbycategories": "table output; fixture to be added",
}


# Geometry-family algorithms (M6a) that did not run in a real QGIS session, with the error CI reported. Empty means every one ran.
GEOMETRY_NOT_YET = {}

# Geometry-family candidates that must NOT be on the allow-list, with what the first live run (QGIS 4.2.2, 2026-10-14) showed. The
# offline test fails if one of these ids is ever allow-listed without this entry being removed on purpose, with a passing live run.
GEOMETRY_REJECTED = {
    "native:concavehull": "hung: no result after 60 s on a 2-polygon layer with default parameters",
    "native:transect": "crashed the QGIS process (SIGSEGV, exit code -11) on polygon, line and point input",
    "qgis:variabledistancebuffer": "Python algorithm raised a traceback on polygon, line and point input with a numeric field (QGIS 4.2.2, two live runs); cause not investigated",
    "qgis:rectanglesovalsdiamondsvariable": "Python algorithm raised a traceback on polygon, line and point input with a numeric field (QGIS 4.2.2, two live runs); cause not investigated",
    "native:transectfixeddistance": "crashed the QGIS process (SIGSEGV, exit code -11) on polygon, line and point input",
    # package E, first live run (QGIS 4.2.2, 2026-10-16)
    "native:findprojection": "hung: no result after 60 s on a 2-polygon layer with default parameters (it searches the CRS database)",
    "native:linedensity": "raster output could not be created with the probe's parameters on any of four test layers (GDAL provider error); cause not investigated",
    "native:shortestpathlayertopoint": "needs a purpose-built road network: the end point was 1.41 from the nearest edge on every test layer (limit 1)",
}

# GRASS-family candidates (M9) that did not run in a real QGIS session, with the error CI reported. They are NOT on the allow-list; the
# offline test fails if one is listed in both places. Empty means every candidate ran.
MESH_REJECTED = {
    "native:meshcontours": "hung: no result after 90 s on a 9-node, 8-triangle test mesh with default parameters (first live run, QGIS 4.2.2, 2026-10-16)",
}

GRASS_REJECTED = {
    "grass:i.evapo.mh": "first live run (CI, QGIS 4.2.2, 2026-10-16): 'Unable to execute algorithm' with the probe's default inputs (GRASS gave no detail); likely needs purpose-built inputs; cause not investigated",
    "grass:i.landsat.acca": "first live run (CI, QGIS 4.2.2, 2026-10-16): 'Unable to execute algorithm' with the probe's default inputs (GRASS gave no detail); likely needs purpose-built inputs; cause not investigated",
    "grass:r.drain": "first live run (CI, QGIS 4.2.2, 2026-10-16): 'Unable to execute algorithm' with the probe's default inputs (GRASS gave no detail); likely needs purpose-built inputs; cause not investigated",
    "grass:r.null": "first live run (CI, QGIS 4.2.2, 2026-10-16): 'Unable to execute algorithm' with the probe's default inputs (GRASS gave no detail); likely needs purpose-built inputs; cause not investigated",
    "grass:r.resamp.filter": "first live run (CI, QGIS 4.2.2, 2026-10-16): 'Unable to execute algorithm' with the probe's default inputs (GRASS gave no detail); likely needs purpose-built inputs; cause not investigated",
    "grass:r.rescale": "first live run (CI, QGIS 4.2.2, 2026-10-16): 'Unable to execute algorithm' with the probe's default inputs (GRASS gave no detail); likely needs purpose-built inputs; cause not investigated",
    "grass:r.rescale.eq": "first live run (CI, QGIS 4.2.2, 2026-10-16): 'Unable to execute algorithm' with the probe's default inputs (GRASS gave no detail); likely needs purpose-built inputs; cause not investigated",
    "grass:v.drape": "first live run (CI, QGIS 4.2.2, 2026-10-16): 'Unable to execute algorithm' with the probe's default inputs (GRASS gave no detail); likely needs purpose-built inputs; cause not investigated",
    "grass:v.extrude": "first live run (CI, QGIS 4.2.2, 2026-10-16): 'Unable to execute algorithm' with the probe's default inputs (GRASS gave no detail); likely needs purpose-built inputs; cause not investigated",
    "grass:v.net.connectivity": "first live run (CI, QGIS 4.2.2, 2026-10-16): 'Unable to execute algorithm' with the probe's default inputs (GRASS gave no detail); likely needs purpose-built inputs; cause not investigated",
    "grass:v.net.flow": "first live run (CI, QGIS 4.2.2, 2026-10-16): 'Unable to execute algorithm' with the probe's default inputs (GRASS gave no detail); likely needs purpose-built inputs; cause not investigated",
    "grass:v.to.3d": "first live run (CI, QGIS 4.2.2, 2026-10-16): 'Unable to execute algorithm' with the probe's default inputs (GRASS gave no detail); likely needs purpose-built inputs; cause not investigated",
}
