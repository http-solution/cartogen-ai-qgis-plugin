"""Pure (Qt-free) source-string logic for the M8 layer-type tools in new_layer_tools.py, unit-tested offline.

Which layer types this QGIS can open was measured, not assumed: docs/QGIS_CAPABILITY_PROBE_2026-10-16.md (CI image, QGIS 4.2.2)."""
import os

from .data_source_tools import validate_service_url

POINT_CLOUD_EXTENSIONS = (".las", ".laz", ".copc.laz")
VECTOR_TILE_FILE_TYPES = {".mbtiles": "mbtiles", ".vtpk": "vtpk"}
TILED_SCENE_FILES = (".json",)
MAX_ZOOM = 24


def point_cloud_provider(path):
    """('pdal' | 'copc' | 'ept', error). Chosen from the file name only: .copc.laz is COPC, ept.json is an EPT dataset, .las/.laz is read
    by the PDAL-based provider."""
    name = os.path.basename(str(path or "")).lower()
    if name.endswith(".copc.laz"):
        return "copc", None
    if name == "ept.json":
        return "ept", None
    if name.endswith((".las", ".laz")):
        return "pdal", None
    return None, "A point cloud file must be .las, .laz, .copc.laz or an EPT dataset's ept.json."


def zoom_violation(zmin, zmax):
    """None when the zoom range is usable."""
    try:
        zmin, zmax = int(zmin), int(zmax)
    except (TypeError, ValueError):
        return "min_zoom and max_zoom must be whole numbers."
    if not 0 <= zmin <= zmax <= MAX_ZOOM:
        return f"Zoom levels must satisfy 0 <= min_zoom <= max_zoom <= {MAX_ZOOM}."
    return None


def vector_tile_uri(source, zmin=0, zmax=14):
    """(uri, error) for QgsVectorTileLayer. An https URL with {z}/{x}/{y} is an XYZ service; a local .mbtiles/.vtpk file is read in place."""
    from urllib.parse import quote
    problem = zoom_violation(zmin, zmax)
    if problem:
        return None, problem
    text = str(source or "").strip()
    if "://" in text:
        problem = validate_service_url(text)
        if problem:
            return None, problem
        if not all(token in text for token in ("{z}", "{x}", "{y}")):
            return None, "A vector tile URL must contain {z}, {x} and {y}."
        return f"type=xyz&url={quote(text, safe=':/{}')}&zmax={int(zmax)}&zmin={int(zmin)}", None
    kind = VECTOR_TILE_FILE_TYPES.get(os.path.splitext(text)[1].lower())
    if not kind:
        return None, "Give an https tile URL with {z}/{x}/{y}, or a local .mbtiles or .vtpk file."
    return f"type={kind}&url={text}", None


def tiled_scene_source(source):
    """(uri, error). A 3D Tiles tileset is a tileset.json, local or https."""
    text = str(source or "").strip()
    if "://" in text:
        problem = validate_service_url(text)
        if problem:
            return None, problem
        if not text.split("?")[0].lower().endswith(".json"):
            return None, "A 3D Tiles source is the URL of a tileset .json file."
        return text, None
    if not text.lower().endswith(TILED_SCENE_FILES):
        return None, "A 3D Tiles source is a tileset .json file."
    return text, None
