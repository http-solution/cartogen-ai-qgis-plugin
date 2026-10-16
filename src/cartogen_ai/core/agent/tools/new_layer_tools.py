"""M8 (roadmap completion plan, package H): layer types the chat could not open before.

add_point_cloud_layer   a local .las / .laz / .copc.laz / EPT dataset as a point cloud layer
add_vector_tile_layer   an https XYZ vector tile service, or a local .mbtiles / .vtpk file
add_3d_tiles_layer      a 3D Tiles tileset.json (local or https) as a tiled scene layer

Only what the CI image's QGIS 4.2.2 reported as available is offered (docs/QGIS_CAPABILITY_PROBE_2026-10-16.md). Honest limit: CI has no
network and no point cloud or tile sample data, so tests/test_new_layer_tools_live.py checks the refusal paths and that QGIS accepts
the source strings; opening real data is unverified until someone tries it."""
import contextlib
import os

from .new_layer_options import point_cloud_provider, tiled_scene_source, vector_tile_uri
from .registry import register_tool

try:
    from qgis.core import QgsPointCloudLayer, QgsProject, QgsProviderRegistry, QgsTiledSceneLayer, QgsVectorTileLayer
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False


def _added(layer, kind, note):
    QgsProject.instance().addMapLayer(layer)
    return {"success": True, "layer_name": layer.name(), "layer_type": kind, "crs": layer.crs().authid(), "note": note}


@register_tool(
    "add_point_cloud_layer",
    "Add a point cloud (.las, .laz, .copc.laz, or an EPT dataset's ept.json) from a local file as a layer. Read-only: the file is not changed.",
    {"type": "object", "properties": {"file_path": {"type": "string"}, "layer_name": {"type": "string"}}, "required": ["file_path"]})
def add_point_cloud_layer(file_path, layer_name=None):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    provider, problem = point_cloud_provider(file_path)
    if problem:
        return {"error": problem}
    if not os.path.isfile(file_path):
        return {"error": f"File not found: {file_path}"}
    # The CI image's QGIS lists copc, ept and vpc but no 'pdal' provider (probe 2026-10-16), so plain .las/.laz cannot open there; say
    # so instead of the generic "could not open" that would send the user hunting for a file problem.
    if provider not in QgsProviderRegistry.instance().providerList():
        return {"error": (f"This QGIS has no '{provider}' point cloud provider, so it cannot open {os.path.basename(file_path)}. "
                          "A COPC (.copc.laz) or EPT version of the data opens without it.")}
    name = layer_name or os.path.basename(file_path).split(".")[0] or "point cloud"
    layer = QgsPointCloudLayer(file_path, name, provider)
    if not layer.isValid():
        return {"error": f"QGIS could not open {os.path.basename(file_path)} as a point cloud."}
    out = _added(layer, "point_cloud", "Shown in the 2D map; the 3D view is not part of this tool.")
    with contextlib.suppress(Exception):
        out["point_count"] = int(layer.pointCount())   # best-effort extra; some providers report -1 or raise before indexing
    return out


@register_tool(
    "add_vector_tile_layer",
    "Add a vector tile layer: an https XYZ service URL containing {z}/{x}/{y}, or a local .mbtiles / .vtpk file. Only https URLs are accepted.",
    {"type": "object", "properties": {"source": {"type": "string"}, "layer_name": {"type": "string"}, "min_zoom": {"type": "integer"},
                                      "max_zoom": {"type": "integer"}}, "required": ["source"]})
def add_vector_tile_layer(source, layer_name=None, min_zoom=0, max_zoom=14):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    uri, problem = vector_tile_uri(source, min_zoom, max_zoom)
    if problem:
        return {"error": problem}
    if "://" not in str(source) and not os.path.isfile(source):
        return {"error": f"File not found: {source}"}
    layer = QgsVectorTileLayer(uri, layer_name or "vector tiles")
    if not layer.isValid():
        return {"error": "QGIS could not open this vector tile source. Check the URL or file."}
    return _added(layer, "vector_tile", "QGIS fetches tiles itself when the map draws; a remote service sees this computer's address.")


@register_tool(
    "add_3d_tiles_layer",
    "Add a 3D Tiles tileset (a tileset.json, local or https) as a tiled scene layer. Only https URLs are accepted.",
    {"type": "object", "properties": {"source": {"type": "string"}, "layer_name": {"type": "string"}}, "required": ["source"]})
def add_3d_tiles_layer(source, layer_name=None):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    uri, problem = tiled_scene_source(source)
    if problem:
        return {"error": problem}
    if "://" not in uri and not os.path.isfile(uri):
        return {"error": f"File not found: {uri}"}
    layer = QgsTiledSceneLayer(uri, layer_name or "3D tiles", "cesiumtiles")
    if not layer.isValid():
        return {"error": "QGIS could not open this 3D Tiles source. Check the URL or file."}
    return _added(layer, "tiled_scene", "QGIS fetches tiles itself when the map draws; a remote service sees this computer's address.")
