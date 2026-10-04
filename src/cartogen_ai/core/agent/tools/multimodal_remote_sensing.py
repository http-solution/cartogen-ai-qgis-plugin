# -*- coding: utf-8 -*-
"""
Multimodal Vision Inspection & STAC Satellite Tools for Cartogen AI.
Interacts with STAC Satellite APIs (Earth Search / Sentinel STAC),
performs visual canvas inspections, and calculates temporal layer change detection.
"""

import json
import time
import urllib.request
import urllib.parse
from .registry import register_tool

try:
    from qgis.utils import iface
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False
    iface = None

# Plugin-process-lifetime cache + quota guard for STAC queries -- same module-global
# scoping already used elsewhere in this codebase (e.g. TOOL_REGISTRY). Nothing formal
# tracks a "session" boundary here, so this resets naturally on plugin reload/QGIS restart.
_STAC_CACHE = {}
_STAC_CACHE_TTL_SECONDS = 600
_STAC_REQUEST_COUNT = 0
_STAC_MAX_REQUESTS = 20


@register_tool("search_stac_satellite_imagery", "Search STAC API (Earth Search / Sentinel-2) for satellite scenes by bounding box and date range.", {"type": "object", "properties": {"bbox": {"type": "array", "items": {"type": "number"}}, "start_date": {"type": "string"}, "end_date": {"type": "string"}, "limit": {"type": "integer"}}, "required": ["bbox", "start_date", "end_date"]})
def search_stac_satellite_imagery(bbox: list, start_date: str, end_date: str, limit: int = 5):
    """Queries STAC Earth Search API (Element 84 / Sentinel-2). Cached and quota-guarded to
    avoid burning API quota via repeated agent-loop queries within the same plugin session."""
    global _STAC_REQUEST_COUNT

    if len(bbox) != 4:
        return {"error": "bbox must be list of 4 numbers [west, south, east, north]"}

    cache_key = (tuple(bbox), start_date, end_date, limit)
    cached = _STAC_CACHE.get(cache_key)
    if cached is not None:
        cached_at, cached_result = cached
        if time.time() - cached_at < _STAC_CACHE_TTL_SECONDS:
            return {**cached_result, "cached": True}
        del _STAC_CACHE[cache_key]

    if _STAC_REQUEST_COUNT >= _STAC_MAX_REQUESTS:
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
    }

    try:
        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data_bytes, headers={"Content-Type": "application/json", "User-Agent": "QGIS-AI-Assistant"})
        _STAC_REQUEST_COUNT += 1
        with urllib.request.urlopen(req, timeout=15) as response:
            res = json.loads(response.read().decode())
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

            result = {"success": True, "scene_count": len(results), "scenes": results}
            _STAC_CACHE[cache_key] = (time.time(), result)
            return result
    except Exception as e:
        return {"error": f"STAC API query failed: {e}"}


@register_tool("inspect_canvas_visually", "Capture current map canvas view and return visual inspection context.", {"type": "object", "properties": {"prompt_guidance": {"type": "string"}}, "required": []})
def inspect_canvas_visually(prompt_guidance: str = "Analyze visible map layers"):
    """Captures map canvas image for multimodal vision inspection."""
    if not QGIS_AVAILABLE or iface is None:
        return {"error": "QGIS map canvas interface not available"}

    try:
        import base64
        import tempfile
        fd, path = tempfile.mkstemp(suffix=".png")
        import os
        os.close(fd)

        iface.mapCanvas().saveAsImage(path)
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
    {"type": "object", "properties": {"raster_before": {"type": "string"}, "raster_after": {"type": "string"}}, "required": ["raster_before", "raster_after"]},
)
def calculate_raster_change_detection(raster_before: str, raster_after: str):
    """Calculates temporal raster difference layer (after - before)."""
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}

    try:
        from .raster_tools import _find_layer_by_name, _run_raster_and_add
        r1 = _find_layer_by_name(raster_before)
        r2 = _find_layer_by_name(raster_after)
        if r1 is None:
            return {"error": f"Layer '{raster_before}' not found"}
        if r2 is None:
            return {"error": f"Layer '{raster_after}' not found"}

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
        if isinstance(result, dict) and result.get("success"):
            try:
                from qgis.core import QgsProject
                from .humanitarian_style import style_diverging_raster
                made = QgsProject.instance().mapLayersByName(result["layer_name"])
                if made:
                    result["styled"] = style_diverging_raster(made[-1])
            except Exception:
                pass
        return result
    except Exception as e:
        return {"error": f"calculate_raster_change_detection failed: {e}"}
