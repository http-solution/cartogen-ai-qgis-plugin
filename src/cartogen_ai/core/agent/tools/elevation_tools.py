"""M8 leftovers (gap-closing package): elevation settings, the "elevation controller" part of the new layer types.

set_layer_elevation   turn elevation on for a raster (a surface, or a fixed range) or a vector layer (Z clamping, extrusion), with offset and scale
set_project_terrain   the project's terrain: flat (with an offset) or a DEM raster layer, with offset and scale

Both only change settings stored in the project; nothing is written to the data. Written without a QGIS install: tests/test_elevation_tools_live.py
reads every value back from real layers (CI's first run is its first execution). Not covered: the 3D map itself (CI's QGIS has no 3D map layout item
and the plugin has no canvas in CI), so what these settings do to a 3D view or a profile chart is unverified."""
from .gap_options import check_layer_elevation, check_terrain
from .registry import register_tool

try:
    from qgis.core import Qgis, QgsFlatTerrainProvider, QgsProject, QgsRasterDemTerrainProvider, QgsRasterLayer, QgsVectorLayer
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False


def _layer(name):
    found = QgsProject.instance().mapLayersByName(name)
    return found[0] if found else None


@register_tool(
    "set_layer_elevation",
    "Change a layer's elevation settings (used by elevation profiles and 3D views). Raster: enabled, mode 'surface' (the cells are heights) or "
    "'fixed_range', band, z_offset, z_scale. Vector (no on/off switch): clamping 'absolute', 'relative' or 'terrain', z_offset, z_scale, extrusion (metres). "
    "Only the values you give are changed; the result lists the settings read back.",
    {"type": "object", "properties": {
        "layer_name": {"type": "string"}, "enabled": {"type": "boolean"}, "mode": {"type": "string"}, "band": {"type": "integer"},
        "z_offset": {"type": "number"}, "z_scale": {"type": "number"}, "clamping": {"type": "string"}, "extrusion": {"type": "number"}},
     "required": ["layer_name"]})
def set_layer_elevation(layer_name, enabled=None, mode=None, band=None, z_offset=None, z_scale=None, clamping=None, extrusion=None):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    options, problem = check_layer_elevation(enabled, mode, band, z_offset, z_scale, clamping, extrusion)
    if problem:
        return {"error": problem}
    layer = _layer(layer_name)
    if layer is None:
        return {"error": f"Layer '{layer_name}' not found."}
    props = layer.elevationProperties()
    if props is None:
        return {"error": f"Layer '{layer_name}' has no elevation settings (only raster and vector layers do)."}
    if isinstance(layer, QgsRasterLayer):
        if "clamping" in options or "extrusion" in options:
            return {"error": "clamping and extrusion are for vector layers; a raster has mode and band."}
        if "enabled" in options:
            props.setEnabled(options["enabled"])
        if "mode" in options:
            names = {"surface": Qgis.RasterElevationMode.RepresentsElevationSurface, "fixed_range": Qgis.RasterElevationMode.FixedElevationRange}
            props.setMode(names[options["mode"]])
        if "band" in options:
            props.setBandNumber(int(options["band"]))
        read = {"enabled": props.isEnabled(), "band": props.bandNumber()}
    elif isinstance(layer, QgsVectorLayer):
        if "mode" in options or "band" in options:
            return {"error": "mode and band are for raster layers; a vector layer has clamping and extrusion."}
        if "enabled" in options:
            # First live run (QGIS 4.2.2): QgsVectorLayerElevationProperties has no setEnabled/isEnabled. A vector layer's elevation always
            # applies; there is no switch to turn it on, so say so rather than pretending.
            return {"error": "A vector layer has no elevation on/off switch (it always applies). Set clamping, z_offset, z_scale or extrusion instead."}
        if "clamping" in options:
            names = {"absolute": Qgis.AltitudeClamping.Absolute, "relative": Qgis.AltitudeClamping.Relative, "terrain": Qgis.AltitudeClamping.Terrain}
            props.setClamping(names[options["clamping"]])
        if "extrusion" in options:
            props.setExtrusionEnabled(options["extrusion"] > 0)
            props.setExtrusion(options["extrusion"])
        read = {"extrusion_enabled": props.extrusionEnabled(), "extrusion": props.extrusionHeight()}
    else:
        return {"error": f"Layer '{layer_name}' is not a raster or vector layer."}
    if "z_offset" in options:
        props.setZOffset(options["z_offset"])
    if "z_scale" in options:
        props.setZScale(options["z_scale"])
    layer.triggerRepaint()
    read.update({"z_offset": props.zOffset(), "z_scale": props.zScale()})
    return {"success": True, "layer_name": layer.name(), "elevation": read,
            "note": "Stored in the project. What it does to a profile or a 3D view has not been checked by the plugin."}


@register_tool(
    "set_project_terrain",
    "Set the project's terrain used by elevation profiles and 3D views: source 'flat' (optional offset) or 'dem' (a raster layer, optional offset "
    "and scale). Stored in the project; nothing is written to the data.",
    {"type": "object", "properties": {"source": {"type": "string"}, "layer_name": {"type": "string"}, "offset": {"type": "number"},
                                      "scale": {"type": "number"}}, "required": ["source"]})
def set_project_terrain(source, layer_name=None, offset=None, scale=None):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    options, problem = check_terrain(source, offset, scale)
    if problem:
        return {"error": problem}
    props = QgsProject.instance().elevationProperties()
    if options["source"] == "flat":
        provider = QgsFlatTerrainProvider()
        if "offset" in options:
            provider.setOffset(options["offset"])
        if "scale" in options:
            return {"error": "A flat terrain has an offset but no scale."}
    else:
        raster = _layer(layer_name) if layer_name else None
        if not isinstance(raster, QgsRasterLayer):
            return {"error": "source 'dem' needs layer_name: the raster layer that holds the heights."}
        provider = QgsRasterDemTerrainProvider()
        provider.setLayer(raster)
        if "offset" in options:
            provider.setOffset(options["offset"])
        if "scale" in options:
            provider.setScale(options["scale"])
    props.setTerrainProvider(provider)
    now = props.terrainProvider()
    return {"success": True, "source": options["source"], "layer_name": layer_name if options["source"] == "dem" else None,
            "offset": now.offset(), "scale": now.scale(),
            "note": "Stored in the project. What it does to a profile or a 3D view has not been checked by the plugin."}
