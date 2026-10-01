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
# What a raster's values MEAN, shown as the legend title (QgsColorRampLegendNodeSettings) so the numbers carry a unit.
# Population is WorldPop's "people per cell" (the cell size depends on the product the user fetched, so it is not stated).
RASTER_UNITS = {"population": "People per cell", "density": "Relative density (0 = none, max = highest)",
                "surface": "Value"}
ALGORITHM_RASTER_UNITS = {"slope": "Slope (degrees)", "aspect": "Aspect (degrees from north)",
                          "heatmapkerneldensityestimation": "Kernel density (relative)",
                          "idwinterpolation": "Interpolated value", "tininterpolation": "Interpolated value",
                          "cellstatistics": "Cell statistic", "reclassifybytable": "Reclassified value",
                          "rastercalculator": "Calculated value"}

# Field-name candidates for an automatic label, best first (matched case-insensitively). Only names a person would read.
LABEL_FIELD_CANDIDATES = ("name", "name_en", "facility_name", "facility", "site_name", "adm3_en", "adm2_en", "adm1_en",
                          "admin3name_en", "admin2name_en", "admin1name_en", "shapename", "name_1", "name_2", "title",
                          "label", "name_ar")
AUTO_LABEL_MAX_FEATURES = 60          # above this a label layer is a cloud; the user can ask for labels explicitly
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


def raster_unit_for(kind, alg_id=None):
    """Legend title for a raster: the algorithm's own meaning when known, else the kind's. Pure."""
    short = str(alg_id or "").split(":")[-1]
    return ALGORITHM_RASTER_UNITS.get(short) or RASTER_UNITS.get(kind) or RASTER_UNITS["surface"]


def choose_label_field(field_names):
    """The field to label by, or None. Pure. Prefers LABEL_FIELD_CANDIDATES in order; never an id/code field."""
    lowered = {str(n).lower(): n for n in field_names or []}
    for candidate in LABEL_FIELD_CANDIDATES:
        if candidate in lowered:
            return lowered[candidate]
    return None


def should_auto_label(feature_count, field_names, limit=AUTO_LABEL_MAX_FEATURES):
    """(label?, field). Label only a small layer that has a readable name field. Pure."""
    field = choose_label_field(field_names)
    try:
        count = int(feature_count)
    except (TypeError, ValueError):
        return False, None
    if field is None or count <= 0 or count > limit:
        return False, None
    return True, field


def algorithm_short_name(alg_id):
    return str(alg_id or "").split(":")[-1]


def vector_role_for(alg_id):
    return ALGORITHM_VECTOR_ROLES.get(algorithm_short_name(alg_id))


def raster_kind_for(alg_id):
    return ALGORITHM_RASTER_KINDS.get(algorithm_short_name(alg_id))


# ----------------------------------------------------------- QGIS half --

def style_continuous_raster(layer, kind="surface", band=1, unit=None):
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
    _set_unit_legend(shader, unit or raster_unit_for(kind))
    raster_shader = QgsRasterShader()
    raster_shader.setRasterShaderFunction(shader)
    layer.setRenderer(QgsSingleBandPseudoColorRenderer(provider, band, raster_shader))
    layer.triggerRepaint()
    return True


def _set_unit_legend(shader, unit_text):
    """Continuous colour-bar legend whose title carries the unit (QgsColorRampLegendNodeSettings, QGIS >= 3.18).

    Without it the legend is a column of bare numbers. Best-effort: an older/odd build keeps the plain labelled entries."""
    try:
        from qgis.core import QgsColorRampLegendNodeSettings
        legend = QgsColorRampLegendNodeSettings()
        legend.setUseContinuousLegend(True)
        legend.setTitle(unit_text)
        shader.setLegendSettings(legend)
        return True
    except Exception:
        return False


def style_auto_labels(layer, limit=AUTO_LABEL_MAX_FEATURES):
    """Label a small named layer (facilities, admin areas) with its name field. Returns the field used, or None.

    Reuses apply_labels' halo/placement so automatic and requested labels look the same; large layers are skipped
    (a label cloud hides the map) and the user can still ask for labels explicitly."""
    if not QGIS_AVAILABLE or layer is None or not hasattr(layer, "featureCount") or hasattr(layer, "bandCount"):
        return None
    try:
        ok, field = should_auto_label(layer.featureCount(), [f.name() for f in layer.fields()], limit)
        if not ok:
            return None
        from .vector_tools import apply_labels
        from qgis.core import QgsProject
        if QgsProject.instance().mapLayer(layer.id()) is None:
            return None
        res = apply_labels(layer.name(), target_field=field, font_size=9)
        return field if isinstance(res, dict) and not res.get("error") else None
    except Exception:
        return None


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
        return f"raster:{kind}" if kind and style_continuous_raster(layer, kind, unit=raster_unit_for(kind, alg_id)) else None
    role = vector_role_for(alg_id)
    try:
        from ..map_intelligence import process_map_output
        if role:
            process_map_output(layer, output_role=role)
            return f"vector:{role}"
        if QgsWkbTypes.geometryType(layer.wkbType()) == QgsWkbTypes.GeometryType.PointGeometry:
            if not style_points_default(layer):
                return None
            style_auto_labels(layer)
            return "points"
    except Exception:
        return None
    return None
