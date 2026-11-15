"""Every allow-listed Processing algorithm can be reached from a plain request: either its dedicated tool or run_allowlisted_processing_algorithm
is offered. Written 2026-10-14 (QGIS vocabulary audit); before it, 'create a grid' offered neither. A new algorithm added to the allow-list
must get a row here, which the first test enforces. Checks what is OFFERED, not what the model then does with it."""
import unittest

from cartogen_ai.core.agent.tools import TOOLS_SCHEMA
from cartogen_ai.core.agent.tools._processing_allowlist import ALLOWED_ALGORITHM_IDS, FAMILY_NAMES
from cartogen_ai.core.services.tool_router import ToolRouter

PROCESSING_TOOL = "run_allowlisted_processing_algorithm"
# algorithm id -> (plain request, dedicated tool that also covers it or None)
ROWS = {
    "gdal:cliprasterbymasklayer": ("clip the raster by mask layer", "raster_clip"),
    "gdal:merge": ("merge the rasters into one", "mosaic_rasters"),
    "gdal:pansharp": ("pansharpen the image", "pan_sharpening"),
    "native:aspect": ("aspect of the dem", "aspect_analysis"),
    "native:buffer": ("buffer the layer", "buffer_analysis"),
    "native:cellstatistics": ("cell statistics across the rasters", None),
    "native:centroids": ("centroids of polygons", "centroid"),
    "native:clip": ("clip the layer", "clip_layer"),
    "native:convexhull": ("convex hull", "convex_hull"),
    "native:countpointsinpolygon": ("count points in polygon", None),
    "native:creategrid": ("create a grid", None),
    "native:dbscanclustering": ("dbscan clustering", "hotspot_analysis"),
    "native:delaunaytriangulation": ("delaunay triangulation", "delaunay_triangulation"),
    "native:difference": ("difference of two layers", "difference_layers"),
    "native:dissolve": ("dissolve by field", "dissolve_layer"),
    "native:extractbylocation": ("extract by location", None),
    "native:fixgeometries": ("fix geometries", "fix_geometries"),
    "native:hillshade": ("hillshade", "hillshade"),
    "native:intersection": ("intersection of two layers", "intersect_layers"),
    "native:joinattributesbylocation": ("join attributes by location", "spatial_join"),
    "native:joinattributestable": ("join attributes table by field value", "join_by_attribute"),
    "native:joinbynearest": ("join by nearest", None),
    "native:kmeansclustering": ("k-means clustering", None),
    "native:mergevectorlayers": ("merge vector layers", "merge_layers"),
    "native:multiparttosingleparts": ("multipart to singleparts", "convert_to_singlepart"),
    "native:rastersampling": ("sample raster values", None),
    "native:reclassifybytable": ("reclassify by table", None),
    "native:reprojectlayer": ("reproject layer", "reproject_layer"),
    "native:selectbylocation": ("select by location", "select_by_location"),
    "native:serviceareafrompoint": ("service area from point", "calculate_service_area"),
    "native:shortestpathpointtolayer": ("shortest path point to layer", None),
    "native:shortestpathpointtopoint": ("shortest path point to point", None),
    "native:simplifygeometries": ("simplify geometries", "simplify_geometry"),
    "native:slope": ("slope", "slope_analysis"),
    "native:symmetricaldifference": ("symmetrical difference", None),
    "native:union": ("union", "union_layers"),
    "native:voronoipolygons": ("voronoi polygons", "voronoi_polygons"),
    "native:zonalstatisticsfb": ("zonal statistics", "zonal_statistics"),
    "qgis:heatmapkerneldensityestimation": ("heatmap kernel density", "apply_heatmap_style"),
    "qgis:idwinterpolation": ("idw interpolation", "interpolate_surface"),
    "qgis:statisticsbycategories": ("statistics by categories", None),
    "qgis:tininterpolation": ("tin interpolation", "interpolate_surface"),
}


# M6a geometry family: the plain request is the algorithm's own display name in lower case, without the bracketed part
# ("Concave hull (by layer)" -> "concave hull"). A one-word name is asked for the way a user would say it.
_ONE_WORD_REQUESTS = {"Boundary": "get the boundary of the polygons", "Polygonize": "polygonize the lines", "Roundness": "calculate the roundness of the polygons",
                      "Extrude": "extrude the lines", "Rotate": "rotate the features by 45 degrees", "Smooth": "smooth the lines",
                      "Subdivide": "subdivide the polygons", "Translate": "translate the features by 100 m",
                      "Holes": "check the geometry for holes", "Overlaps": "check the geometry for overlaps",
                      "Mean coordinate(s)": "calculate the mean coordinate of the points", "Join by lines (hub lines)": "draw join by lines from the points to the hubs",
                      "Create layer from extent": "create layer from extent", "Create layer from point": "create layer from point 10,10",
                      # package D raster family: names that are one word, shared with a dedicated tool, or a bracketed variant
                      "Grid (Moving average)": "grid with moving average", "Grid (Data metrics)": "grid with data metrics",
                      "Grid (Inverse distance to a power)": "grid with inverse distance",
                      "Grid (IDW with nearest neighbor searching)": "grid with inverse distance", "Grid (Linear)": "grid with linear interpolation",
                      "Grid (Nearest neighbor)": "grid with nearest neighbor", "Hillshade": "gdal hillshade", "Slope": "gdal slope", "Aspect": "gdal aspect",
                      "Proximity (raster distance)": "raster proximity", "Translate (convert format)": "convert raster format",
                      "Warp (reproject)": "warp the raster", "Roughness": "roughness of the dem", "Sieve": "sieve the raster",
                      "Fill NoData": "fill nodata", "Fill NoData cells": "fill nodata", "Fill sinks (Wang & Liu)": "fill sinks",
                      # package E: names shared with a dedicated tool or too short to be a phrase of their own
                      "Difference (multiple)": "difference of multiple layers", "Intersection (multiple)": "intersection of multiple layers",
                      "Union (multiple)": "union of multiple layers", "Drape (set Z value from raster)": "drape the lines on the dem",
                      "Heatmap (Kernel Density Estimation)": "kernel density heatmap", "Service area (from layer)": "service area from a layer of facilities",
                      "Rename field": "rename a table field", "Assign projection": "assign projection to the layer",
                      "Extract layer extent": "extract layer extent as a polygon", "Generate points (pixel centroids) inside polygons":
                      "generate points at pixel centroids inside polygons", "Extract by attribute": "extract by attribute value",
                      "Extract selected features": "extract selected features to a new layer", "Add X/Y fields to layer": "add x y fields to layer",
                      "Rasterize (vector to raster)": "rasterize the vector to a raster",
                      # gap-closing package: mesh family names that are generic words
                      "Export contours": "export mesh contours", "Surface to polygon": "surface to polygon from the mesh"}


def _plain_request(name):
    import re
    if name in _ONE_WORD_REQUESTS:
        return _ONE_WORD_REQUESTS[name]
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", re.sub(r"\(.*?\)", "", name).lower()).split())


for _alg_id, _name in FAMILY_NAMES.items():
    # M9 GRASS family: the display name is the GRASS command (r.watershed), which people write with the dots and a "grass" in front
    ROWS[_alg_id] = (f"grass {_name}" if _alg_id.startswith("grass:") else _plain_request(_name), None)


class TestAllowlistedAlgorithmsAreReachable(unittest.TestCase):
    def test_every_allowlisted_algorithm_has_a_row(self):
        self.assertEqual(set(ALLOWED_ALGORITHM_IDS) - set(ROWS), set(), "add a plain request for the new algorithm")

    def test_each_one_is_reachable_from_its_plain_request(self):
        router = ToolRouter(TOOLS_SCHEMA)
        missing = []
        for algorithm, (request, dedicated) in ROWS.items():
            offered = {t["function"]["name"] for t in router.filter_relevant_tools(request)}
            if PROCESSING_TOOL not in offered and not (dedicated and dedicated in offered):
                missing.append(f"{algorithm}: {request!r}")
        self.assertEqual(missing, [], chr(10).join(missing))


if __name__ == "__main__":
    unittest.main()
