# -*- coding: utf-8 -*-
"""Default look for outputs that used to arrive in QGIS's raw defaults (visualization gap analysis, 2026-10-01).

Measured gaps this closes (see docs/VISUALIZATION_AND_ANALYSIS_GAP_ANALYSIS_2026-10-01.md):
- fetch_worldpop_population, hotspot_analysis and interpolate_surface added a raster with NO renderer call, so a population
  or density surface came up in QGIS's default grey stretch -- the reach figures and exposure numbers sat on top of an
  unreadable grey block.
- run_allowlisted_processing_algorithm styled nothing it created.
- load_tabular_data_as_layer drew points in a random default colour.

The pure half (ramp stops, labels, role mapping) is unit tested offline. The QGIS half uses the raster shader API the
repo already runs against QGIS 4.2.2 (raster_tools.apply_raster_stretch resolves the same enums) and is covered by
tests/test_output_style_live.py in CI.
"""
try:
    from qgis.core import (
        QgsColorRampShader, QgsMarkerSymbol, QgsRasterShader, QgsSingleBandPseudoColorRenderer, QgsSingleSymbolRenderer,
        QgsWkbTypes,
    )
    from qgis.PyQt.QtGui import QColor
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False

# kind -> [(fraction of the maximum, (r, g, b, a))]. Population and density are heavy-tailed, so the stops crowd toward the
# low end; the first stop (the zero value) is fully transparent so empty land shows the basemap.
RASTER_RAMPS = {
    "population": [
        (0.0, (255, 255, 204, 0)), (0.002, (255, 255, 204, 150)), (0.02, (254, 217, 118, 200)),
        (0.1, (253, 141, 60, 220)), (0.3, (227, 26, 28, 235)), (0.6, (177, 0, 38, 245)), (1.0, (103, 0, 13, 255)),
    ],
    "density": [
        (0.0, (255, 245, 235, 0)), (0.05, (254, 224, 144, 160)), (0.25, (253, 174, 97, 210)),
        (0.5, (244, 109, 67, 235)), (0.75, (215, 48, 39, 245)), (1.0, (165, 0, 38, 255)),
    ],
    # A continuous surface (interpolated values, slope, aspect): fully opaque, perceptually ordered.
    "surface": [
        (0.0, (68, 1, 84, 255)), (0.25, (59, 82, 139, 255)), (0.5, (33, 144, 140, 255)),
        (0.75, (93, 201, 99, 255)), (1.0, (253, 231, 37, 255)),
    ],
}

# Allowlisted algorithm -> how its OUTPUT should look.
ALGORITHM_VECTOR_ROLES = {
    "buffer": "proximity_buffer", "convexhull": "proximity_buffer", "voronoipolygons": "proximity_buffer",
    "delaunaytriangulation": "proximity_buffer",
    "clip": "selection_overlay", "intersection": "selection_overlay", "difference": "selection_overlay",
    "symmetricaldifference": "selection_overlay", "union": "selection_overlay", "dissolve": "selection_overlay",
    "extractbylocation": "selection_overlay",
    "shortestpathpointtopoint": "route_line", "shortestpathpointtolayer": "route_line",
    "serviceareafrompoint": "route_line",
}
ALGORITHM_RASTER_KINDS = {
    "slope": "surface", "aspect": "surface", "rastercalculator": "surface", "idwinterpolation": "surface",
    "tininterpolation": "surface", "cellstatistics": "surface", "reclassifybytable": "surface",
    "heatmapkerneldensityestimation": "density",
}
POINT_STYLE = {"color": "#1d6fa5", "outline": "#ffffff", "size": "2.6"}


def ramp_stops(kind, vmax, vmin=0.0):
    """[(value, (r,g,b,a), label)] for a raster ramp, values ascending between vmin and vmax. Pure.

    Population/density ramps start at 0 (transparent); a surface ramp spans vmin..vmax. A non-positive range returns
    a single opaque stop pair so a flat raster still draws."""
    base = RASTER_RAMPS.get(kind) or RASTER_RAMPS["surface"]
    try:
        top = float(vmax)
        low = float(vmin)
    except (TypeError, ValueError):
        top, low = 1.0, 0.0
    if kind in ("population", "density"):
        low = 0.0
    if top <= low:
        top = low + 1.0
    stops, last = [], None
    for fraction, rgba in base:
        value = low + fraction * (top - low)
        if last is not None and value <= last:
            continue
        stops.append((value, rgba, _label(value)))
        last = value
    return stops


def _label(value):
    v = float(value)
    if abs(v) >= 100:
        return f"{v:,.0f}"
    if abs(v) >= 1:
        return f"{v:.1f}"
    return f"{v:.3g}"


def algorithm_short_name(alg_id):
    return str(alg_id or "").split(":")[-1]


def vector_role_for(alg_id):
    return ALGORITHM_VECTOR_ROLES.get(algorithm_short_name(alg_id))


def raster_kind_for(alg_id):
    return ALGORITHM_RASTER_KINDS.get(algorithm_short_name(alg_id))


# ----------------------------------------------------------- QGIS half --

def style_continuous_raster(layer, kind="surface", band=1):
    """Pseudocolour renderer from RASTER_RAMPS[kind] over the band's own min/max. Returns True when applied."""
    if not QGIS_AVAILABLE or layer is None:
        return False
    from .raster_tools import _COLOR_RAMP_SHADER_ITEM, _RAMP_INTERPOLATED
    if _COLOR_RAMP_SHADER_ITEM is None or _RAMP_INTERPOLATED is None:
        return False
    provider = layer.dataProvider()
    stats = provider.bandStatistics(band)
    vmin, vmax = stats.minimumValue, stats.maximumValue
    stops = ramp_stops(kind, vmax, vmin)
    shader = QgsColorRampShader(stops[0][0], stops[-1][0])
    shader.setColorRampType(_RAMP_INTERPOLATED)
    shader.setColorRampItemList([
        _COLOR_RAMP_SHADER_ITEM(value, QColor(*rgba), label) for value, rgba, label in stops])
    raster_shader = QgsRasterShader()
    raster_shader.setRasterShaderFunction(shader)
    layer.setRenderer(QgsSingleBandPseudoColorRenderer(provider, band, raster_shader))
    layer.triggerRepaint()
    return True


def style_points_default(layer):
    """One consistent point look (blue, white halo) instead of a random default colour. Returns True when applied."""
    if not QGIS_AVAILABLE or layer is None:
        return False
    symbol = QgsMarkerSymbol.createSimple({
        "name": "circle", "color": POINT_STYLE["color"], "outline_color": POINT_STYLE["outline"],
        "outline_width": "0.4", "size": POINT_STYLE["size"]})
    layer.setRenderer(QgsSingleSymbolRenderer(symbol))
    layer.triggerRepaint()
    return True


def style_algorithm_output(layer, alg_id):
    """Styles a Processing output by what the algorithm made. Returns a short label of what was applied, or None."""
    if not QGIS_AVAILABLE or layer is None:
        return None
    if hasattr(layer, "bandCount"):                       # raster
        kind = raster_kind_for(alg_id)
        return f"raster:{kind}" if kind and style_continuous_raster(layer, kind) else None
    role = vector_role_for(alg_id)
    try:
        from ..map_intelligence import process_map_output
        if role:
            process_map_output(layer, output_role=role)
            return f"vector:{role}"
        if QgsWkbTypes.geometryType(layer.wkbType()) == QgsWkbTypes.GeometryType.PointGeometry:
            return "points" if style_points_default(layer) else None
    except Exception:
        return None
    return None
