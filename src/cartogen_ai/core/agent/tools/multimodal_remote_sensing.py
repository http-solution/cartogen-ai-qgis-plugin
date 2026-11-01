"""
Multimodal Vision Inspection & STAC Satellite Tools for Cartogen AI.
Interacts with STAC Satellite APIs (Earth Search / Sentinel STAC),
performs visual canvas inspections, and calculates temporal layer change detection.
"""

import contextlib
import datetime
import json
import time
from ...logger import log_event
from ...net import urlopen as _qgis_urlopen
from .registry import register_tool
from ...net import build_request as _net_build_request
from ...net import read_capped as _read_capped

try:
    from qgis.utils import iface
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False
    iface = None

# Plugin-process-lifetime cache + quota guard for STAC queries -- same module-global
# scoping already used elsewhere in this codebase (e.g. TOOL_REGISTRY). Nothing formal
# tracks a "session" boundary here, so this resets naturally on plugin reload/QGIS restart.
_STAC_CACHE: dict = {}
_STAC_CACHE_TTL_SECONDS = 600
_STAC_QUOTA = {"count": 0}   # holder rather than a global (ruff PLW0603)
_STAC_MAX_REQUESTS = 20


@register_tool(
    "search_stac_satellite_imagery",
    "Search STAC API (Earth Search / Sentinel-2) for satellite scenes by bounding box and date range. Pass max_cloud_cover (percent) "
    "when the user names a cloud limit: the filter is applied by the service, so every scene returned meets it. The reply lists "
    "only scenes the service returned (newest first); never add scenes from memory.",
    {"type": "object", "properties": {"bbox": {"type": "array", "items": {"type": "number"}}, "start_date": {"type": "string"},
     "end_date": {"type": "string"}, "limit": {"type": "integer"},
     "max_cloud_cover": {"type": "number", "description": "Only scenes with eo:cloud_cover below this percent (0-100)."}},
     "required": ["bbox", "start_date", "end_date"]})
def search_stac_satellite_imagery(bbox: list, start_date: str, end_date: str, limit: int = 5, max_cloud_cover: float | None = None):
    """Queries STAC Earth Search API (Element 84 / Sentinel-2). Cached and quota-guarded to
    avoid burning API quota via repeated agent-loop queries within the same plugin session."""
    if len(bbox) != 4:
        return {"error": "bbox must be list of 4 numbers [west, south, east, north]"}

    if max_cloud_cover is not None:
        try:
            max_cloud_cover = float(max_cloud_cover)
        except (TypeError, ValueError):
            return {"error": "max_cloud_cover must be a number between 0 and 100 (percent)."}
        if not 0 <= max_cloud_cover <= 100:
            return {"error": "max_cloud_cover must be a number between 0 and 100 (percent)."}

    # A malformed date reached the service as HTTP 400 and the model saw only "STAC API query failed", with nothing to correct (DEF-10).
    try:
        first = datetime.date.fromisoformat(str(start_date)[:10])
        last = datetime.date.fromisoformat(str(end_date)[:10])
    except ValueError:
        return {"error": f"start_date and end_date must be dates written YYYY-MM-DD (got {start_date!r} and {end_date!r})."}
    if first > last:
        return {"error": f"start_date {start_date} is after end_date {end_date}; send the earlier date as start_date."}
    start_date, end_date = first.isoformat(), last.isoformat()

    cache_key = (tuple(bbox), start_date, end_date, limit, max_cloud_cover)
    cached = _STAC_CACHE.get(cache_key)
    if cached is not None:
        cached_at, cached_result = cached
        if time.time() - cached_at < _STAC_CACHE_TTL_SECONDS:
            return {**cached_result, "cached": True}
        del _STAC_CACHE[cache_key]

    if _STAC_QUOTA["count"] >= _STAC_MAX_REQUESTS:
        return {
            "error": f"STAC query quota exceeded for this session (max {_STAC_MAX_REQUESTS}). "
            "Reload the plugin to reset, or reuse an earlier search."
        }

    url = "https://earth-search.aws.element84.com/v1/search"
    payload = {
        "bbox": bbox,
        "datetime": f"{start_date}T00:00:00Z/{end_date}T23:59:59Z",
        "collections": ["sentinel-2-l2a"],
        "limit": limit,
        # newest first, so "the latest scenes" is what the service returns rather than what the model fills in
        "sortby": [{"field": "properties.datetime", "direction": "desc"}],
    }
    if max_cloud_cover is not None:
        # 1.18.2 hand test A13 (2026-10-26): "under 20 percent cloud" had no parameter, so the service returned unfiltered scenes and
        # the model padded the table from memory. The STAC query extension filters at the service.
        payload["query"] = {"eo:cloud_cover": {"lt": max_cloud_cover}}

    try:
        data_bytes = json.dumps(payload).encode("utf-8")
        req = _net_build_request(url, data=data_bytes, headers={"Content-Type": "application/json", "User-Agent": "QGIS-AI-Assistant"})
        _STAC_QUOTA["count"] += 1
        with _qgis_urlopen(req, timeout=15) as response:
            res = json.loads(_read_capped(response).decode())
            features = res.get("features", [])

            results = []
            for feat in features:
                props = feat.get("properties", {})
                assets = feat.get("assets", {})
                results.append({
                    "id": feat.get("id"),
                    "datetime": props.get("datetime"),
                    "cloud_cover": props.get("eo:cloud_cover"),
                    "thumbnail": assets.get("thumbnail", {}).get("href"),
                    "visual_href": assets.get("visual", {}).get("href"),
                })

            result = {"success": True, "scene_count": len(results), "scenes": results,
                      "filters": {"max_cloud_cover": max_cloud_cover, "start_date": start_date, "end_date": end_date}}
            if not results:
                result["note"] = "The service returned no scenes for these filters; say so rather than listing scenes from memory."
            _STAC_CACHE[cache_key] = (time.time(), result)
            return result
    except Exception as e:
        return {"error": f"STAC API query failed: {e}"}


_LEGEND_MAX_CHARS = 1500
_LEGEND_ITEMS_PER_LAYER = 6


def _legend_text(layers):
    """One short line per visible layer: its name and the legend labels of its renderer (or 'raster'). Best effort, never raises: the picture is
    the point, the text is a help beside it."""
    lines = []
    for layer in layers:
        label = layer.name()
        with contextlib.suppress(Exception):
            renderer = layer.renderer() if hasattr(layer, "renderer") else None
            items = [i.label() for i in renderer.legendSymbolItems()][:_LEGEND_ITEMS_PER_LAYER] if renderer is not None else []
            label += f": {', '.join(items)}" if items else (": raster" if getattr(layer, "rasterType", None) else "")
        lines.append(label)
    return "; ".join(lines)[:_LEGEND_MAX_CHARS]


def _render_capped(canvas, extent_layer=None):
    """Renders what the canvas shows (or the extent of `extent_layer`) off-screen at no more than 1,280 pixels on the long edge, without moving the
    canvas. Returns {"image_b64", "mime", "width", "height", "blank", "legend_text", "layers_text"}. MAIN THREAD. Raises on any failure so the caller
    can fall back to the plain screenshot."""
    import base64
    from qgis.core import QgsCoordinateTransform, QgsMapRendererParallelJob, QgsMapSettings, QgsProject
    from qgis.PyQt.QtCore import QBuffer, QIODevice, QSize
    from ...services.canvas_capture import fit_size
    settings = QgsMapSettings(canvas.mapSettings())
    size = canvas.size()
    width, height = fit_size(size.width(), size.height())
    settings.setOutputSize(QSize(width, height))
    if extent_layer:
        found = QgsProject.instance().mapLayersByName(extent_layer)
        if not found:
            raise ValueError(f"Layer '{extent_layer}' not found")
        box = QgsCoordinateTransform(found[0].crs(), settings.destinationCrs(), QgsProject.instance()).transformBoundingBox(found[0].extent())
        box.scale(1.1)
        settings.setExtent(box)
    job = QgsMapRendererParallelJob(settings)
    job.start()
    job.waitForFinished()
    image = job.renderedImage()
    if image.isNull():
        raise ValueError("the canvas rendered no image")
    background = settings.backgroundColor().rgba()
    blank = all(image.pixel(int(x * (width - 1) / 31), int(y * (height - 1) / 31)) == background for x in range(32) for y in range(32))
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    layers = list(settings.layers())
    return {"image_b64": base64.b64encode(bytes(buffer.data())).decode(), "mime": "png", "width": width, "height": height, "blank": blank,
            "legend_text": _legend_text(layers), "layers_text": ", ".join(layer.name() for layer in layers)}


@register_tool("inspect_canvas_visually",
    "LOOK at the current map: captures the map canvas as a picture you can see (at most 1,280 pixels on the long edge), sent to you right after "
    "this result together with the legend and the visible layers as text. Use it for 'what is wrong with this map', 'does it look right', "
    "'what does the map show'. Optional extent_layer: look at that layer's extent instead of the current view (the canvas is not moved). If the "
    "model cannot see pictures you get the legend and layer list as text instead.",
    {"type": "object", "properties": {"prompt_guidance": {"type": "string"},
     "extent_layer": {"type": "string", "description": "Optional: name of a layer; the picture shows that layer's extent instead of the current view."}},
     "required": []},
    keywords=[
        "look at the map", "look at the canvas", "see the map", "screenshot of the map", "what does the map look like",
        "inspect the canvas", "check how the map looks", "view the canvas", "what is wrong with this map", "what's wrong with the map",
        "does the map look right", "describe the map",
    ],
)
def inspect_canvas_visually(prompt_guidance: str = "Analyze visible map layers", extent_layer: str | None = None):
    """Captures the map canvas for the model to look at. The picture is taken out of this result by the agent loop and sent as an image part
    (core/services/canvas_capture.py); it is NOT meant to be read as text."""
    if not QGIS_AVAILABLE or iface is None:
        return {"error": "QGIS map canvas interface not available"}

    try:
        canvas = iface.mapCanvas()
        try:
            return {"success": True, "prompt_guidance": prompt_guidance, **_render_capped(canvas, extent_layer),
                    "message": "Canvas image captured successfully for vision model evaluation."}
        except ValueError as e:
            return {"error": f"inspect_canvas_visually failed: {e}"}
        except Exception as e:
            # The off-screen render needs the real QGIS API; if it is not available (or fails) take the plain screenshot of the canvas, as before.
            log_event("canvas_render_fallback", tag="Tools", error_class=type(e).__name__, error=True)
        import base64
        import os
        import tempfile
        fd, path = tempfile.mkstemp(suffix=".png")
        os.close(fd)

        canvas.saveAsImage(path)
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()

        return {
            "success": True,
            "prompt_guidance": prompt_guidance,
            "mime": "png",
            "image_b64": b64,
            "message": "Canvas image captured successfully for vision model evaluation."
        }
    except Exception as e:
        return {"error": f"inspect_canvas_visually failed: {e}"}


_ALIGN_PARAMS_CHANGE = {
    "align_to_first": {"type": "boolean", "description": "If the two rasters are not on one pixel grid, warp the 'before' raster onto the 'after' raster's grid instead of refusing; the result says what was done. Default false: refuse."},
    "resampling": {"type": "string", "description": "With align_to_first: 'bilinear' (default), 'nearest' (classes/counts) or 'cubic'."},
}


@register_tool(
    "calculate_raster_change_detection",
    "Compute pixel-wise differential change between two temporal rasters (after minus before) -- "
    "'what changed between these two satellite images', 'compare before and after images for "
    "damage', 'show me the damage from before to after'. The core building block "
    "calculate_damage_exposure_severity composes into a full damage assessment (zonal stats per "
    "admin unit, building exposure counts, severity classing) -- use this tool directly only for "
    "the raw pixel-difference layer itself, calculate_damage_exposure_severity for a per-district "
    "severity score. Produces a new raster layer named 'change_detection_<after>_vs_<before>' "
    "added to the project with a diverging ramp symmetric about zero (blue = decrease, red = "
    "increase, no change transparent) so the change pattern is visible straight away.",
    {"type": "object", "properties": {"raster_before": {"type": "string"}, "raster_after": {"type": "string"}, **_ALIGN_PARAMS_CHANGE}, "required": ["raster_before", "raster_after"]},
    keywords=[
        "got worse", "show where it got worse", "between last year and this year", "newly flooded", "before and after the", "compare the vegetation", "change between the two",
        "before and after", "compare images", "what changed", "how much damage", "damage from before to after",
        "satellite comparison",
    ],
)
def calculate_raster_change_detection(raster_before: str, raster_after: str, align_to_first: bool = False, resampling: str = "bilinear"):
    """Calculates temporal raster difference layer (after - before)."""
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}

    try:
        from .raster_tools import _find_raster_argument, _grid_or_error, _run_raster_and_add
        # DEF-11: accepts a layer name, the file of a loaded raster, or a raster file to load (the D6 prompt names files, not layers).
        r1, note_before = _find_raster_argument(raster_before)
        r2, note_after = _find_raster_argument(raster_after)
        if r1 is None:
            return {"error": f"Layer '{raster_before}' not found. Give the name of a raster layer in the project, or the path of a raster file."}
        if r2 is None:
            return {"error": f"Layer '{raster_after}' not found. Give the name of a raster layer in the project, or the path of a raster file."}
        loaded_notes = [n for n in (note_before, note_after) if n]
        raster_before, raster_after = r1.name(), r2.name()
        used, grid_error, align_note = _grid_or_error([r2, r1], align_to_first, resampling)
        if grid_error:
            return {"error": grid_error}
        r2, r1 = used

        result = _run_raster_and_add(
            "gdal:rastercalculator",
            {
                "INPUT_A": r2,
                "BAND_A": 1,
                "INPUT_B": r1,
                "BAND_B": 1,
                "FORMULA": "A.astype(float)-B.astype(float)",
                "NO_DATA": None,
                "RTYPE": 5,
            },
            f"change_detection_{raster_after}_vs_{raster_before}",
        )
        if isinstance(result, dict) and result.get("success") and align_note:
            result["alignment"] = align_note
        if isinstance(result, dict) and result.get("success") and loaded_notes:
            result["loaded"] = " ".join(loaded_notes)
        if isinstance(result, dict) and result.get("success"):
            with contextlib.suppress(Exception):
                from qgis.core import QgsProject
                from .humanitarian_style import style_diverging_raster
                made = QgsProject.instance().mapLayersByName(result["layer_name"])
                if made:
                    result["styled"] = style_diverging_raster(made[-1])
        return result
    except Exception as e:
        return {"error": f"calculate_raster_change_detection failed: {e}"}
