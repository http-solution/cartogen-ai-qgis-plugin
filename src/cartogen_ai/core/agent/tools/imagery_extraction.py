# -*- coding: utf-8 -*-
"""
Imagery feature extraction via SAM-family segmentation (FastSAM), for
Cartogen AI. See docs/archive/SAM_IMAGERY_EXTRACTION_SPEC.md for the full design
rationale -- this module implements that spec's recommended defaults
(FastSAM only, hard reject over max_pixel_dimension, library's own default
checkpoint cache).

Deliberately isolated in its own module, not folded into raster_tools.py or
multimodal_remote_sensing.py: this is the only tool in the codebase needing
a real ML runtime (torch, via the `ultralytics` package) and a downloaded
model checkpoint rather than an API-key-only provider integration.
`ultralytics` is imported lazily, inside the tool function -- the same
guard pattern generate_chart already uses for matplotlib -- so a missing
optional dependency here can't break plugin startup or any other tool.

Class-agnostic by design: FastSAM finds object BOUNDARIES, not identities
-- it never returns "building" or "tree", only a polygon and a confidence
score. Labeling a result with a specific class the model didn't actually
determine would be a fabrication, exactly what agent/prompts.py rule 12
exists to prevent -- applied here to this codebase's own tool output, not
just the LLM's text.
"""

import os
import re
import tempfile
from .registry import register_tool

try:
    from qgis.core import QgsProject, QgsRasterLayer, QgsVectorLayer, QgsFeature, QgsField, QgsGeometry
    from qgis.PyQt.QtCore import QVariant
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False

_DEFAULT_MAX_PIXEL_DIMENSION = 2048


def _find_layer_by_name(name):
    if not QGIS_AVAILABLE:
        return None
    layers = QgsProject.instance().mapLayersByName(name)
    if not layers:
        return None
    return layers[0]


_URL = re.compile(r"https?://\S+")
_DOWNLOAD_HINTS = ("download", "http error", "416", "range not satisfiable", "urlopen", "connection", "timed out", "ssl")


def describe_model_failure(exc):
    """The error text for a failed FastSAM load or inference, with no URLs in it.

    rc15 hand test D06 (2026-10-06): the first run downloaded the FastSAM-s checkpoint, got HTTP 416 (Range Not Satisfiable,
    which is what a download resuming from a PARTIAL file earns), QGIS showed Not Responding for about a minute, and the chat
    printed the whole signed download URL. The exception text is kept for the log-free summary but every URL is removed from
    it, and a download failure says what to do. The download still happens on QGIS's main thread; that is not fixed here. Pure."""
    text = _URL.sub("<url removed>", str(exc) or type(exc).__name__)
    if any(h in text.lower() for h in _DOWNLOAD_HINTS):
        return ("The FastSAM model checkpoint (FastSAM-s.pt) could not be downloaded, so nothing was detected: "
                f"{text[:200]}. QGIS can stop responding while this download runs. An HTTP 416 usually means an earlier "
                "download left a partial FastSAM-s.pt behind: delete that file from the ultralytics weights folder (or from "
                "QGIS's working folder) and try again on a stable connection, or place a complete copy there yourself.")
    return f"FastSAM inference failed: {text[:300]}"


def _temp_path(suffix):
    fd, path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    return path


def _pixel_to_map(px, py, geotransform):
    """Converts a pixel (column, row) coordinate to a real-world map
    coordinate using a GDAL 6-element geotransform (origin_x, pixel_w,
    rot_x, origin_y, rot_y, pixel_h). Pure arithmetic, no GDAL/QGIS objects
    needed -- kept as its own function so it's testable without a real
    raster (see docs/archive/SAM_IMAGERY_EXTRACTION_SPEC.md section 9's "can verify"
    list)."""
    origin_x, pixel_w, rot_x, origin_y, rot_y, pixel_h = geotransform
    map_x = origin_x + px * pixel_w + py * rot_x
    map_y = origin_y + px * rot_y + py * pixel_h
    return map_x, map_y


def _mask_pixel_count(mask, threshold=0.5):
    """Counts pixels above threshold in a 2D mask array -- works with numpy
    arrays (via a boolean-sum) or plain nested lists/tuples (pure Python
    fallback), so it's testable without requiring numpy in the test
    environment. Used to cheaply skip degenerate all-empty masks before the
    expensive polygonize step, not for the real-world area filter (that
    uses the polygon's actual geometry area in map units instead, which
    accounts for pixel size correctly -- pixel count alone does not)."""
    try:
        return int((mask > threshold).sum())
    except (AttributeError, TypeError):
        return sum(1 for row in mask for v in row if v > threshold)


def _finalize_extracted_geometry(qgs_geom, pixel_size, min_area_m2, area_m2=None):
    """Simplifies a raw gdal.Polygonize-traced geometry (smooths the jagged pixel-grid
    "staircase" boundary by roughly one pixel width, Douglas-Peucker via
    QgsGeometry.simplify()), repairs it if simplification introduced a self-intersection
    (QgsGeometry.makeValid()), and applies the min_area_m2 filter -- extracted from
    extract_features_from_imagery's per-feature loop so this decision logic is directly
    unit-testable with a mocked QgsGeometry, without needing the GDAL/OGR/FastSAM
    pipeline around it (out of scope for this suite -- see this file's own test module
    docstring). Returns the finalized geometry, or None if it should be dropped
    (empty/invalid after repair, or below min_area_m2)."""
    if pixel_size > 0:
        qgs_geom = qgs_geom.simplify(pixel_size)
    if not qgs_geom.isGeosValid():
        qgs_geom = qgs_geom.makeValid()
    if qgs_geom is None or qgs_geom.isEmpty():
        return None
    # Audit F18 (#154): geometry.area() is planar, in the layer's CRS units (degrees squared for EPSG:4326, feet squared for
    # a US-foot CRS), so a "square metres" threshold was compared with the wrong unit. `area_m2` is a callable that measures
    # in square metres on the ellipsoid; without one (unit tests) the planar area is used.
    if min_area_m2 is not None:
        area = area_m2(qgs_geom) if area_m2 is not None else qgs_geom.area()
        if area < min_area_m2:
            return None
    return qgs_geom


@register_tool(
    "extract_features_from_imagery",
    "Extract object boundary polygons from a loaded raster using a class-agnostic segmentation "
    "model (FastSAM) -- for a specific image the user actually has (a fresh drone/satellite photo, "
    "a scanned map), NOT for pre-vetted baseline data (use fetch_building_footprints for that "
    "instead, which is faster and free but can lag real conditions by months). Runs entirely "
    "locally/offline once the model is downloaded -- no cloud vision API call, matching this "
    "plugin's offline-first posture. IMPORTANT: this tool is class-agnostic -- it finds object "
    "BOUNDARIES, never object IDENTITIES. Never describe a result polygon as a specific class "
    "('this is a building') unless the user's own request already established that framing for "
    "the whole image; state plainly that these are detected boundaries with a confidence score, "
    "not classified objects. Requires the raster's pixel dimensions to be at most "
    "max_pixel_dimension -- clip to a smaller area of interest first for a large image rather than "
    "expecting this tool to silently downsample it for you. Requires the optional `ultralytics` "
    "package (installs a real ML runtime plus a ~150MB+ model checkpoint on first use) -- install "
    "via qpip if prompted, or manually in the OSGeo4W Shell.",
    {
        "type": "object",
        "properties": {
            "raster_layer": {"type": "string", "description": "An already-loaded raster layer to extract features from."},
            "output_layer_name": {"type": "string", "description": "Name for the resulting polygon layer. Defaults to '{raster_layer}_extracted_features'."},
            "min_area_m2": {"type": "number", "description": "Optional: drop detected features smaller than this real-world area (square meters) -- SAM-family 'segment everything' mode reliably produces noise-scale false positives worth filtering out."},
            "confidence_threshold": {"type": "number", "description": "Minimum model confidence (0-1) to keep a detected feature. Defaults to 0.4."},
            "max_pixel_dimension": {"type": "integer", "description": "Hard cap on the raster's width/height in pixels. Defaults to 2048 -- larger rasters are rejected with an error asking you to clip first, rather than silently downsampled."},
        },
        "required": ["raster_layer"],
    },
)
def extract_features_from_imagery(raster_layer, output_layer_name=None, min_area_m2=None,
                                   confidence_threshold=0.4, max_pixel_dimension=_DEFAULT_MAX_PIXEL_DIMENSION):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}

    layer = _find_layer_by_name(raster_layer)
    if layer is None:
        return {"error": f"Layer '{raster_layer}' not found"}
    if not isinstance(layer, QgsRasterLayer):
        return {"error": f"'{raster_layer}' is not a raster layer."}

    if not (0 <= confidence_threshold <= 1):
        return {"error": "confidence_threshold must be between 0 and 1."}

    width, height = layer.width(), layer.height()
    if width > max_pixel_dimension or height > max_pixel_dimension:
        return {
            "error": f"Raster is {width}x{height}px, exceeding the {max_pixel_dimension}px cap. "
                     "Clip to a smaller area of interest first rather than processing the full extent."
        }

    try:
        from ultralytics import FastSAM
    except ImportError:
        return {
            "error": "The 'ultralytics' package is required for imagery feature extraction "
                     "(installs a real ML runtime plus a model checkpoint on first use). Install it "
                     "with QGIS fully closed, not while it's running: this dependency group shares "
                     "jinja2/markupsafe with folium (already installed for generate_html_dashboard), "
                     "and Windows can't replace a .pyd file QGIS already has loaded -- installing while "
                     "QGIS is open can fail with 'PermissionError: [WinError 5] Access is denied' on a "
                     "locked file (confirmed in real use, see docs/archive/SAM_IMAGERY_EXTRACTION_SPEC.md). Close "
                     "QGIS completely, then install via qpip on next launch or in the OSGeo4W Shell: "
                     "python -m pip install ultralytics -- then reopen QGIS."
        }

    try:
        from osgeo import gdal, ogr, osr
    except ImportError:
        return {"error": "GDAL Python bindings (osgeo) not available in this environment."}

    source_path = layer.source()
    ds = gdal.Open(source_path)
    if ds is None:
        return {
            "error": f"GDAL could not open '{raster_layer}''s source directly ({source_path}) -- "
                     "this tool needs a real file-backed raster, not a virtual/streamed layer."
        }

    geotransform = ds.GetGeoTransform()
    projection = ds.GetProjection()

    # FastSAM expects a standard 8-bit visual image, not necessarily what
    # the source raster's band count/bit depth already is (satellite/drone
    # imagery is often >8-bit or has more than 3 bands) -- gdal.Translate
    # handles the type/band-count conversion in one step, reusing GDAL's
    # own conversion rather than hand-rolling one.
    png_path = _temp_path(".png")
    try:
        band_count = ds.RasterCount
        band_list = [1, 2, 3] if band_count >= 3 else [1, 1, 1]
        gdal.Translate(png_path, ds, format="PNG", outputType=gdal.GDT_Byte, bandList=band_list, scaleParams=[[]])
    except Exception as e:
        return {"error": f"Failed to prepare imagery for the model: {e}"}
    if not os.path.exists(png_path):
        return {"error": "Failed to export the raster to an image the model can read."}

    try:
        model = FastSAM("FastSAM-s.pt")
        results = model(png_path, device="cpu", retina_masks=True, conf=confidence_threshold, verbose=False)
    except Exception as e:
        return {"error": describe_model_failure(e)}
    finally:
        try:
            os.remove(png_path)
        except OSError:
            pass

    if not results or results[0].masks is None:
        return {"success": True, "feature_count": 0, "message": "No features detected."}

    masks = results[0].masks.data.cpu().numpy()
    boxes = results[0].boxes
    confidences = boxes.conf.cpu().numpy() if boxes is not None else [1.0] * len(masks)

    out_name = output_layer_name or f"{raster_layer}_extracted_features"
    crs = layer.crs().authid()
    from qgis.core import QgsDistanceArea
    distance_area = QgsDistanceArea()
    distance_area.setSourceCrs(layer.crs(), QgsProject.instance().transformContext())
    project_ellipsoid = QgsProject.instance().ellipsoid()
    distance_area.setEllipsoid(project_ellipsoid if project_ellipsoid and project_ellipsoid != "NONE" else "WGS84")
    out_layer = QgsVectorLayer(f"Polygon?crs={crs}", out_name, "memory")
    provider = out_layer.dataProvider()
    provider.addAttributes([QgsField("confidence", QVariant.Double)])
    out_layer.updateFields()

    mem_driver = gdal.GetDriverByName("MEM")
    srs = osr.SpatialReference()
    srs.ImportFromWkt(projection)

    new_features = []
    for mask, conf in zip(masks, confidences):
        conf = float(conf)
        if conf < confidence_threshold or _mask_pixel_count(mask) == 0:
            continue

        mask_h, mask_w = mask.shape
        # FastSAM's mask resolution may differ from the source raster's own
        # pixel grid (retina_masks=True keeps it close, but not guaranteed
        # identical) -- scale the mask's own geotransform to match rather
        # than assuming a 1:1 pixel correspondence with the source.
        scale_x = width / mask_w
        scale_y = height / mask_h
        mask_geotransform = (
            geotransform[0], geotransform[1] * scale_x, geotransform[2],
            geotransform[3], geotransform[4], geotransform[5] * scale_y,
        )

        mem_ds = mem_driver.Create("", mask_w, mask_h, 1, gdal.GDT_Byte)
        mem_ds.SetGeoTransform(mask_geotransform)
        mem_ds.SetProjection(projection)
        band = mem_ds.GetRasterBand(1)
        band.WriteArray((mask > 0.5).astype("uint8"))
        band.SetNoDataValue(0)

        ogr_ds = ogr.GetDriverByName("Memory").CreateDataSource("")
        ogr_layer = ogr_ds.CreateLayer("mask", srs=srs)
        # maskBand=None (not srcBand) so GDAL uses the band's own nodata
        # value (0, set above) to skip background pixels automatically --
        # only the detected (1-valued) region gets polygonized.
        gdal.Polygonize(band, None, ogr_layer, -1)

        # gdal.Polygonize traces the raw pixel grid, so every boundary is a jagged
        # "staircase" of right angles at the mask's own pixel resolution -- not a real
        # cartographic edge. Simplifying by roughly one pixel width (Douglas-Peucker via
        # QgsGeometry.simplify(), same algorithm/API the OCHA/cartography-guide fixes
        # elsewhere in this project use) smooths that staircase without losing real shape
        # detail beyond what the source imagery's own resolution could show anyway.
        pixel_size = abs(mask_geotransform[1])

        for ogr_feat in ogr_layer:
            geom = ogr_feat.GetGeometryRef()
            if geom is None or geom.IsEmpty():
                continue
            qgs_geom = QgsGeometry.fromWkt(geom.ExportToWkt())
            qgs_geom = _finalize_extracted_geometry(qgs_geom, pixel_size, min_area_m2, distance_area.measureArea)
            if qgs_geom is None:
                continue
            new_feat = QgsFeature(out_layer.fields())
            new_feat.setGeometry(qgs_geom)
            new_feat.setAttributes([conf])
            new_features.append(new_feat)

    provider.addFeatures(new_features)
    out_layer.updateExtents()
    QgsProject.instance().addMapLayer(out_layer)
    from .humanitarian_style import style_detected_features
    style_detected_features(out_layer)      # HX1b: confidence bands (best effort)

    return {
        "success": True,
        "layer_name": out_name,
        "feature_count": len(new_features),
        "raw_mask_count": len(masks),
        "confidence_threshold": confidence_threshold,
        "note": (
            "Boundaries only, not classified -- state plainly that these are detected object "
            "boundaries with a confidence score, not identified object types, unless the user's "
            "own request already framed what they're looking for."
        ),
    }
