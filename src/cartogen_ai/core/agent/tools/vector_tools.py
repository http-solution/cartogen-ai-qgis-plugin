# -*- coding: utf-8 -*-
"""
Vector Geoprocessing & Spatial Tool implementations for Cartogen AI.
"""

import difflib
import math
import os
import random
from .registry import register_tool

try:
    from qgis.core import (
        QgsProject, QgsExpression, QgsRasterLayer, QgsVectorLayer,
        QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsFeature, QgsFeatureRequest, QgsGeometry,
        QgsPalLayerSettings, QgsTextFormat, QgsTextBufferSettings, QgsVectorLayerSimpleLabeling, QgsWkbTypes,
        QgsField, QgsPointXY, QgsSpatialIndex, QgsUnitTypes, QgsLabelObstacleSettings,
        QgsProcessingFeatureSourceDefinition
    )
    from qgis.PyQt.QtCore import QVariant, Qt
    from qgis.PyQt.QtGui import QColor, QFont
    import processing
    from qgis.utils import iface
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False
    iface = None
    QFont = None

from ._qgis_enum_compat import resolve_qgis_enum
from ...logger import log_event


def _find_layer_by_name(name):
    if not QGIS_AVAILABLE:
        return None
    layers = QgsProject.instance().mapLayersByName(name)
    if not layers:
        return None
    return layers[0]


def _run_and_add(alg, params, new_name):
    """Shared Processing-run-and-register helper behind ~18 vector tools
    (intersect_layers, union_layers, spatial_join, buffer_analysis,
    dissolve, clip, difference, etc.). Point 22 of
    docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md flagged this
    function by name as the flagship unhandled case: a spatial operation
    that runs without error but produces an empty output layer (e.g. two
    layers that don't actually overlap) previously returned a bare
    {"success": True} identical to a real result, with nothing surfacing
    the zero-feature outcome to the caller. Fixed once here rather than in
    each of the ~18 call sites, so every one of them picks it up
    automatically -- the same "extend the shared function" fix shape
    point 4's diagnose_topology extension already used."""
    try:
        output = processing.run(alg, params)
        new_layer = output["OUTPUT"]
        if hasattr(new_layer, "setName"):
            new_layer.setName(new_name)
            QgsProject.instance().addMapLayer(new_layer)
        result = {"success": True, "layer_name": new_name}
        if hasattr(new_layer, "featureCount"):
            try:
                count = int(new_layer.featureCount())
            except (TypeError, ValueError):
                count = None
            if count is not None:
                result["feature_count"] = count
                if count == 0:
                    result["warning"] = (
                        f"'{new_name}' was created but has 0 features -- the operation ran "
                        "without error but produced an empty result (e.g. no overlap "
                        "between the inputs, or every feature was filtered out). Do not "
                        "report this as a successful result without checking the inputs "
                        "first."
                    )
        return result
    except Exception as e:
        return {"error": f"{alg} failed: {e}"}


@register_tool(
    "get_layers",
    "Get all layers in current QGIS project with name, type, ID, CRS, feature count, and field "
    "names in one call -- covers most basic inspection needs (a vector layer's field names, a "
    "rough size check via feature_count) without a separate get_attributes round trip per layer. "
    "Point 21 of docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md. feature_count/fields are "
    "omitted for layers that don't have them (e.g. a raster has no attribute table).",
    {"type": "object", "properties": {}, "required": []},
)
def get_layers():
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    result = []
    for layer_id, layer in QgsProject.instance().mapLayers().items():
        crs = layer.crs() if hasattr(layer, "crs") else None
        entry = {
            "name": layer.name(),
            "type": layer.type().name if hasattr(layer.type(), "name") else str(layer.type()),
            "id": layer_id,
            "crs": crs.authid() if crs else None,
        }
        # Vector-only: a raster layer has neither an attribute table nor a
        # feature count, so these are only added when actually present
        # rather than reported as empty/zero.
        if hasattr(layer, "fields"):
            entry["fields"] = list(layer.fields().names())
        if hasattr(layer, "featureCount"):
            entry["feature_count"] = layer.featureCount()
        result.append(_model_view_entry(entry, layer))
    return result


def bbox_orders(west, south, east, north):
    """The same WGS84 box in both orders this plugin's tools want, with names so the order cannot be guessed. Pure.

    fetch_osm_features / fetch_building_footprints take [south, west, north, east]; search_stac_satellite_imagery takes
    [west, south, east, north]. rc18 hand test N4/N5 (2026-10-06): with no way to ask QGIS for a layer's extent in degrees the model
    recalled a bounding box from memory (Damascus, for a fixture in Jordan) and passed it to both tools."""
    w, s_, e, n = (round(float(v), 6) for v in (west, south, east, north))
    return {"west": w, "south": s_, "east": e, "north": n,
            "bbox_south_west_north_east": [s_, w, n, e], "bbox_west_south_east_north": [w, s_, e, n]}


@register_tool(
    "get_layer_extent",
    "Get a layer's extent, in its own CRS and transformed to WGS84 degrees. Use this -- never a remembered or estimated bounding box -- "
    "whenever a tool needs a bbox in degrees (fetch_osm_features, fetch_building_footprints, search_stac_satellite_imagery, fetch_worldpop_population). "
    "The result gives the box in BOTH orders, named: bbox_south_west_north_east for the OSM and building-footprint tools, "
    "bbox_west_south_east_north for the STAC search. Pass layer_name='canvas' for the current map view.",
    {"type": "object", "properties": {"layer_name": {"type": "string", "description": "A layer name, or 'canvas' for the current map view."}},
     "required": ["layer_name"]},
)
def get_layer_extent(layer_name):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    from qgis.core import QgsCoordinateReferenceSystem as _Crs, QgsCoordinateTransform as _Xf
    if str(layer_name).strip().lower() == "canvas":
        try:
            from qgis.utils import iface
            canvas = iface.mapCanvas()
            rect, crs = canvas.extent(), canvas.mapSettings().destinationCrs()
        except Exception as e:
            return {"error": f"Could not read the map canvas: {e}"}
        label = "the current map view"
    else:
        layer = _find_layer_by_name(layer_name)
        if layer is None:
            return {"error": f"Layer '{layer_name}' not found"}
        rect, crs, label = layer.extent(), layer.crs(), f"layer '{layer_name}'"
    if rect is None or rect.isNull() or rect.isEmpty():
        return {"error": f"{label} has no extent (it may be empty)."}
    if not crs.isValid():
        return {"error": f"{label} has no valid CRS, so its extent cannot be expressed in degrees."}
    try:
        wgs = _Xf(crs, _Crs("EPSG:4326"), QgsProject.instance()).transformBoundingBox(rect)
    except Exception as e:
        return {"error": f"Could not transform the extent of {label} to WGS84: {e}"}
    result = {"success": True, "source": label, "source_crs": crs.authid(),
              "native_extent": {"xmin": rect.xMinimum(), "ymin": rect.yMinimum(), "xmax": rect.xMaximum(), "ymax": rect.yMaximum()},
              "wgs84": bbox_orders(wgs.xMinimum(), wgs.yMinimum(), wgs.xMaximum(), wgs.yMaximum()),
              "note": "Use the bbox that matches the tool's order. Degrees; the box is the transformed rectangle, slightly larger than a rotated area needs."}
    return result


def _model_view_entry(entry, layer):
    """The layer entry as the model may see it: field names withheld for a protected layer when the cloud gate is
    enforcing (F21). See models/model_view.py."""
    try:
        from ...models import model_view, sensitivity
        return model_view.apply_to_layer_entry(entry, sensitivity.get_layer_sensitivity(layer).get("level"))
    except Exception:
        return entry


@register_tool("get_attributes", "Get list of field/attribute names for a layer.", {"type": "object", "properties": {"layer_name": {"type": "string"}}, "required": ["layer_name"]})
def get_attributes(layer_name):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    layer = _find_layer_by_name(layer_name)
    if layer is None:
        return {"error": f"Layer '{layer_name}' not found"}
    if not hasattr(layer, "fields"):
        return {"error": f"Layer '{layer_name}' has no attribute fields"}
    return list(layer.fields().names())


@register_tool("run_query", "Filter layer features using a QGIS expression.", {"type": "object", "properties": {"layer_name": {"type": "string"}, "expression": {"type": "string"}}, "required": ["layer_name", "expression"]})
def run_query(layer_name, expression):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    layer = _find_layer_by_name(layer_name)
    if layer is None:
        return {"error": f"Layer '{layer_name}' not found"}

    expr = QgsExpression(expression)
    if expr.hasParserError():
        return {"error": f"Invalid expression: {expr.parserErrorString()}"}

    if not layer.setSubsetString(expression):
        return {"error": "Failed to apply filter (layer may not support subset strings)"}
    return {"success": True, "message": f"Filter applied to '{layer_name}'", "count": layer.featureCount()}


@register_tool(
    "buffer_analysis",
    "Create a buffer polygon layer around features. `distance` is interpreted in the layer's "
    "OWN CRS units, not automatically converted -- meters for a typical projected/UTM CRS, but "
    "DEGREES for a geographic CRS (e.g. EPSG:4326/WGS84). Buffering a WGS84 layer by 500 "
    "expecting 500 meters actually buffers by 500 degrees (most of the way around the globe), "
    "not a small error but a silently nonsensical result. If the target layer's CRS is "
    "geographic, reproject it to an appropriate projected/UTM CRS first (or check "
    "get_layers()'s crs field before calling this). To buffer only SPECIFIC features "
    "(e.g. 'buffer around alerts X and Y', not the whole layer), first select them -- "
    "select_by_attribute for one value, or highlight_features with an expression like "
    "\"event_id IN ('X','Y')\" for several -- then call this with only_selected=True. "
    "Without only_selected=True, this always buffers every feature in the layer, "
    "regardless of any current selection.",
    {
        "type": "object",
        "properties": {
            "layer_name": {"type": "string"},
            "distance": {
                "type": "number",
                "description": "Buffer distance in the layer's own CRS units (meters for a projected CRS, degrees for a geographic one -- see this tool's own description).",
            },
            "only_selected": {
                "type": "boolean",
                "description": "If true, buffer only the layer's currently-selected features instead of the whole layer. Errors if nothing is selected, rather than silently falling back to the full layer.",
            },
            "output_name": {
                "type": "string",
                "description": "Name for the new buffer layer, used exactly as given when the user asked for a specific name. Omit to get '<layer>_buffer_<distance>'.",
            },
        },
        "required": ["layer_name", "distance"],
    },
)
def buffer_analysis(layer_name, distance, only_selected=False, output_name=None):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    layer = _find_layer_by_name(layer_name)
    if layer is None:
        return {"error": f"Layer '{layer_name}' not found"}

    if only_selected and layer.selectedFeatureCount() == 0:
        # Same fail-loudly-not-silently-wrong choice as export_tools.py's _write_vector:
        # a caller explicitly asking to buffer "just these features" getting the WHOLE
        # layer back instead, with no error, is a much worse failure mode than an
        # explicit error here -- confirmed live 2026-09-24: "buffer 5 km around active
        # GDACS alerts X,Y" with no selected-only option meant the model had no way to
        # scope the buffer to just those 2 alerts at all.
        return {
            "error": "only_selected=True was requested, but the layer has no features "
            "currently selected. Select the target features first (select_by_attribute "
            "or highlight_features), or omit only_selected to buffer the whole layer "
            "intentionally."
        }

    try:
        buffer_input = (
            QgsProcessingFeatureSourceDefinition(layer.id(), selectedFeaturesOnly=True)
            if only_selected else layer
        )
        params = {
            "INPUT": buffer_input,
            "DISTANCE": distance,
            "SEGMENTS": 5,
            "END_CAP_STYLE": 0,
            "JOIN_STYLE": 0,
            "MITER_LIMIT": 2,
            "DISSOLVE": False,
            "OUTPUT": "memory:",
        }
        output = processing.run("native:buffer", params)
        new_layer = output["OUTPUT"]
        # rc17 hand test D11 (2026-10-06): "name the result smoke_points_buffer_500m" came out as smoke_points_buffer_500 because
        # the tool had no way to be told a name.
        new_name = str(output_name).strip() if output_name and str(output_name).strip() else f"{layer_name}_buffer_{distance}"
        new_layer.setName(new_name)

        # Map Intelligence Engine: local role-based insertion (below source layer) & component symbology (20% fill, 100% stroke)
        from ..map_intelligence import process_map_output
        intel_res = process_map_output(
            new_layer,
            output_role="proximity_buffer",
            source_layer_id=layer.id() if hasattr(layer, "id") else None,
        )

        result = {
            "success": True,
            "layer_name": new_name,
            "action_chips": intel_res.get("action_chips", []),
            "only_selected_features": bool(only_selected),
            "input_feature_count": layer.selectedFeatureCount() if only_selected else layer.featureCount(),
        }
        if intel_res.get("findings"):
            result["map_quality_findings"] = intel_res["findings"]
        # Point 3 of docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md,
        # confirmed live against real QGIS 4.2.2: native:buffer's DISTANCE is
        # applied in the input layer's own CRS units with no conversion --
        # buffering an EPSG:4326 point by 500 (meaning 500 meters) actually
        # produced a buffer 1000 degrees wide (500 on each side), not ~1km.
        # No computed-UTM-from-AOI reprojection exists to silently "fix" this
        # (a real, separate feature -- not invented here), so this is an
        # honest warning, not a guessed correction.
        try:
            if layer.crs().isGeographic():
                result["warning"] = (
                    f"'{layer_name}' is in a geographic CRS ({layer.crs().authid()}), so "
                    f"distance={distance} was applied in DEGREES, not meters -- the output is "
                    "very likely not the buffer you intended. Reproject the layer to a "
                    "projected/UTM CRS first, then re-run this with a distance in meters."
                )
        except Exception as e:
            log_event("swallowed_exception", tag="Tools", tool="buffer_crs_warning",
                      error_class=type(e).__name__, error=True)
        return result
    except Exception as e:
        return {"error": f"Buffer analysis failed: {e}"}


@register_tool("highlight_features", "Select features in a layer matching expression.", {"type": "object", "properties": {"layer_name": {"type": "string"}, "expression": {"type": "string"}}, "required": ["layer_name", "expression"]})
def highlight_features(layer_name, expression):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    layer = _find_layer_by_name(layer_name)
    if layer is None:
        return {"error": f"Layer '{layer_name}' not found"}

    expr = QgsExpression(expression)
    if expr.hasParserError():
        return {"error": f"Invalid expression: {expr.parserErrorString()}"}

    layer.selectByExpression(expression)
    count = layer.selectedFeatureCount()
    return {"success": True, "count": count}


@register_tool("remove_layer", "Remove layer from QGIS project. Destructive action requiring UI confirmation.", {"type": "object", "properties": {"layer_name": {"type": "string"}}, "required": ["layer_name"]})
def remove_layer(layer_name: str, confirmed: bool = False):
    if not confirmed:
        return {
            "status": "PREVIEW_REQUIRED",
            "requires_confirmation": True,
            "is_destructive": True,
            "tool_name": "remove_layer",
            "arguments": {"layer_name": layer_name, "confirmed": True},
            "code_snippet": f"QgsProject.instance().removeMapLayer('{layer_name}')",
            "rationale": f"Destructive Action Preview: Remove layer '{layer_name}' permanently from project.",
            "message": f"Confirmation required before removing layer '{layer_name}'."
        }

    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    layer = _find_layer_by_name(layer_name)
    if layer is None:
        return {"error": f"Layer '{layer_name}' not found"}

    QgsProject.instance().removeMapLayer(layer.id())
    return {"success": True, "message": f"Removed layer '{layer_name}'"}


@register_tool("rename_layer", "Rename layer in QGIS project.", {"type": "object", "properties": {"old_name": {"type": "string"}, "new_name": {"type": "string"}}, "required": ["old_name", "new_name"]})
def rename_layer(old_name, new_name):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    layer = _find_layer_by_name(old_name)
    if layer is None:
        return {"error": f"Layer '{old_name}' not found"}
    layer.setName(new_name)
    return {"success": True, "message": f"Renamed '{old_name}' to '{new_name}'"}


def _extent_to_canvas_crs(canvas, extent, source_crs):
    """Transforms extent from source_crs into the canvas's own destination
    CRS. canvas.setExtent() expects the extent already in the canvas's CRS,
    but a layer's .extent()/a feature's boundingBox() is in the LAYER's own
    CRS, which is very often different from the canvas/project CRS -- e.g. a
    freshly fetched WGS84 (degrees) boundary layer against a Web Mercator
    (meters) OSM-basemap project, a near-universal setup. Passing the raw
    layer-CRS extent straight into setExtent() silently produces a wildly
    wrong view: degree-magnitude numbers applied as if they were Web
    Mercator meters lands the canvas near the map's coordinate origin
    instead of the actual layer -- confirmed as the cause of exactly this
    symptom in live use. Returns the extent unchanged if source_crs already
    matches the canvas CRS. If the transform itself fails it returns None
    (rc20 audit A13: it used to hand back the untransformed extent, which is
    exactly the wrong-place zoom described above, reported as success), so
    callers must report an error instead of zooming."""
    canvas_crs = canvas.mapSettings().destinationCrs()
    if not source_crs.isValid() or source_crs == canvas_crs:
        return extent
    try:
        transform = QgsCoordinateTransform(source_crs, canvas_crs, QgsProject.instance())
        return transform.transformBoundingBox(extent)
    except Exception:
        return None


@register_tool("zoom_to_layer", "Zoom canvas to extent of layer.", {"type": "object", "properties": {"layer_name": {"type": "string"}}, "required": ["layer_name"]})
def zoom_to_layer(layer_name):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    layer = _find_layer_by_name(layer_name)
    if layer is None:
        return {"error": f"Layer '{layer_name}' not found"}
    if iface is None:
        return {"error": "QGIS interface not available"}
    canvas = iface.mapCanvas()
    extent = _extent_to_canvas_crs(canvas, layer.extent(), layer.crs())
    if extent is None:
        return {"error": f"Could not transform '{layer_name}' from {layer.crs().authid()} into the map CRS, so the view was not changed."}
    canvas.setExtent(extent)
    canvas.refresh()
    return {"success": True, "message": f"Zoomed to '{layer_name}'"}


@register_tool("toggle_visibility", "Show or hide a layer in layer tree.", {"type": "object", "properties": {"layer_name": {"type": "string"}, "visible": {"type": "boolean"}}, "required": ["layer_name"]})
def toggle_visibility(layer_name, visible=True):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    layer = _find_layer_by_name(layer_name)
    if layer is None:
        return {"error": f"Layer '{layer_name}' not found"}
    node = QgsProject.instance().layerTreeRoot().findLayer(layer.id())
    if node is None:
        return {"error": f"Layer tree node for '{layer_name}' not found"}
    node.setItemVisibilityChecked(bool(visible))
    return {"success": True, "message": f"Layer '{layer_name}' visibility set to {bool(visible)}"}


def _is_safe_url(file_path):
    """Rejects URLs that resolve to loopback/private/link-local/reserved
    addresses -- including 169.254.169.254, the cloud-provider metadata
    endpoint -- before anything fetches them. file_path is LLM-controlled (the
    model names the URL in a tool call), so without this a prompt-injected
    instruction could point add_layer_from_path at an internal service or a
    metadata endpoint (SSRF). Returns an error string, or None if the URL is
    safe to fetch."""
    import socket
    import ipaddress
    from urllib.parse import urlparse

    parsed = urlparse(file_path)
    if parsed.scheme not in ("http", "https"):
        return f"Unsupported URL scheme '{parsed.scheme}'."
    host = parsed.hostname
    if not host:
        return "URL has no host."

    try:
        addr = ipaddress.ip_address(host)
        addrs = [addr]
    except ValueError:
        try:
            addrs = [ipaddress.ip_address(a[4][0]) for a in socket.getaddrinfo(host, None)]
        except (socket.gaierror, OSError) as e:
            return f"Could not resolve host '{host}': {e}"

    for addr in addrs:
        if addr.is_loopback or addr.is_private or addr.is_link_local or addr.is_reserved or addr.is_multicast:
            return f"URL resolves to a non-public address ({addr}) -- refusing to fetch."
    return None


_MAX_DOWNLOAD_BYTES = 200 * 1024 * 1024  # 200MB -- generous for GeoJSON/small rasters, not unbounded


class _SafeRedirectHandler:
    """Re-validates every redirect target against _is_safe_url before
    following it. Confirmed live (a local redirect server) that Python's
    default HTTPRedirectHandler follows a 3xx unconditionally: a URL that
    passed _is_safe_url at call time can 302 to a completely different,
    unvalidated address (e.g. the cloud metadata endpoint) and urlopen()
    fetches it anyway -- validating file_path once, before the request, is
    not sufficient on its own. Mixed into a real HTTPRedirectHandler at
    build time (see _build_safe_opener) rather than subclassed directly, so
    this stays a plain, import-light class."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        import urllib.error
        unsafe_reason = _is_safe_url(newurl)
        if unsafe_reason:
            raise urllib.error.URLError(f"Redirect blocked: {unsafe_reason}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _build_safe_opener():
    import urllib.request

    class _Handler(_SafeRedirectHandler, urllib.request.HTTPRedirectHandler):
        pass

    return urllib.request.build_opener(_Handler)


def _prefetch_url_to_temp(file_path):
    """If file_path is an http(s) URL, downloads it to a local temp file (pure
    network I/O, no qgis.core access -- safe to run on a background thread)
    and returns (temp_path, True). Otherwise returns (file_path, False)
    unchanged. Caller is responsible for deleting the temp file when done.
    Used by agent_orchestrator.py's two-phase dispatch to keep the download off the QGIS
    main GUI thread; add_layer_from_path also calls this itself so it still
    works correctly when invoked directly (e.g. outside the agent, in tests).

    Every redirect hop is re-validated (see _SafeRedirectHandler) and the
    response body is capped at _MAX_DOWNLOAD_BYTES, streamed rather than
    read() in one shot -- file_path is LLM-controlled, so neither the final
    destination nor the response size can be trusted just because the
    initial URL passed _is_safe_url."""
    if not (file_path.startswith("http://") or file_path.startswith("https://")):
        return file_path, False

    unsafe_reason = _is_safe_url(file_path)
    if unsafe_reason:
        raise ValueError(f"Refusing to fetch URL: {unsafe_reason}")

    import os
    import tempfile
    import urllib.request

    clean = file_path.split("?")[0]
    ext = os.path.splitext(clean)[1] or ""
    req = urllib.request.Request(file_path, headers={"User-Agent": "QGIS-AI-Assistant"})
    opener = _build_safe_opener()
    fd, tmp_path = tempfile.mkstemp(suffix=ext)
    try:
        # os.fdopen wraps the fd first, before the network call -- if
        # opener.open() raised inside a combined `with a, b:` instead, the
        # raw fd from mkstemp would never get closed on that path.
        with os.fdopen(fd, "wb") as f:
            with opener.open(req, timeout=60) as response:
                total = 0
                while True:
                    chunk = response.read(65536)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > _MAX_DOWNLOAD_BYTES:
                        raise ValueError(
                            f"Download exceeded the {_MAX_DOWNLOAD_BYTES // (1024 * 1024)}MB size limit -- refusing to continue."
                        )
                    f.write(chunk)
    except Exception:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise
    return tmp_path, True


_SPATIALITE_EXTS = {".sqlite", ".db"}


def _ensure_spatialite_index(layer):
    """SpatiaLite has no automatic spatial-indexing verification -- a table loaded without
    one (e.g. exported by a tool that never ran CreateSpatialIndex) silently falls back to
    a full table scan for every spatial predicate/join against it, with nothing surfacing
    that to the caller. QgsVectorDataProvider.createSpatialIndex() is the standard PyQGIS
    way to check-and-create one: a no-op returning True if the provider doesn't support
    indexes or one already exists, best-effort creation otherwise. Returns a note if index
    creation was attempted and failed, or None if nothing needed reporting (already
    indexed, or the provider doesn't support spatial indexes at all)."""
    try:
        provider = layer.dataProvider()
        if provider is None:
            return None
        ok = provider.createSpatialIndex()
    except Exception as e:
        return f"Could not verify/create a spatial index on this SpatiaLite layer: {e}"
    if not ok:
        return "Could not create a spatial index on this SpatiaLite layer -- spatial queries against it may be slow on large tables."
    return None


def _ensure_shapefile_encoding(layer, shp_path):
    """A .shp has no built-in text encoding of its own -- a sibling .cpg file (or the
    now-legacy .dbf codepage byte) is the only place that's ever recorded, and plenty of
    real-world shapefiles (especially older exports) have neither. Without one, GDAL/OGR
    falls back to a platform-dependent default (commonly Windows-1252 on Windows), which
    silently corrupts non-Latin-script attribute values (Arabic, Cyrillic, etc. --
    directly relevant to this project's humanitarian/OCHA data). When no .cpg is present,
    explicitly sets the layer's provider encoding to UTF-8 instead of leaving it to that
    default -- UTF-8 won't help a shapefile that was actually written in some OTHER
    non-UTF-8 encoding with no .cpg to say so, but it's a materially safer default than
    Windows-1252 for the common case of a UTF-8-exported shapefile missing its .cpg.
    Returns a human-readable note on what happened, or None if a .cpg was found (nothing
    to override -- GDAL already knows the real encoding)."""
    cpg_path = os.path.splitext(shp_path)[0] + ".cpg"
    if os.path.isfile(cpg_path):
        return None
    try:
        layer.dataProvider().setEncoding("UTF-8")
    except Exception:
        return "No .cpg file found and could not override the provider encoding -- attribute values in a non-UTF-8/non-ASCII script may be garbled."
    return "No .cpg file found alongside this shapefile -- assumed UTF-8 instead of the platform default. If attribute text looks garbled, the shapefile may actually be in a different encoding (e.g. Windows-1256 for Arabic)."


_GEOJSON_TYPES = {
    "FeatureCollection", "Feature", "Point", "MultiPoint", "LineString",
    "MultiLineString", "Polygon", "MultiPolygon", "GeometryCollection",
}


def _describe_unreadable_download(path):
    """Best guess at why GDAL rejected a downloaded file, from its first bytes.

    Without this, a URL that serves the wrong content fails with only "Invalid layer".
    For example, a GitHub /blob/ page URL returns HTML instead of the raw file, and an
    API may return an error JSON or a zip. The model then has nothing to correct
    against. Reported live (2026-09-24, QGIS 4.2.2): "Invalid layer:
    C:\\...\\Temp\\tmp_2kgn_72.geojson" after a URL load, with no hint of the cause.

    Only returns a short classification plus, for JSON, up to 5 top-level key names.
    It never includes body content. The result goes to the model as a tool error and
    is not logged. Returns None if nothing recognizable was found."""
    import json
    import os

    try:
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            head = f.read(4096)
    except OSError:
        return None
    if size == 0:
        return "The downloaded file is empty."
    text = head.lstrip(b"\xef\xbb\xbf \t\r\n").lower()
    if text.startswith(b"pk\x03\x04"):
        return ("The download is a zip archive, not a single geodata file. Load a direct link "
                "to the file inside it, or a URL that serves the file itself.")
    if text.startswith(b"<!doctype html") or text.startswith(b"<html") or b"<html" in text[:512]:
        return ("The URL returned an HTML web page, not geodata. For GitHub, use the "
                "raw.githubusercontent.com link (the 'Raw' button), not the /blob/ page URL. "
                "For other sites, use the direct download link.")
    if text.startswith(b"<?xml") or text.startswith(b"<"):
        return ("The URL returned XML that GDAL could not read as a layer. It may be a "
                "server error/exception report rather than data.")
    if text.startswith(b"{") or text.startswith(b"["):
        if size > 5 * 1024 * 1024:
            return None
        try:
            with open(path, "rb") as f:
                doc = json.loads(f.read().decode("utf-8-sig"))
        except (ValueError, UnicodeDecodeError):
            return "The download looks like JSON but is not valid JSON (possibly truncated)."
        if isinstance(doc, dict) and doc.get("type") in _GEOJSON_TYPES:
            if doc.get("type") == "FeatureCollection" and not doc.get("features"):
                return "The download is a GeoJSON FeatureCollection with no features."
            return None
        if isinstance(doc, dict):
            keys = ", ".join(sorted(str(k)[:40] for k in doc)[:5])
            return (f"The download is JSON but not GeoJSON (no FeatureCollection/Feature/geometry "
                    f"'type'). Top-level keys: {keys or 'none'}. It may be an API error response "
                    f"or a wrapper around the real data URL.")
        return "The download is a JSON array, not a GeoJSON object."
    return None


@register_tool("add_layer_from_path", "Load vector or raster file from a local path or remote URL (e.g. a GeoJSON download link).", {"type": "object", "properties": {"file_path": {"type": "string"}, "layer_name": {"type": "string"}}, "required": ["file_path"]})
def add_layer_from_path(file_path, layer_name=None, source_label=None):
    """source_label is the original URL when agent_orchestrator.py has already downloaded
    it and file_path is the local temp copy. Without it, the default layer name and
    error messages came from the temp file ("tmp_2kgn_72") instead of the URL the model
    asked for. It is not in the tool schema, so the model can't set it: the dispatcher
    filters args to schema properties."""
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}

    import os

    # Downloads here if called directly with a URL (e.g. in tests, or outside the
    # agent). When dispatched through agent_orchestrator.py's two-phase handling, file_path has
    # already been swapped to a local temp path there, so this is a no-op.
    try:
        local_path, is_temp = _prefetch_url_to_temp(file_path)
    except Exception as e:
        return {"error": f"Download failed: {e}"}
    try:
        if not is_temp and not os.path.exists(local_path):
            return {"error": f"File not found: {file_path}"}

        label = source_label or file_path
        downloaded = is_temp or bool(source_label)
        clean_path = label.split("?")[0]
        name = layer_name or os.path.splitext(os.path.basename(clean_path.rstrip("/")))[0] or "layer"
        ext = os.path.splitext(clean_path)[1].lower()
        raster_exts = {".tif", ".tiff", ".geotiff", ".img", ".asc", ".jp2", ".png", ".jpg", ".jpeg"}

        encoding_note = None
        if ext in raster_exts:
            layer = QgsRasterLayer(local_path, name)
        else:
            layer = QgsVectorLayer(local_path, name, "ogr")
            if ext == ".shp":
                encoding_note = _ensure_shapefile_encoding(layer, local_path)

        if not layer.isValid():
            error = f"Invalid layer: {label}"
            if downloaded:
                reason = _describe_unreadable_download(local_path)
                error += f" -- {reason}" if reason else " -- the downloaded file could not be read as a vector or raster layer."
            return {"error": error}

        QgsProject.instance().addMapLayer(layer)
        result = {"success": True, "layer_name": layer.name()}
        if encoding_note:
            result["encoding_note"] = encoding_note
        if ext in _SPATIALITE_EXTS:
            spatial_index_note = _ensure_spatialite_index(layer)
            if spatial_index_note:
                result["spatial_index_note"] = spatial_index_note
        return result
    finally:
        if is_temp:
            try:
                os.remove(local_path)
            except OSError:
                pass


# Ordered by confidence -- checked in this order, first exact (case-insensitive)
# name match wins. Bare "x"/"y" are last resort since those names are common
# for non-coordinate columns too; only used when nothing more specific matches.
_LAT_NAME_PRIORITY = ["latitude", "lat", "y"]
_LON_NAME_PRIORITY = ["longitude", "long", "lon", "lng", "x"]
_WKT_NAME_PRIORITY = ["wkt", "geom", "geometry", "the_geom"]


def _sniff_csv_header(file_path, delimiter=","):
    """Reads just the first row of a CSV for its column names. Deliberately
    doesn't use pandas (unlike the file-attachment preview elsewhere) so
    geometry-column auto-detection still works even when that optional
    dependency isn't installed, or when the CSV wasn't attached through the
    chat UI at all (e.g. the user just names a path in a message)."""
    import csv
    with open(file_path, "r", encoding="utf-8-sig", errors="ignore", newline="") as f:
        reader = csv.reader(f, delimiter=delimiter)
        return next(reader, [])


def _sniff_excel_header(file_path, sheet_name=None):
    """Reads just the column names of an Excel sheet -- the Excel analogue of
    _sniff_csv_header, needed so geometry-column auto-detection covers Excel
    too (it previously only ran for CSV, so a spreadsheet with lat/lon
    columns was always loaded as a plain non-spatial table). Requires
    pandas/openpyxl -- these are optional, qpip-managed dependencies."""
    import pandas as pd
    # sheet_name=None is a pandas special case meaning "read every sheet into
    # a dict" -- pass 0 (first sheet) instead when none was specified.
    df = pd.read_excel(file_path, sheet_name=sheet_name or 0, nrows=0)
    return list(df.columns)


def _detect_geometry_fields(header):
    """Best-effort match against common lat/lon/WKT column naming
    conventions. Only returns a mapping when a name matches exactly
    (case-insensitively) -- ambiguous headers are left for the caller to
    resolve explicitly (FIELD_SUGGESTION) rather than silently guessing wrong
    and creating a mislocated layer."""
    lower_map = {str(h).strip().lower(): h for h in header}

    for name in _WKT_NAME_PRIORITY:
        if name in lower_map:
            return {"wkt_field": lower_map[name]}

    lat = next((lower_map[n] for n in _LAT_NAME_PRIORITY if n in lower_map), None)
    lon = next((lower_map[n] for n in _LON_NAME_PRIORITY if n in lower_map), None)
    if lat and lon:
        return {"x_field": lon, "y_field": lat}
    return None


def _validate_wgs84_coordinates(x_values, y_values):
    """Pure Python, no QGIS needed -- sanity-checks a sample of x/y values
    against valid WGS84 longitude/latitude ranges before a point layer is
    built from them. Catches a common, otherwise-silent failure mode: an
    auto-detected or manually-specified x_field/y_field pair that's actually
    swapped, or pointed at the wrong columns entirely -- which would
    otherwise build a layer that loads without any error and just plots
    every point in the wrong place. Only meaningful for EPSG:4326 (the
    default and overwhelmingly common case); the caller skips this for any
    other CRS since valid ranges vary."""
    if not x_values or not y_values:
        return None
    pairs = list(zip(x_values, y_values))
    bad = [(x, y) for x, y in pairs if not (-180 <= x <= 180 and -90 <= y <= 90)]
    if len(bad) > len(pairs) / 2:
        return (
            f"{len(bad)}/{len(pairs)} sampled coordinate pairs are outside valid WGS84 "
            f"longitude/latitude ranges (e.g. x={bad[0][0]}, y={bad[0][1]}) -- x_field/y_field may "
            "be swapped, pointed at the wrong columns, or the data isn't in EPSG:4326 degrees "
            "(pass the correct crs if it's already projected, e.g. UTM meters)."
        )
    return None


def _sample_xy_values(file_path, ext, x_field, y_field, delimiter, sheet_name, limit=20):
    """Reads up to `limit` (x, y) pairs directly from the source file, for
    _validate_wgs84_coordinates -- deliberately independent of the QGIS
    layer-loading path below so the sanity check runs BEFORE a layer is
    actually built, not after. Any read failure just yields an empty sample
    (validation is skipped, not treated as fatal -- this is a heuristic
    safety net, not a required step)."""
    xs, ys = [], []
    try:
        if ext == ".csv":
            import csv
            with open(file_path, "r", encoding="utf-8-sig", errors="ignore", newline="") as f:
                reader = csv.DictReader(f, delimiter=delimiter)
                for i, row in enumerate(reader):
                    if i >= limit:
                        break
                    try:
                        xs.append(float(row[x_field]))
                        ys.append(float(row[y_field]))
                    except (KeyError, TypeError, ValueError):
                        continue
        else:
            import pandas as pd
            df = pd.read_excel(file_path, sheet_name=sheet_name or 0, nrows=limit)
            for _, row in df.iterrows():
                try:
                    xs.append(float(row[x_field]))
                    ys.append(float(row[y_field]))
                except (KeyError, TypeError, ValueError):
                    continue
    except Exception:
        return [], []
    return xs, ys


def _qvariant_type_for_dtype(dtype):
    """Maps a pandas column dtype to the closest QVariant field type, for
    building a QgsFields schema out of a DataFrame. Falls back to String for
    anything not clearly numeric/boolean/datetime -- safe default, since
    QGIS can always display a value as text even if a tighter type would
    have been possible.

    Uses pandas' own is_*_dtype predicates rather than raw np.issubdtype --
    confirmed live that np.issubdtype raises TypeError on pandas' newer
    extension dtypes (e.g. the Arrow-backed/nullable string dtype), which
    aren't plain numpy dtypes at all. pandas' predicates handle both numpy
    and pandas extension dtypes correctly."""
    import pandas as pd
    if pd.api.types.is_bool_dtype(dtype):
        return QVariant.Bool
    if pd.api.types.is_integer_dtype(dtype):
        return QVariant.LongLong
    if pd.api.types.is_float_dtype(dtype):
        return QVariant.Double
    if pd.api.types.is_datetime64_any_dtype(dtype):
        return QVariant.DateTime
    return QVariant.String


def _load_excel_as_geometry_layer(file_path, name, sheet_name, x_field, y_field, wkt_field, crs):
    """Builds a real in-memory point/geometry QGIS layer from an Excel
    sheet's x/y or WKT column(s) -- the Excel analogue of the CSV path's
    'delimitedtext' provider, which can't be reused here since it expects a
    plain-text CSV, not an Excel binary file. Reads the full sheet via
    pandas rather than QGIS's OGR Excel driver so attribute typing can be
    inferred from pandas dtypes and geometries built explicitly per row."""
    try:
        import pandas as pd
    except ImportError:
        return {"error": "pandas and openpyxl are required to load Excel geometry columns. Install via qpip, or in the OSGeo4W Shell: python -m pip install pandas openpyxl"}

    try:
        df = pd.read_excel(file_path, sheet_name=sheet_name or 0)
    except Exception as e:
        return {"error": f"Could not read Excel file: {e}"}

    missing = [c for c in (x_field, y_field, wkt_field) if c and c not in df.columns]
    if missing:
        return {"error": f"Column(s) not found in sheet: {missing}. Available columns: {list(df.columns)}"}

    geom_field_names = {f for f in (x_field, y_field, wkt_field) if f}
    attr_cols = [c for c in df.columns if c not in geom_field_names]

    if wkt_field:
        wkb_geom_type = None
        for val in df[wkt_field]:
            if isinstance(val, str) and val.strip():
                probe = QgsGeometry.fromWkt(val)
                if not probe.isNull():
                    wkb_geom_type = QgsWkbTypes.displayString(probe.wkbType())
                    break
        if wkb_geom_type is None:
            return {"error": f"No valid WKT geometry found in column '{wkt_field}'."}
        uri = f"{wkb_geom_type}?crs={crs}"
    else:
        uri = f"Point?crs={crs}"

    layer = QgsVectorLayer(uri, name, "memory")
    if not layer.isValid():
        return {"error": f"Could not create a memory layer for '{name}' (uri: {uri})."}
    provider = layer.dataProvider()
    provider.addAttributes([QgsField(str(col), _qvariant_type_for_dtype(df[col].dtype)) for col in attr_cols])
    layer.updateFields()

    features = []
    skipped = 0
    for _, row in df.iterrows():
        geom = None
        if wkt_field:
            val = row[wkt_field]
            if isinstance(val, str) and val.strip():
                g = QgsGeometry.fromWkt(val)
                if not g.isNull():
                    geom = g
        else:
            try:
                geom = QgsGeometry.fromPointXY(QgsPointXY(float(row[x_field]), float(row[y_field])))
            except (TypeError, ValueError):
                geom = None

        if geom is None:
            skipped += 1
            continue

        feat = QgsFeature(layer.fields())
        feat.setGeometry(geom)
        for col in attr_cols:
            val = row[col]
            if pd.isna(val):
                val = None
            elif hasattr(val, "isoformat"):
                val = val.isoformat()
            feat.setAttribute(str(col), val)
        features.append(feat)

    if not features:
        return {"error": "No valid geometries could be built from the given field(s) -- check x_field/y_field/wkt_field point to the right columns."}

    provider.addFeatures(features)
    layer.updateExtents()
    return {"layer": layer, "skipped_rows": skipped, "total_rows": len(df)}


@register_tool(
    "load_tabular_data_as_layer",
    "Load the FULL contents of a CSV or Excel (.xlsx/.xls) file as a real QGIS layer -- not a "
    "preview or a summary. Use this whenever the user has attached, downloaded, or referenced a "
    "spreadsheet/CSV file and wants the actual data in the project, not just a description of it. "
    "If the file has coordinate columns (e.g. latitude/longitude) or a WKT geometry column, pass "
    "x_field/y_field or wkt_field to create a real point/geometry layer; if omitted, this tool "
    "tries to auto-detect common column names on its own (for both CSV and Excel) and reports what "
    "it used -- if it can't confidently guess, it returns FIELD_SUGGESTION with the real column "
    "names instead of guessing wrong. Omit all three (or call again after a FIELD_SUGGESTION with "
    "none set) to load it as a plain non-spatial attribute table.",
    {
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "Absolute path to the .csv/.xlsx/.xls file."},
            "layer_name": {"type": "string"},
            "x_field": {"type": "string", "description": "Longitude/X column name."},
            "y_field": {"type": "string", "description": "Latitude/Y column name."},
            "wkt_field": {"type": "string", "description": "Column containing WKT geometry strings."},
            "sheet_name": {"type": "string", "description": "Sheet name for Excel files with multiple sheets. Defaults to the first sheet."},
            "crs": {"type": "string", "description": "CRS of x_field/y_field coordinates. Defaults to EPSG:4326."},
            "delimiter": {"type": "string", "description": "CSV field delimiter. Defaults to ','."},
        },
        "required": ["file_path"],
    },
)
def load_tabular_data_as_layer(file_path, layer_name=None, x_field=None, y_field=None, wkt_field=None, sheet_name=None, crs="EPSG:4326", delimiter=","):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}

    import os
    if not os.path.exists(file_path):
        return {"error": f"File not found: {file_path}"}

    ext = os.path.splitext(file_path)[1].lower()
    if ext not in (".csv", ".xlsx", ".xls"):
        return {"error": f"Unsupported file type '{ext}' for this tool -- use add_layer_from_path for other vector/raster formats."}

    name = layer_name or os.path.splitext(os.path.basename(file_path))[0] or "layer"
    auto_detected = None

    if not (x_field or y_field or wkt_field):
        try:
            header = _sniff_csv_header(file_path, delimiter) if ext == ".csv" else _sniff_excel_header(file_path, sheet_name)
        except ImportError:
            return {"error": "pandas and openpyxl are required to read Excel files. Install via qpip, or in the OSGeo4W Shell: python -m pip install pandas openpyxl"}
        except Exception as e:
            return {"error": f"Could not read file header: {e}"}
        detected = _detect_geometry_fields(header)
        if detected:
            x_field = detected.get("x_field")
            y_field = detected.get("y_field")
            wkt_field = detected.get("wkt_field")
            auto_detected = detected
        elif header:
            return {
                "status": "FIELD_SUGGESTION",
                "message": (
                    "Couldn't confidently auto-detect coordinate columns for a point layer. Call "
                    "again with x_field/y_field (or wkt_field) set to one of the columns below to "
                    "create a point layer, or call again with all three omitted to load the FULL "
                    "file as a non-spatial attribute table instead."
                ),
                "columns": header,
            }

    if x_field and y_field and crs.upper() == "EPSG:4326":
        xs, ys = _sample_xy_values(file_path, ext, x_field, y_field, delimiter, sheet_name)
        coord_warning = _validate_wgs84_coordinates(xs, ys)
        if coord_warning:
            return {"error": coord_warning}

    try:
        if ext in (".xlsx", ".xls") and (wkt_field or (x_field and y_field)):
            excel_res = _load_excel_as_geometry_layer(file_path, name, sheet_name, x_field, y_field, wkt_field, crs)
            if "error" in excel_res:
                return excel_res
            layer = excel_res["layer"]
        elif wkt_field or (x_field and y_field):
            from qgis.PyQt.QtCore import QUrl, QUrlQuery
            url = QUrl.fromLocalFile(file_path)
            query = QUrlQuery()
            query.addQueryItem("type", "csv")
            query.addQueryItem("delimiter", delimiter)
            if wkt_field:
                query.addQueryItem("wktField", wkt_field)
            else:
                query.addQueryItem("xField", x_field)
                query.addQueryItem("yField", y_field)
            query.addQueryItem("crs", crs)
            url.setQuery(query)
            layer = QgsVectorLayer(url.toString(), name, "delimitedtext")
        else:
            path_spec = file_path
            if ext in (".xlsx", ".xls") and sheet_name:
                path_spec = f"{file_path}|layername={sheet_name}"
            layer = QgsVectorLayer(path_spec, name, "ogr")

        if not layer.isValid():
            return {"error": f"Could not load '{file_path}' as a layer -- check the file and field names are correct."}

        QgsProject.instance().addMapLayer(layer)
        if layer.isSpatial():
            try:
                from .output_style import style_points_default
                if layer.geometryType() == QgsWkbTypes.GeometryType.PointGeometry:
                    style_points_default(layer)   # one consistent point look instead of a random default colour
                    from .output_style import style_auto_labels
                    style_auto_labels(layer)      # facility names when the layer is small enough to read
            except Exception:  # nosec B110 (best-effort: failure is non-fatal)
                pass
        result = {
            "success": True,
            "layer_name": layer.name(),
            "feature_count": layer.featureCount(),
            "is_spatial": layer.isSpatial(),
        }
        if auto_detected:
            result["auto_detected_geometry"] = auto_detected
        return result
    except Exception as e:
        return {"error": f"Failed to load '{file_path}': {e}"}


@register_tool(
    "apply_labels",
    "Apply text labels to a vector layer, either from a single field (target_field) or a QGIS "
    "expression combining multiple fields/literals (expression) -- e.g. a governorate name, P-code, "
    "and a count combined into one label like \"Sa'dah [YE22 | 4 Orgs]\" via "
    "\"adm1_name || ' [' || adm1_pcode || ' | ' || org_count || ' Orgs]'\" -- instead of hand-writing "
    "QgsPalLayerSettings code via execute_pyqgis_script for a combined label. Pass exactly one of "
    "target_field/expression. Applies a white text halo/buffer by default so labels stay legible over "
    "dense polygons or dark rasters, and -- for point layers -- an 8-position ordered placement with "
    "collision avoidance instead of an arbitrary single position.",
    {
        "type": "object",
        "properties": {
            "layer_name": {"type": "string"},
            "target_field": {"type": "string", "description": "A single field to label from. Omit if using expression instead."},
            "expression": {"type": "string", "description": "A QGIS expression combining multiple fields/literals into one label. Omit if using target_field instead."},
            "font_size": {"type": "number", "description": "Label text point size. Defaults to 10 -- pass a larger value for higher-hierarchy features (e.g. a capital vs. a village) and a smaller one for dense point layers."},
            "priority": {"type": "number", "description": "PAL anti-collision priority, 0 (lowest) to 10 (highest). Defaults to 5. Higher-priority labels win when two labels would otherwise overlap."},
        },
        "required": ["layer_name"],
    },
)
def apply_labels(layer_name, target_field=None, expression=None, font_size=10, priority=5):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}

    layer = _find_layer_by_name(layer_name)
    if layer is None:
        return {"error": f"Layer '{layer_name}' not found"}

    if not target_field and not expression:
        return {"error": "Pass either target_field or expression."}
    if target_field and expression:
        return {"error": "Pass only one of target_field or expression, not both."}

    # Validate the label source BEFORE constructing any QGIS style objects below, so a
    # bad expression/missing field returns cleanly without partially building (and
    # discarding) a QgsPalLayerSettings/QgsTextFormat pair.
    if expression:
        parsed = QgsExpression(expression)
        if parsed.hasParserError():
            return {"error": f"Invalid expression: {parsed.parserErrorString()}"}
        label_source = f"expression '{expression}'"
    else:
        field_names = [f.name() for f in layer.fields()]
        if target_field not in field_names:
            return {"error": f"Field '{target_field}' not found on layer '{layer_name}'. Available fields: {field_names}"}
        label_source = f"field '{target_field}'"

    settings = QgsPalLayerSettings()
    text_format = QgsTextFormat()
    if QFont is not None:
        try:
            text_format.setFont(QFont("Source Sans 3", int(font_size)))
        except Exception:  # nosec B110 (best-effort: failure is non-fatal)
            pass
    text_format.setColor(QColor("#1C1C1E"))
    text_format.setSize(font_size)

    # OGC SE 1.1.0-style halo/buffer -- 0.8mm, 80%-opacity white, round join -- so labels
    # stay legible over dense polygon fills or dark satellite/hillshade rasters instead of
    # sitting directly on top of them with no contrast separation.
    buffer_settings = QgsTextBufferSettings()
    buffer_settings.setEnabled(True)
    buffer_settings.setSize(0.8)
    buffer_settings.setSizeUnit(QgsUnitTypes.RenderMillimeters)
    buffer_settings.setColor(QColor(255, 255, 255, 204))
    buffer_settings.setJoinStyle(Qt.PenJoinStyle.RoundJoin if hasattr(Qt, "PenJoinStyle") else Qt.RoundJoin)
    text_format.setBuffer(buffer_settings)
    settings.setFormat(text_format)

    settings.priority = priority
    settings.obstacleSettings().setIsObstacle(True)

    # Geometry-specific placement and obstacle strategy (QGIS 4.2 cookbook)
    point_geometry = resolve_qgis_enum(QgsWkbTypes, "GeometryType", "PointGeometry")
    line_geometry = resolve_qgis_enum(QgsWkbTypes, "GeometryType", "LineGeometry")
    polygon_geometry = resolve_qgis_enum(QgsWkbTypes, "GeometryType", "PolygonGeometry")

    if point_geometry is not None and layer.geometryType() == point_geometry:
        ordered_positions = resolve_qgis_enum(QgsPalLayerSettings, "Placement", "OrderedPositionsAroundPoint")
        if ordered_positions is not None:
            settings.placement = ordered_positions
    elif line_geometry is not None and layer.geometryType() == line_geometry:
        curved = resolve_qgis_enum(QgsPalLayerSettings, "Placement", "Curved")
        if curved is not None:
            settings.placement = curved
    elif polygon_geometry is not None and layer.geometryType() == polygon_geometry:
        horizontal = resolve_qgis_enum(QgsPalLayerSettings, "Placement", "Horizontal")
        if horizontal is not None:
            settings.placement = horizontal
        settings.fitInPolygonOnly = True
        # For polygons, boundary obstacle prevents label suppression across adjacent areas
        poly_boundary = resolve_qgis_enum(QgsLabelObstacleSettings, "ObstacleType", "PolygonBoundary")
        if poly_boundary is not None:
            settings.obstacleSettings().setType(poly_boundary)

    # Scale-aware visibility heuristics to prevent massive label clouds
    fc = layer.featureCount() if hasattr(layer, "featureCount") else 0
    if isinstance(fc, (int, float)) and fc > 500:
        settings.scaleVisibility = True
        settings.minimumScale = 150000

    if expression:
        settings.fieldName = expression
        settings.isExpression = True
    else:
        settings.fieldName = target_field
        settings.isExpression = False

    layer.setLabeling(QgsVectorLayerSimpleLabeling(settings))
    layer.setLabelsEnabled(True)
    layer.triggerRepaint()

    return {
        "success": True,
        "message": f"Labels applied to '{layer_name}' using {label_source} (halo enabled, priority={priority}).",
    }


@register_tool("clip_layer", "Clip vector layer by mask layer.", {"type": "object", "properties": {"input_layer": {"type": "string"}, "mask_layer": {"type": "string"}}, "required": ["input_layer", "mask_layer"]})
def clip_layer(input_layer, mask_layer):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    a = _find_layer_by_name(input_layer)
    b = _find_layer_by_name(mask_layer)
    if a is None:
        return {"error": f"Layer '{input_layer}' not found"}
    if b is None:
        return {"error": f"Layer '{mask_layer}' not found"}

    crs_info = verify_crs_compatibility(input_layer, mask_layer)
    res = _run_and_add(
        "native:clip",
        {"INPUT": a, "OVERLAY": b, "OUTPUT": "memory:"},
        f"{input_layer}_clipped",
    )
    if isinstance(res, dict) and crs_info.get("warning"):
        res["crs_warning"] = crs_info["warning"]
    return res


@register_tool("intersect_layers", "Intersection of two vector layers.", {"type": "object", "properties": {"layer1": {"type": "string"}, "layer2": {"type": "string"}}, "required": ["layer1", "layer2"]})
def intersect_layers(layer1, layer2):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    a = _find_layer_by_name(layer1)
    b = _find_layer_by_name(layer2)
    if a is None:
        return {"error": f"Layer '{layer1}' not found"}
    if b is None:
        return {"error": f"Layer '{layer2}' not found"}

    crs_info = verify_crs_compatibility(layer1, layer2)
    res = _run_and_add(
        "native:intersection",
        {"INPUT": a, "OVERLAY": b, "OUTPUT": "memory:"},
        f"{layer1}_intersect_{layer2}",
    )
    if isinstance(res, dict) and crs_info.get("warning"):
        res["crs_warning"] = crs_info["warning"]
    return res


@register_tool("union_layers", "Geometric union of two vector layers.", {"type": "object", "properties": {"layer1": {"type": "string"}, "layer2": {"type": "string"}}, "required": ["layer1", "layer2"]})
def union_layers(layer1, layer2):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    a = _find_layer_by_name(layer1)
    b = _find_layer_by_name(layer2)
    if a is None:
        return {"error": f"Layer '{layer1}' not found"}
    if b is None:
        return {"error": f"Layer '{layer2}' not found"}

    crs_info = verify_crs_compatibility(layer1, layer2)
    res = _run_and_add(
        "native:union",
        {"INPUT": a, "OVERLAY": b, "OUTPUT": "memory:"},
        f"{layer1}_union_{layer2}",
    )
    if isinstance(res, dict) and crs_info.get("warning"):
        res["crs_warning"] = crs_info["warning"]
    return res


@register_tool(
    "difference_layers",
    "Subtract one vector layer from another (A minus B) -- e.g. 'everything outside the flood "
    "zone'. Set symmetric=true for a symmetric difference (everything in A or B but not in both) "
    "instead.",
    {
        "type": "object",
        "properties": {
            "input_layer": {"type": "string", "description": "Layer to subtract from (A)."},
            "overlay_layer": {"type": "string", "description": "Layer to subtract (B)."},
            "symmetric": {"type": "boolean", "description": "True for symmetric difference. Defaults to false."},
        },
        "required": ["input_layer", "overlay_layer"],
    },
)
def difference_layers(input_layer, overlay_layer, symmetric=False):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    a = _find_layer_by_name(input_layer)
    b = _find_layer_by_name(overlay_layer)
    if a is None:
        return {"error": f"Layer '{input_layer}' not found"}
    if b is None:
        return {"error": f"Layer '{overlay_layer}' not found"}

    crs_info = verify_crs_compatibility(input_layer, overlay_layer)
    alg = "native:symmetricaldifference" if symmetric else "native:difference"
    suffix = "symdiff" if symmetric else "diff"
    res = _run_and_add(
        alg,
        {"INPUT": a, "OVERLAY": b, "OUTPUT": "memory:"},
        f"{input_layer}_{suffix}_{overlay_layer}",
    )
    if isinstance(res, dict) and crs_info.get("warning"):
        res["crs_warning"] = crs_info["warning"]
    return res


@register_tool(
    "convex_hull",
    "Generate the convex hull polygon(s) enclosing a layer's features -- the smallest convex "
    "polygon containing all of them. Useful for catchment/coverage-area style analysis (e.g. the "
    "outer boundary of a set of service points).",
    {"type": "object", "properties": {"layer_name": {"type": "string"}}, "required": ["layer_name"]},
)
def convex_hull(layer_name):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    layer = _find_layer_by_name(layer_name)
    if layer is None:
        return {"error": f"Layer '{layer_name}' not found"}
    return _run_and_add(
        "native:convexhull",
        {"INPUT": layer, "OUTPUT": "memory:"},
        f"{layer_name}_convex_hull",
    )


@register_tool(
    "voronoi_polygons",
    "Generate Voronoi polygons (Thiessen polygons) from a point layer -- each polygon covers the "
    "area closest to its point. Common for coverage/catchment analysis (e.g. 'which points are "
    "closest to each facility').",
    {
        "type": "object",
        "properties": {
            "layer_name": {"type": "string"},
            "buffer_percent": {"type": "number", "description": "Extends the diagram past the point extent by this percentage, to avoid clipped edge polygons. Defaults to 0."},
        },
        "required": ["layer_name"],
    },
)
def voronoi_polygons(layer_name, buffer_percent=0):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    layer = _find_layer_by_name(layer_name)
    if layer is None:
        return {"error": f"Layer '{layer_name}' not found"}
    if layer.geometryType() != QgsWkbTypes.GeometryType.PointGeometry:
        return {"error": "voronoi_polygons only supports point layers."}
    return _run_and_add(
        "native:voronoipolygons",
        {"INPUT": layer, "BUFFER": buffer_percent, "OUTPUT": "memory:"},
        f"{layer_name}_voronoi",
    )


@register_tool(
    "delaunay_triangulation",
    "Generate a Delaunay triangulation from a point layer -- a mesh of non-overlapping triangles "
    "connecting the points, useful as a basis for terrain interpolation or network-like proximity "
    "analysis.",
    {"type": "object", "properties": {"layer_name": {"type": "string"}}, "required": ["layer_name"]},
)
def delaunay_triangulation(layer_name):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    layer = _find_layer_by_name(layer_name)
    if layer is None:
        return {"error": f"Layer '{layer_name}' not found"}
    if layer.geometryType() != QgsWkbTypes.GeometryType.PointGeometry:
        return {"error": "delaunay_triangulation only supports point layers."}
    return _run_and_add(
        "native:delaunaytriangulation",
        {"INPUT": layer, "OUTPUT": "memory:"},
        f"{layer_name}_delaunay",
    )


@register_tool(
    "find_nearest_features",
    "For each feature in input_layer, find the nearest feature(s) in near_layer and join it "
    "(distance in meters, plus the nearest feature's attributes) -- e.g. 'nearest hospital to "
    "each village'. Creates a new layer; input_layer and near_layer are unchanged.",
    {
        "type": "object",
        "properties": {
            "input_layer": {"type": "string", "description": "Layer whose features get a nearest-match added, e.g. villages."},
            "near_layer": {"type": "string", "description": "Layer to search for the nearest feature in, e.g. hospitals."},
            "neighbors": {"type": "integer", "description": "How many nearest matches per feature. Defaults to 1."},
        },
        "required": ["input_layer", "near_layer"],
    },
)
def find_nearest_features(input_layer, near_layer, neighbors=1):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    if neighbors < 1:
        return {"error": "neighbors must be at least 1."}
    a = _find_layer_by_name(input_layer)
    b = _find_layer_by_name(near_layer)
    if a is None:
        return {"error": f"Layer '{input_layer}' not found"}
    if b is None:
        return {"error": f"Layer '{near_layer}' not found"}

    crs_info = verify_crs_compatibility(input_layer, near_layer)
    res = _run_and_add(
        "native:joinbynearest",
        {
            "INPUT": a,
            "INPUT_2": b,
            "FIELDS_TO_COPY": [],
            "NEIGHBORS": neighbors,
            "MAX_DISTANCE": None,
            "OUTPUT": "memory:",
        },
        f"{input_layer}_nearest_{near_layer}",
    )
    if isinstance(res, dict) and crs_info.get("warning"):
        res["crs_warning"] = crs_info["warning"]
    return res


@register_tool(
    "convert_to_singlepart",
    "Split multipart geometries (e.g. a MultiPolygon feature representing several separate "
    "islands) into one single-part feature per part. Useful cleanup before per-feature analysis "
    "like calculate_area or centroid, which otherwise treat all parts as one feature.",
    {"type": "object", "properties": {"layer_name": {"type": "string"}}, "required": ["layer_name"]},
)
def convert_to_singlepart(layer_name):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    layer = _find_layer_by_name(layer_name)
    if layer is None:
        return {"error": f"Layer '{layer_name}' not found"}
    return _run_and_add(
        "native:multiparttosingleparts",
        {"INPUT": layer, "OUTPUT": "memory:"},
        f"{layer_name}_singlepart",
    )


@register_tool(
    "simplify_geometry",
    "Simplify (generalize) a layer's geometries by removing vertices within tolerance of a "
    "straight line -- reduces file size/complexity for display at smaller scales or for web "
    "export. Larger tolerance means more simplification.",
    {
        "type": "object",
        "properties": {
            "layer_name": {"type": "string"},
            "tolerance": {"type": "number", "description": "Simplification tolerance in the layer's map units."},
        },
        "required": ["layer_name", "tolerance"],
    },
)
def simplify_geometry(layer_name, tolerance):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    if tolerance <= 0:
        return {"error": "tolerance must be positive."}
    layer = _find_layer_by_name(layer_name)
    if layer is None:
        return {"error": f"Layer '{layer_name}' not found"}
    return _run_and_add(
        "native:simplifygeometries",
        {"INPUT": layer, "METHOD": 0, "TOLERANCE": tolerance, "OUTPUT": "memory:"},
        f"{layer_name}_simplified",
    )


_STATS_KEYS = ("count", "sum", "mean", "median", "min", "max", "stdev", "range")


def _compute_field_statistics(values):
    """Pure Python, no QGIS needed -- takes a plain list of numbers (already
    extracted from a layer's features) and returns the same summary stats
    QgsStatisticalSummary would, so this logic is directly unit-testable."""
    if not values:
        return None
    n = len(values)
    total = sum(values)
    mean = total / n
    sorted_vals = sorted(values)
    mid = n // 2
    median = sorted_vals[mid] if n % 2 else (sorted_vals[mid - 1] + sorted_vals[mid]) / 2
    variance = sum((x - mean) ** 2 for x in values) / n
    return {
        "count": n,
        "sum": total,
        "mean": mean,
        "median": median,
        "min": sorted_vals[0],
        "max": sorted_vals[-1],
        "stdev": variance ** 0.5,
        "range": sorted_vals[-1] - sorted_vals[0],
    }


@register_tool(
    "field_statistics",
    "Compute summary statistics (count, sum, mean, median, min, max, stdev, range) for a numeric "
    "field across every feature in a layer -- a flat project-wide summary, not per-zone (use "
    "zonal_statistics for that).",
    {
        "type": "object",
        "properties": {
            "layer_name": {"type": "string"},
            "field": {"type": "string"},
        },
        "required": ["layer_name", "field"],
    },
)
def field_statistics(layer_name, field):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    layer = _find_layer_by_name(layer_name)
    if layer is None:
        return {"error": f"Layer '{layer_name}' not found"}
    if field not in [f.name() for f in layer.fields()]:
        return {"error": f"Field '{field}' not found in '{layer_name}'"}

    values = [float(feat[field]) for feat in layer.getFeatures() if isinstance(feat[field], (int, float))]
    stats = _compute_field_statistics(values)
    if stats is None:
        return {"error": f"No numeric values found in field '{field}'."}
    stats["success"] = True
    stats["layer_name"] = layer_name
    stats["field"] = field
    return stats


_SELECT_PREDICATES = {
    "intersects": 0, "contains": 1, "equals": 3, "touches": 4,
    "overlaps": 5, "within": 6, "crosses": 7,
}
_SELECT_METHODS = {"new": 0, "add": 1, "remove": 2, "intersect": 3}


@register_tool(
    "select_by_location",
    "Select features in target_layer based on their spatial relationship to reference_layer "
    "(e.g. select all points within a polygon boundary). Use method to combine with an existing "
    "selection instead of replacing it (e.g. 'add' after a select_by_attribute call to build up a "
    "combined selection, or 'intersect' to narrow one down).",
    {
        "type": "object",
        "properties": {
            "target_layer": {"type": "string", "description": "Layer whose features get selected."},
            "reference_layer": {"type": "string", "description": "Layer to test spatial relationship against."},
            "predicate": {
                "type": "string",
                "description": "Spatial relationship: 'intersects' (default), 'contains', 'within', 'touches', 'overlaps', 'crosses', 'equals'.",
            },
            "method": {
                "type": "string",
                "description": "'new' (default, replaces current selection), 'add', 'remove', or 'intersect' with the current selection.",
            },
        },
        "required": ["target_layer", "reference_layer"],
    },
)
def select_by_location(target_layer, reference_layer, predicate="intersects", method="new"):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    predicate_val = _SELECT_PREDICATES.get((predicate or "intersects").lower())
    if predicate_val is None:
        return {"error": f"Unknown predicate '{predicate}'. Use one of: {list(_SELECT_PREDICATES)}"}
    method_val = _SELECT_METHODS.get((method or "new").lower())
    if method_val is None:
        return {"error": f"Unknown method '{method}'. Use one of: {list(_SELECT_METHODS)}"}

    a = _find_layer_by_name(target_layer)
    b = _find_layer_by_name(reference_layer)
    if a is None:
        return {"error": f"Layer '{target_layer}' not found"}
    if b is None:
        return {"error": f"Layer '{reference_layer}' not found"}

    try:
        processing.run(
            "native:selectbylocation",
            {"INPUT": a, "PREDICATE": [predicate_val], "INTERSECT": b, "METHOD": method_val},
        )
        return {"success": True, "layer_name": target_layer, "selected_count": a.selectedFeatureCount()}
    except Exception as e:
        return {"error": f"select_by_location failed: {e}"}


@register_tool(
    "invert_selection",
    "Invert the current feature selection on a layer -- previously unselected features become "
    "selected and vice versa.",
    {"type": "object", "properties": {"layer_name": {"type": "string"}}, "required": ["layer_name"]},
)
def invert_selection(layer_name):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    layer = _find_layer_by_name(layer_name)
    if layer is None:
        return {"error": f"Layer '{layer_name}' not found"}
    try:
        layer.invertSelection()
        return {"success": True, "layer_name": layer_name, "selected_count": layer.selectedFeatureCount()}
    except Exception as e:
        return {"error": f"invert_selection failed: {e}"}


@register_tool("dissolve_layer", "Dissolve vector features optionally grouped by field.", {"type": "object", "properties": {"layer_name": {"type": "string"}, "field": {"type": "string"}}, "required": ["layer_name"]})
def dissolve_layer(layer_name, field=None):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    layer = _find_layer_by_name(layer_name)
    if layer is None:
        return {"error": f"Layer '{layer_name}' not found"}
    params = {
        "INPUT": layer,
        "FIELD": [field] if field else [],
        "OUTPUT": "memory:",
    }
    return _run_and_add("native:dissolve", params, f"{layer_name}_dissolved")


@register_tool("merge_layers", "Merge multiple vector layers into one.", {"type": "object", "properties": {"layer_names_list": {"type": "array", "items": {"type": "string"}}}, "required": ["layer_names_list"]})
def merge_layers(layer_names_list):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    if not isinstance(layer_names_list, list) or len(layer_names_list) < 2:
        return {"error": "Provide a list of at least 2 layer names"}
    layers = []
    for name in layer_names_list:
        layer = _find_layer_by_name(name)
        if layer is None:
            return {"error": f"Layer '{name}' not found"}
        layers.append(layer)
    return _run_and_add(
        "native:mergevectorlayers",
        {"LAYERS": layers, "OUTPUT": "memory:"},
        "merged_layer",
    )


@register_tool("spatial_join", "Join attributes from one layer to another by spatial location.", {"type": "object", "properties": {"target_layer": {"type": "string"}, "join_layer": {"type": "string"}}, "required": ["target_layer", "join_layer"]})
def spatial_join(target_layer, join_layer):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    a = _find_layer_by_name(target_layer)
    b = _find_layer_by_name(join_layer)
    if a is None:
        return {"error": f"Layer '{target_layer}' not found"}
    if b is None:
        return {"error": f"Layer '{join_layer}' not found"}

    crs_info = verify_crs_compatibility(target_layer, join_layer)
    res = _run_and_add(
        "native:joinattributesbylocation",
        {
            "INPUT": a,
            "JOIN": b,
            "PREDICATE": [0],
            "JOIN_FIELDS": [],
            "METHOD": 1,
            "DISCARD_NONMATCHING": False,
            "PREFIX": "",
            "OUTPUT": "memory:",
        },
        f"{target_layer}_joined",
    )
    if isinstance(res, dict) and crs_info.get("warning"):
        res["crs_warning"] = crs_info["warning"]
    return res


@register_tool(
    "join_by_attribute",
    "Join attributes from one layer to another by a shared field value (not location -- use "
    "spatial_join for that). If target_field/join_field are omitted, suggests fuzzy-matched "
    "candidate field pairs instead of running the join -- call again with the fields once you've "
    "picked one. Warns if the join field isn't unique on the join layer, since that duplicates "
    "features on the target side (1-to-many) rather than a clean 1-to-1 join.",
    {
        "type": "object",
        "properties": {
            "target_layer": {"type": "string"},
            "join_layer": {"type": "string"},
            "target_field": {"type": "string", "description": "Field on target_layer to join on. Omit to get fuzzy-matched suggestions."},
            "join_field": {"type": "string", "description": "Field on join_layer to join on. Omit to get fuzzy-matched suggestions."},
        },
        "required": ["target_layer", "join_layer"],
    },
)
def join_by_attribute(target_layer, join_layer, target_field=None, join_field=None):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    a = _find_layer_by_name(target_layer)
    b = _find_layer_by_name(join_layer)
    if a is None:
        return {"error": f"Layer '{target_layer}' not found"}
    if b is None:
        return {"error": f"Layer '{join_layer}' not found"}

    target_fields = [f.name() for f in a.fields()]
    join_fields = [f.name() for f in b.fields()]

    if not target_field or not join_field:
        suggestions = []
        for tf in target_fields:
            matches = difflib.get_close_matches(tf, join_fields, n=1, cutoff=0.6)
            if matches:
                suggestions.append({"target_field": tf, "join_field": matches[0]})
        if not suggestions:
            return {
                "error": "No target_field/join_field specified and no confident fuzzy match found "
                f"between fields. Target layer fields: {target_fields}. Join layer fields: {join_fields}. "
                "Specify target_field and join_field explicitly."
            }
        return {
            "status": "FIELD_SUGGESTION",
            "message": "No join fields specified -- here are fuzzy-matched candidates. Call again "
            "with target_field/join_field set to run the join.",
            "suggestions": suggestions,
        }

    if target_field not in target_fields:
        return {"error": f"Field '{target_field}' not found on '{target_layer}'. Available: {target_fields}"}
    if join_field not in join_fields:
        return {"error": f"Field '{join_field}' not found on '{join_layer}'. Available: {join_fields}"}

    # Cardinality check: if the join field isn't unique on the join-layer side, the join will
    # duplicate features on the target side -- warn rather than silently producing surprise duplicates.
    cardinality_warning = None
    try:
        join_idx = b.fields().indexOf(join_field)
        total_features = b.featureCount()
        unique_count = len(b.uniqueValues(join_idx))
        if total_features > 0 and unique_count < total_features:
            cardinality_warning = (
                f"Join field '{join_field}' on '{join_layer}' is not unique ({unique_count} unique "
                f"values across {total_features} features) -- this join may duplicate features on "
                f"'{target_layer}' (1-to-many), not a clean 1-to-1 join."
            )
    except Exception:  # nosec B110 (best-effort: failure is non-fatal)
        pass  # best-effort; don't block the join if the cardinality check itself fails

    res = _run_and_add(
        "native:joinattributestable",
        {
            "INPUT": a,
            "FIELD": target_field,
            "INPUT_2": b,
            "FIELD_2": join_field,
            "FIELDS_TO_COPY": [],
            "METHOD": 1,
            "DISCARD_NONMATCHING": False,
            "PREFIX": "",
            "OUTPUT": "memory:",
        },
        f"{target_layer}_attrjoined",
    )
    if isinstance(res, dict) and cardinality_warning:
        res["cardinality_warning"] = cardinality_warning
    return res


def _add_calculated_field(layer, field_name, expression_text=None, value_fn=None):
    """Writes a numeric field on `layer`, from a QGIS expression or from `value_fn(feature)`.

    GitHub #143 / #144 (audit F07, F08): the first version started and committed its own edit session even on a layer the user
    was already editing (committing their unrelated edits, or rolling them back on an error), added the field straight to the
    provider, and ignored the result of every write, so a malformed expression wrote NULLs and a read-only layer "succeeded".
    Now: the expression is parsed and prepared BEFORE anything changes; an evaluation error aborts the whole write; every call
    is checked; the changes are one edit command (see _edit_session.py); a layer the user already has in edit mode keeps its
    session and the result says the values are unsaved."""
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    if layer is None:
        return {"error": "Layer is None"}
    from ._edit_session import EditError, add_numeric_field, edit_command, set_value
    try:
        expression = None
        context = None
        if value_fn is None:
            expression = QgsExpression(expression_text)
            if expression.hasParserError():
                return {"error": f"Invalid expression: {expression.parserErrorString()}"}
            context = layer.createExpressionContext()
            if not expression.prepare(context) or expression.hasEvalError():
                return {"error": f"Expression cannot be used on this layer: {expression.evalErrorString()}"}

        written = 0
        with edit_command(layer, "Cartogen AI: write field " + field_name) as owned:
            field_idx = add_numeric_field(layer, field_name)
            for feature in layer.getFeatures():
                if value_fn is not None:
                    value = value_fn(feature)
                else:
                    context.setFeature(feature)
                    value = expression.evaluate(context)
                    if expression.hasEvalError():
                        raise EditError(f"the expression failed on feature {feature.id()}: {expression.evalErrorString()}")
                set_value(layer, feature.id(), field_idx, value)
                written += 1
        result = {"success": True, "layer_name": layer.name(), "field": field_name, "features_updated": written}
        if not owned:
            result["note"] = ("The layer is already in edit mode, so the new values are in your edit session and are NOT "
                              "saved: save or discard the layer edits yourself.")
        return result
    except EditError as e:
        return {"error": f"Field calculation failed, nothing was changed: {e}"}
    except Exception as e:
        return {"error": f"Field calculation failed: {e}"}


def _si_measure_fn(layer, kind):
    """value_fn(feature) -> the feature's area in square metres ('area') or length in metres ('length'), measured on the
    project ellipsoid and converted explicitly. The old `$area` / `$length` expressions follow the PROJECT's measurement unit
    settings, so a project set to km2 wrote 1.23 into a field named area_sqm for a 1,230,907 m2 polygon (audit F05, #141)."""
    from qgis.core import Qgis, QgsDistanceArea
    da = QgsDistanceArea()
    da.setSourceCrs(layer.crs(), QgsProject.instance().transformContext())
    ellipsoid = QgsProject.instance().ellipsoid()
    da.setEllipsoid(ellipsoid if ellipsoid and ellipsoid != "NONE" else "WGS84")

    def area(feature):
        geom = feature.geometry()
        if geom is None or geom.isEmpty():
            return None
        return da.convertAreaMeasurement(da.measureArea(geom), Qgis.AreaUnit.SquareMeters)

    def length(feature):
        geom = feature.geometry()
        if geom is None or geom.isEmpty():
            return None
        return da.convertLengthMeasurement(da.measureLength(geom), Qgis.DistanceUnit.Meters)

    return area if kind == "area" else length


@register_tool("calculate_area", "Calculate polygon area in square meters and write it into a new "
    "'area_sqm' field on the layer. Destructive action requiring UI confirmation -- same underlying "
    "operation as field_calculator (in-place attribute mutation on the live layer).",
    {"type": "object", "properties": {"layer_name": {"type": "string"}}, "required": ["layer_name"]})
def calculate_area(layer_name, confirmed: bool = False):
    # docs/archive/DESTRUCTIVE_TOOLS_AUDIT_2026-08-21.md: this calls the exact same
    # _add_calculated_field primitive as field_calculator (layer.startEditing()
    # / changeAttributeValue() / commitChanges() on the live, already-loaded
    # layer) -- field_calculator gates that operation behind confirmation, so
    # this must too for the two to be consistent, per prompts.py rule 9's own
    # stated invariant ("attribute mutations ... require user confirmation").
    if not confirmed:
        return {
            "status": "PREVIEW_REQUIRED",
            "requires_confirmation": True,
            "is_destructive": True,
            "tool_name": "calculate_area",
            "arguments": {"layer_name": layer_name, "confirmed": True},
            "code_snippet": "layer.startEditing()\n# Add/update field 'area_sqm' = ellipsoidal area in square metres across features\nlayer.commitChanges()",
            "rationale": f"Data Mutation Preview: Add/update field 'area_sqm' on layer '{layer_name}' with each feature's area.",
            "message": f"Confirmation required before mutating attribute field 'area_sqm' on '{layer_name}'.",
        }
    layer = _find_layer_by_name(layer_name)
    if layer is None:
        return {"error": f"Layer '{layer_name}' not found"}
    return _add_calculated_field(layer, "area_sqm", value_fn=_si_measure_fn(layer, "area"))


@register_tool("calculate_length", "Calculate line length in meters and write it into a new "
    "'length_m' field on the layer. Destructive action requiring UI confirmation -- same underlying "
    "operation as field_calculator (in-place attribute mutation on the live layer).",
    {"type": "object", "properties": {"layer_name": {"type": "string"}}, "required": ["layer_name"]})
def calculate_length(layer_name, confirmed: bool = False):
    if not confirmed:
        return {
            "status": "PREVIEW_REQUIRED",
            "requires_confirmation": True,
            "is_destructive": True,
            "tool_name": "calculate_length",
            "arguments": {"layer_name": layer_name, "confirmed": True},
            "code_snippet": "layer.startEditing()\n# Add/update field 'length_m' = ellipsoidal length in metres across features\nlayer.commitChanges()",
            "rationale": f"Data Mutation Preview: Add/update field 'length_m' on layer '{layer_name}' with each feature's length.",
            "message": f"Confirmation required before mutating attribute field 'length_m' on '{layer_name}'.",
        }
    layer = _find_layer_by_name(layer_name)
    if layer is None:
        return {"error": f"Layer '{layer_name}' not found"}
    return _add_calculated_field(layer, "length_m", value_fn=_si_measure_fn(layer, "length"))


@register_tool("centroid", "Generate centroid points for polygon layer.", {"type": "object", "properties": {"layer_name": {"type": "string"}}, "required": ["layer_name"]})
def centroid(layer_name):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    layer = _find_layer_by_name(layer_name)
    if layer is None:
        return {"error": f"Layer '{layer_name}' not found"}
    return _run_and_add(
        "native:centroids",
        {"INPUT": layer, "ALL_PARTS": False, "OUTPUT": "memory:"},
        f"{layer_name}_centroids",
    )


@register_tool("reproject_layer", "Reproject layer to target CRS code (e.g. 'EPSG:4326').", {"type": "object", "properties": {"layer_name": {"type": "string"}, "crs_code": {"type": "string"}}, "required": ["layer_name", "crs_code"]})
def reproject_layer(layer_name, crs_code):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    layer = _find_layer_by_name(layer_name)
    if layer is None:
        return {"error": f"Layer '{layer_name}' not found"}
    target_crs = QgsCoordinateReferenceSystem(crs_code)
    if not target_crs.isValid():
        return {"error": f"Invalid CRS: '{crs_code}'"}
    return _run_and_add(
        "native:reprojectlayer",
        {"INPUT": layer, "TARGET_CRS": target_crs, "OUTPUT": "memory:"},
        f"{layer_name}_{crs_code.replace(':', '_')}",
    )


@register_tool("fix_geometries", "Fix invalid geometries in vector layer.", {"type": "object", "properties": {"layer_name": {"type": "string"}}, "required": ["layer_name"]})
def fix_geometries(layer_name):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    layer = _find_layer_by_name(layer_name)
    if layer is None:
        return {"error": f"Layer '{layer_name}' not found"}
    return _run_and_add(
        "native:fixgeometries",
        {"INPUT": layer, "OUTPUT": "memory:"},
        f"{layer_name}_fixed",
    )


@register_tool("select_by_attribute", "Select features matching specific field value.", {"type": "object", "properties": {"layer_name": {"type": "string"}, "field": {"type": "string"}, "value": {"type": "string"}}, "required": ["layer_name", "field", "value"]})
def select_by_attribute(layer_name, field, value):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    layer = _find_layer_by_name(layer_name)
    if layer is None:
        return {"error": f"Layer '{layer_name}' not found"}
    if field not in [f.name() for f in layer.fields()]:
        return {"error": f"Field '{field}' not found in '{layer_name}'"}

    col_quoted = QgsExpression.quotedColumnRef(field)
    val_quoted = QgsExpression.quotedValue(value)
    expr = f"{col_quoted} = {val_quoted}"
    layer.selectByExpression(expr)
    return {"success": True, "count": layer.selectedFeatureCount(), "layer_name": layer_name, "expression": expr}


@register_tool("field_calculator", "Calculate or add field using QGIS expression. Destructive action requiring UI confirmation.", {"type": "object", "properties": {"layer_name": {"type": "string"}, "new_field": {"type": "string"}, "expression": {"type": "string"}}, "required": ["layer_name", "new_field", "expression"]})
def field_calculator(layer_name, new_field, expression, confirmed: bool = False):
    if not confirmed:
        return {
            "status": "PREVIEW_REQUIRED",
            "requires_confirmation": True,
            "is_destructive": True,
            "tool_name": "field_calculator",
            "arguments": {"layer_name": layer_name, "new_field": new_field, "expression": expression, "confirmed": True},
            "code_snippet": f"layer.startEditing()\nfield_idx = layer.fields().indexOf('{new_field}')\n# Calculate expression '{expression}' across features\nlayer.commitChanges()",
            "rationale": f"Data Mutation Preview: Add/update field '{new_field}' on layer '{layer_name}' using expression '{expression}'.",
            "message": f"Confirmation required before mutating attribute field '{new_field}' on '{layer_name}'."
        }

    layer = _find_layer_by_name(layer_name)
    if layer is None:
        return {"error": f"Layer '{layer_name}' not found"}

    return _add_calculated_field(layer, new_field, expression)


@register_tool("get_feature_count", "Get total feature count in a layer.", {"type": "object", "properties": {"layer_name": {"type": "string"}}, "required": ["layer_name"]})
def get_feature_count(layer_name):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    layer = _find_layer_by_name(layer_name)
    if layer is None:
        return {"error": f"Layer '{layer_name}' not found"}
    return {"layer_name": layer_name, "feature_count": layer.featureCount()}


@register_tool("open_attribute_table", "Open attribute table GUI for layer.", {"type": "object", "properties": {"layer_name": {"type": "string"}}, "required": ["layer_name"]})
def open_attribute_table(layer_name):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    if iface is None:
        return {"error": "QGIS interface not available"}
    layer = _find_layer_by_name(layer_name)
    if layer is None:
        return {"error": f"Layer '{layer_name}' not found"}
    iface.showAttributeTable(layer)
    return {"success": True, "layer_name": layer_name}


@register_tool(
    "zoom_to_feature",
    "Zoom map canvas to a single feature, identified either by feature_id or by an "
    "attribute expression (e.g. \"governorate_name = 'Ma\\'rib'\"). Use expression when "
    "the feature_id isn't already known -- this looks it up and zooms in one call, "
    "instead of hand-writing PyQGIS to query for it first.",
    {
        "type": "object",
        "properties": {
            "layer_name": {"type": "string"},
            "feature_id": {"type": "integer", "description": "Feature ID to zoom to. Provide this or expression, not both."},
            "expression": {"type": "string", "description": "QGIS expression selecting exactly one feature by attribute, e.g. \"name = 'Ma\\'rib'\". Provide this or feature_id, not both."},
        },
        "required": ["layer_name"],
    },
)
def zoom_to_feature(layer_name, feature_id=None, expression=None):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    if iface is None:
        return {"error": "QGIS interface not available"}
    layer = _find_layer_by_name(layer_name)
    if layer is None:
        return {"error": f"Layer '{layer_name}' not found"}

    if feature_id is None and not expression:
        return {"error": "Provide either feature_id or expression."}
    if feature_id is not None and expression:
        return {"error": "Provide only one of feature_id or expression, not both."}

    if expression:
        expr = QgsExpression(expression)
        if expr.hasParserError():
            return {"error": f"Invalid expression: {expr.parserErrorString()}"}
        matches = list(layer.getFeatures(QgsFeatureRequest(expr)))
        if not matches:
            return {"error": f"No feature in '{layer_name}' matches expression: {expression}"}
        if len(matches) > 1:
            return {"error": f"Expression matched {len(matches)} features in '{layer_name}' -- expected exactly one. Narrow the expression or use feature_id."}
        feature = matches[0]
        fid = feature.id()
    else:
        try:
            fid = int(feature_id)
        except (TypeError, ValueError):
            return {"error": f"feature_id must be an integer, got {feature_id!r}"}
        feature = layer.getFeature(fid)
        if not feature.isValid():
            return {"error": f"Feature id {fid} not found in '{layer_name}'"}

    geom = feature.geometry()
    if geom is None or geom.isEmpty():
        return {"error": "Feature has no geometry"}
    canvas = iface.mapCanvas()
    extent = _extent_to_canvas_crs(canvas, geom.boundingBox(), layer.crs())
    if extent is None:
        return {"error": f"Could not transform the feature from {layer.crs().authid()} into the map CRS, so the view was not changed."}
    canvas.setExtent(extent)
    canvas.refresh()
    layer.selectByIds([fid])
    return {"success": True, "layer_name": layer_name, "feature_id": fid}


@register_tool("get_crs", "Get CRS authid, description, and units for layer.", {"type": "object", "properties": {"layer_name": {"type": "string"}}, "required": ["layer_name"]})
def get_crs(layer_name):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    layer = _find_layer_by_name(layer_name)
    if layer is None:
        return {"error": f"Layer '{layer_name}' not found"}
    crs = layer.crs()
    return {
        "layer_name": layer_name,
        "authid": crs.authid(),
        "description": crs.description(),
        "is_geographic": crs.isGeographic(),
        "units": crs.mapUnits(),
    }


@register_tool(
    "diagnose_topology",
    "Diagnose self-intersections, slivers, exact-duplicate geometries, and (for polygon layers) "
    "overlapping features in a vector layer. Pass min_area to also flag polygons smaller than a "
    "given threshold (in the layer's CRS units squared) as small_polygons, distinct from exact "
    "zero-area slivers. Does NOT check for gaps between polygons meant to tile an area (e.g. "
    "missing coverage inside an admin boundary) -- that needs a reference boundary to diff "
    "against that this tool has no way to infer, and a heuristic based on dissolving the layer "
    "and looking for interior holes would misfire as a false gap on almost any real humanitarian "
    "admin-boundary layer (a coastline, an unmapped buffer zone, a deliberately excluded area are "
    "all real holes, not QA failures) -- that remains open, see point 4 of "
    "docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md.",
    {
        "type": "object",
        "properties": {
            "layer_name": {"type": "string"},
            "min_area": {
                "type": "number",
                "description": "Optional. Flags polygons with 0 < area < min_area (in the layer's CRS units squared) as small_polygons, separate from exact zero-area slivers.",
            },
        },
        "required": ["layer_name"],
    },
)
def diagnose_topology(layer_name, min_area=None):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    layer = _find_layer_by_name(layer_name)
    if layer is None:
        return {"error": f"Layer '{layer_name}' not found"}

    is_polygon = QgsWkbTypes.geometryType(layer.wkbType()) == QgsWkbTypes.GeometryType.PolygonGeometry

    invalid_count = 0
    zero_area_count = 0
    small_polygon_count = 0
    total_count = layer.featureCount()
    wkt_to_fids = {}
    polygon_geoms_by_fid = {}

    for feature in layer.getFeatures():
        geom = feature.geometry()
        if geom is None or geom.isEmpty():
            invalid_count += 1
            continue
        if not geom.isGeomValid():
            invalid_count += 1
        if geom.type() == 2 and geom.area() == 0:  # Polygon geometry with zero area
            zero_area_count += 1
        elif geom.type() == 2 and min_area is not None and 0 < geom.area() < min_area:
            small_polygon_count += 1

        wkt_to_fids.setdefault(geom.asWkt(), []).append(feature.id())
        if geom.type() == 2:
            polygon_geoms_by_fid[feature.id()] = geom

    # Duplicate geometries: exact WKT match across two or more features. Counts
    # every duplicate BEYOND the first in each group (3 identical features ->
    # 2 duplicates), not the number of groups.
    duplicate_count = sum(len(fids) - 1 for fids in wkt_to_fids.values() if len(fids) > 1)

    # Overlapping features: real area-sharing overlap (QgsGeometry.overlaps,
    # the same OGC predicate already surfaced as a select_by_location option),
    # not mere touching. Spatial-index bbox prefilter is the same
    # QgsSpatialIndex(layer.getFeatures()) + index.intersects(bbox) pattern
    # already used by obfuscate_sensitive_points's admin_unit_snap path in
    # this file -- .overlaps() itself is standard, long-stable GEOS-backed
    # QgsGeometry API, but unlike .intersects()/.contains() (already
    # exercised elsewhere in this file) it isn't independently exercised
    # elsewhere in this codebase, so flagging that plainly rather than
    # implying it's been proven the same way.
    overlapping_pairs = 0
    if is_polygon and polygon_geoms_by_fid:
        index = QgsSpatialIndex(layer.getFeatures())
        checked_pairs = set()
        for fid, geom in polygon_geoms_by_fid.items():
            for candidate_fid in index.intersects(geom.boundingBox()):
                if candidate_fid == fid:
                    continue
                pair_key = tuple(sorted((fid, candidate_fid)))
                if pair_key in checked_pairs:
                    continue
                checked_pairs.add(pair_key)
                candidate_geom = polygon_geoms_by_fid.get(candidate_fid)
                if candidate_geom is not None and geom.overlaps(candidate_geom):
                    overlapping_pairs += 1

    issues = []
    if invalid_count > 0:
        issues.append("Use fix_geometries tool to repair invalid geometries.")
    if zero_area_count > 0 or small_polygon_count > 0:
        issues.append("Review zero-area/small slivers -- fix_geometries does not remove these on its own.")
    if duplicate_count > 0:
        issues.append(f"{duplicate_count} duplicate geometr{'y' if duplicate_count == 1 else 'ies'} found -- consider a dissolve or manual dedup.")
    if overlapping_pairs > 0:
        issues.append(f"{overlapping_pairs} overlapping polygon pair(s) found -- review for digitizing errors.")

    result = {
        "success": True,
        "layer_name": layer_name,
        "total_features": total_count,
        "invalid_geometries": invalid_count,
        "zero_area_slivers": zero_area_count,
        "duplicate_geometries": duplicate_count,
        "recommendation": " ".join(issues) if issues else "Geometries are clean.",
    }
    if is_polygon:
        result["overlapping_feature_pairs"] = overlapping_pairs
    if min_area is not None:
        result["small_polygons"] = small_polygon_count
    return result


@register_tool("verify_crs_compatibility", "Check if two layers share compatible Coordinate Reference Systems.", {"type": "object", "properties": {"layer1": {"type": "string"}, "layer2": {"type": "string"}}, "required": ["layer1", "layer2"]})
def verify_crs_compatibility(layer1, layer2):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    a = _find_layer_by_name(layer1)
    b = _find_layer_by_name(layer2)
    if a is None:
        return {"error": f"Layer '{layer1}' not found"}
    if b is None:
        return {"error": f"Layer '{layer2}' not found"}

    crs_a = a.crs()
    crs_b = b.crs()
    match = (crs_a == crs_b)

    return {
        "success": True,
        "compatible": match,
        "layer1_crs": crs_a.authid(),
        "layer2_crs": crs_b.authid(),
        "units1": crs_a.mapUnits(),
        "units2": crs_b.mapUnits(),
        "warning": "" if match else f"CRS mismatch: '{layer1}' ({crs_a.authid()}) vs '{layer2}' ({crs_b.authid()}). Consider reproject_layer before spatial operations."
    }


def _uniform_disk_offset(radius, rng):
    """Returns a (dx, dy) offset uniformly distributed within a disk of the
    given radius. Uses sqrt(u) for the radius draw, not a bare uniform draw --
    a bare `uniform(0, radius)` radius paired with a uniform angle would
    concentrate points near the center, since area scales with r^2, not r.
    That's exactly backwards for a Do No Harm displacement, which needs to
    spread the true location out roughly evenly across the disk, not cluster
    the obfuscated point near where it actually was. rng is an injected
    random.Random instance so this is fully deterministic and testable."""
    if radius <= 0:
        return 0.0, 0.0
    angle = rng.uniform(0, 2 * math.pi)
    r = radius * math.sqrt(rng.random())
    return r * math.cos(angle), r * math.sin(angle)


def _grid_snap(x, y, cell_size):
    """Snaps (x, y) to the centroid of the cell_size x cell_size grid cell it
    falls in -- every point sharing a cell collapses to an identical output
    location, destroying individual-point linkage. Square, not hexagonal:
    achieves the same privacy effect without hex-coordinate math this
    codebase has no way to verify without a live QGIS session or an external
    geometry library (no shapely/H3 dependency anywhere in this codebase)."""
    cell_x = math.floor(x / cell_size)
    cell_y = math.floor(y / cell_size)
    return (cell_x + 0.5) * cell_size, (cell_y + 0.5) * cell_size


@register_tool(
    "obfuscate_sensitive_points",
    "Displace or aggregate sensitive point locations (e.g. GBV survivors, individual IDP "
    "households, protection incidents) before they're mapped, exported, or included in any "
    "report -- a Do No Harm safeguard, and increasingly an explicit donor/ECHO compliance "
    "requirement. Recommend this as a step before add_incident_point/add_point_layer output or "
    "export_layer involving protection-flagged data goes anywhere -- never apply it silently or "
    "automatically without the user choosing to. Three methods: 'jitter' (random displacement "
    "within radius; radius is in the LAYER'S OWN CRS UNITS, not meters -- for a geographic CRS "
    "like EPSG:4326 a radius intended as '500 meters' would actually mean 500 DEGREES and "
    "scatter points across the globe, so reproject to a projected CRS first if a specific "
    "real-world distance matters), 'grid_snap' (collapses every point sharing a grid cell to "
    "that cell's centroid -- the strongest protection of the three, since it destroys "
    "individual-point identity rather than just displacing it; cell_size is also in the layer's "
    "own CRS units), or 'admin_unit_snap' (moves each point to the centroid of the admin-boundary "
    "polygon it falls within, from a separate polygon layer). The method and its parameter are "
    "always included in the output so they're disclosable in any report alongside the map.",
    {
        "type": "object",
        "properties": {
            "layer_name": {"type": "string", "description": "Point layer with sensitive locations."},
            "method": {"type": "string", "description": "One of: 'jitter', 'grid_snap', 'admin_unit_snap'."},
            "radius": {"type": "number", "description": "Required for 'jitter': max displacement, in the layer's own CRS units."},
            "cell_size": {"type": "number", "description": "Required for 'grid_snap': grid cell size, in the layer's own CRS units."},
            "admin_layer_name": {"type": "string", "description": "Required for 'admin_unit_snap': polygon layer of admin units to snap to."},
            "output_layer_name": {"type": "string", "description": "Optional name for the new layer; defaults to '{layer_name}_obfuscated'."},
            "seed": {"type": "integer", "description": "Optional random seed for 'jitter', for reproducible output."},
        },
        "required": ["layer_name", "method"],
    },
)
def obfuscate_sensitive_points(layer_name, method, radius=None, cell_size=None, admin_layer_name=None, output_layer_name=None, seed=None):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}

    method = (method or "").lower()
    if method not in ("jitter", "grid_snap", "admin_unit_snap"):
        return {"error": "method must be one of: 'jitter', 'grid_snap', 'admin_unit_snap'."}

    layer = _find_layer_by_name(layer_name)
    if layer is None:
        return {"error": f"Layer '{layer_name}' not found"}
    if QgsWkbTypes.geometryType(layer.wkbType()) != QgsWkbTypes.GeometryType.PointGeometry:
        return {"error": f"'{layer_name}' is not a point layer -- obfuscate_sensitive_points only handles point geometries."}

    admin_layer = None
    if method == "jitter":
        if not radius or radius <= 0:
            return {"error": "radius (a positive number) is required for method='jitter'."}
    elif method == "grid_snap":
        if not cell_size or cell_size <= 0:
            return {"error": "cell_size (a positive number) is required for method='grid_snap'."}
    else:  # admin_unit_snap
        if not admin_layer_name:
            return {"error": "admin_layer_name is required for method='admin_unit_snap'."}
        admin_layer = _find_layer_by_name(admin_layer_name)
        if admin_layer is None:
            return {"error": f"Layer '{admin_layer_name}' not found"}
        if QgsWkbTypes.geometryType(admin_layer.wkbType()) != QgsWkbTypes.GeometryType.PolygonGeometry:
            return {"error": f"'{admin_layer_name}' is not a polygon layer."}

    out_name = output_layer_name or f"{layer_name}_obfuscated"
    crs = layer.crs().authid()
    new_layer = QgsVectorLayer(f"Point?crs={crs}", out_name, "memory")
    provider = new_layer.dataProvider()
    provider.addAttributes(layer.fields())
    new_layer.updateFields()

    index = None
    admin_features_by_id = None
    if method == "admin_unit_snap":
        index = QgsSpatialIndex(admin_layer.getFeatures())
        admin_features_by_id = {f.id(): f for f in admin_layer.getFeatures()}

    rng = random.Random(seed)  # nosec B311 (seeded sampling for reproducibility, not security)
    new_features = []
    unmatched_count = 0

    for feat in layer.getFeatures():
        geom = feat.geometry()
        if geom is None or geom.isEmpty():
            continue
        pt = geom.asPoint()

        if method == "jitter":
            dx, dy = _uniform_disk_offset(radius, rng)
            new_pt = QgsPointXY(pt.x() + dx, pt.y() + dy)
        elif method == "grid_snap":
            nx, ny = _grid_snap(pt.x(), pt.y(), cell_size)
            new_pt = QgsPointXY(nx, ny)
        else:  # admin_unit_snap
            matched_geom = None
            for fid in index.intersects(geom.boundingBox()):
                candidate_geom = admin_features_by_id[fid].geometry()
                if candidate_geom.contains(geom) or candidate_geom.intersects(geom):
                    matched_geom = candidate_geom
                    break
            if matched_geom is None:
                unmatched_count += 1
                continue
            centroid = matched_geom.centroid().asPoint()
            new_pt = QgsPointXY(centroid.x(), centroid.y())

        new_feat = QgsFeature(new_layer.fields())
        new_feat.setGeometry(QgsGeometry.fromPointXY(new_pt))
        new_feat.setAttributes(feat.attributes())
        new_features.append(new_feat)

    provider.addFeatures(new_features)
    new_layer.updateExtents()
    QgsProject.instance().addMapLayer(new_layer)
    from .humanitarian_style import style_obfuscated_points
    style_obfuscated_points(new_layer)

    result = {
        "success": True,
        "layer_name": out_name,
        "method": method,
        "feature_count": len(new_features),
    }
    if method == "jitter":
        result["radius"] = radius
        result["seed"] = seed
    elif method == "grid_snap":
        result["cell_size"] = cell_size
    else:
        result["admin_layer_name"] = admin_layer_name
        if unmatched_count:
            result["unmatched_points_skipped"] = unmatched_count
    return result
