"""calculate_change_matrix (PLAN-023 R3-4): the from-to change matrix between two class rasters, with hectares, gain, loss, net and persistence.

The cross-tabulation and the areas are computed by the pure code in raster_change.py (hand-checked offline) from the two rasters read through GDAL. The tool writes
two table layers (the non-empty from-to transitions, and a per-class summary) and a bar chart of the net change per class, and returns the numbers in its reply.
Cells that are NoData in either raster are left out. Class values must be whole numbers; a continuous raster has to be reclassified first. The rasters must share
one pixel grid (the existing check; with align_to_first the second is warped onto the first, with nearest-neighbour resampling by default because classes must not be blended).

Written without a QGIS install; tests/test_raster_change_tool_live.py is its first execution in CI."""
from . import raster_change as rc
from . import raster_indices as ri
from . import raster_numpy as rn
from ._layer_checks import require_valid_layer
from .raster_tools import _find_layer_by_name, _grid_or_error, _with_alignment_note
from .registry import register_tool

try:
    from qgis.core import QgsFeature, QgsProject, QgsRasterLayer, QgsVectorLayer
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False

MATRIX_IN_REPLY_MAX_CLASSES = 12      # a larger matrix is in the table layer, not in the reply
TRANSITIONS_IN_REPLY_MAX = 100        # the largest transitions are listed in the reply; all of them are in the table layer


def crs_area_kind(projection_wkt):
    """(is_geographic, metres per linear unit) from a CRS in WKT: (True, 1.0) geographic, (False, metres per unit) projected, (None, 1.0) when it is neither or cannot be read.
    Uses GDAL's osr, which ships with QGIS."""
    try:
        from osgeo import osr
        srs = osr.SpatialReference()
        if not projection_wkt or srs.ImportFromWkt(projection_wkt) != 0:
            return None, 1.0
        if srs.IsGeographic():
            return True, 1.0
        if srs.IsProjected():
            return False, float(srs.GetLinearUnits())
    except (ImportError, RuntimeError, ValueError, TypeError):      # no GDAL bindings, or GDAL raised on a CRS it cannot read (exceptions enabled)
        return None, 1.0
    return None, 1.0


def _write_tables(base_name, per_class, transitions, area_known):
    """Adds the transitions table and the per-class summary table to the project; returns their names."""
    trans = QgsVectorLayer("None?field=from_class:integer&field=from_name:string&field=to_class:integer&field=to_name:string"
                           "&field=cells:integer&field=hectares:double&field=percent:double", base_name, "memory")
    require_valid_layer(trans)
    feats = []
    for t in transitions:
        f = QgsFeature(trans.fields())
        f.setAttributes([t["from"], t["from_name"], t["to"], t["to_name"], t["cells"], t.get("hectares"), t["percent"]])
        feats.append(f)
    trans.dataProvider().addFeatures(feats)
    QgsProject.instance().addMapLayer(trans)
    summary_name = f"{base_name}_summary"
    summary = QgsVectorLayer("None?field=class_value:integer&field=class_name:string&field=cells_before:integer&field=cells_after:integer"
                             "&field=persistence:integer&field=loss:integer&field=gain:integer&field=net:integer"
                             "&field=ha_before:double&field=ha_after:double&field=ha_loss:double&field=ha_gain:double&field=ha_net:double"
                             "&field=percent_before:double&field=percent_after:double", summary_name, "memory")
    require_valid_layer(summary)
    feats = []
    for c in per_class:
        f = QgsFeature(summary.fields())
        f.setAttributes([c["value"], c["name"], c["cells_before"], c["cells_after"], c["persistence"], c["loss"], c["gain"], c["net"],
                         c.get("ha_before"), c.get("ha_after"), c.get("ha_loss"), c.get("ha_gain"), c.get("ha_net"),
                         c["percent_before"], c["percent_after"]])
        feats.append(f)
    summary.dataProvider().addFeatures(feats)
    QgsProject.instance().addMapLayer(summary)
    return [base_name, summary_name]


def _chart(per_class, area_known):
    """(path, note): a bar chart of the net change per class through generate_chart, or (None, why it was not made). Never raises."""
    try:
        from .reporting_tools import generate_chart
        labels = [c["name"] or str(c["value"]) for c in per_class]
        values = [c["ha_net"] if area_known else c["net"] for c in per_class]
        out = generate_chart("bar", "Net change by class (" + ("hectares" if area_known else "cells") + ")", labels, values,
                             x_label="Class", y_label="Hectares gained minus lost" if area_known else "Cells gained minus lost")
    except Exception as e:
        return None, f"The chart was not made: {e}"
    if isinstance(out, dict) and out.get("success"):
        return out["output_path"], None
    return None, "The chart was not made: " + str((out or {}).get("error", "unknown error"))


@register_tool(
    "calculate_change_matrix",
    "From-to change matrix between two CLASS rasters (for example land cover in two years): how many cells, hectares and percent moved from each class to each other class, "
    "plus per-class persistence, loss, gain and net change. 'What changed between these two land-cover rasters', 'how much forest was lost to cropland'. Give raster_a "
    "(before) and raster_b (after), and optionally `classes` naming the values ({\"10\": \"Tree cover\", \"40\": \"Cropland\"}). Class values must be whole numbers (a "
    "continuous raster must be reclassified first; at most 50 classes). Cells that are NoData in either raster are left out. Hectares come from the CRS: exact for a "
    "projected raster, approximate (sphere, row by row) for a geographic one. Adds two table layers (the transitions and a per-class summary) and a bar chart of the "
    "net change per class. The rasters must share one pixel grid (or pass align_to_first, which resamples with nearest neighbour).",
    {"type": "object", "properties": {
        "raster_a": {"type": "string", "description": "The earlier class raster (layer name, or 'layer name@band')."},
        "raster_b": {"type": "string", "description": "The later class raster."},
        "classes": {"type": "object", "additionalProperties": {"type": "string"}, "description": "Optional names: {value: name}, for example {\"1\": \"Forest\"}."},
        "output_name": {"type": "string", "description": "Name of the transitions table (default change_matrix); the summary is <name>_summary."},
        "chart": {"type": "boolean", "description": "Also make the bar chart (default true)."},
        "align_to_first": {"type": "boolean", "description": "If the rasters are not on one grid, warp raster_b onto raster_a's grid with nearest-neighbour resampling."},
        "resampling": {"type": "string", "description": "With align_to_first: 'nearest' (default, right for classes), 'bilinear' or 'cubic' (they blend classes; not advised)."}},
     "required": ["raster_a", "raster_b"]},
    keywords=["change matrix", "from to", "land cover change", "transition matrix", "what changed between", "gain and loss", "forest loss", "cross tabulation", "land use change"],
)
def calculate_change_matrix(raster_a, raster_b, classes=None, output_name="change_matrix", chart=True, align_to_first=False, resampling="nearest"):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    names, class_error = rc.parse_classes(classes)
    if class_error:
        return {"error": class_error}
    refs = []
    for label, text in (("raster_a", raster_a), ("raster_b", raster_b)):
        layer_name, band_no = ri.parse_band_ref(text)
        if layer_name is None:
            return {"error": f"'{text}' is not a valid reference for {label}: use a layer name or 'layer name@band'."}
        layer = _find_layer_by_name(layer_name)
        if layer is None:
            return {"error": f"Layer '{layer_name}' ({label}) not found."}
        if not isinstance(layer, QgsRasterLayer):
            return {"error": f"'{layer_name}' ({label}) is not a raster layer."}
        if band_no > layer.bandCount():
            return {"error": f"'{layer_name}' has {layer.bandCount()} band(s); band {band_no} was asked for {label}."}
        refs.append((layer, band_no))
    unique = list({layer.id(): layer for layer, _b in refs}.values())
    used, grid_error, align_note = _grid_or_error(unique, align_to_first, resampling)
    if grid_error:
        return {"error": grid_error}
    by_id = {orig.id(): new for orig, new in zip(unique, used, strict=True)}
    try:
        arrays, valid, info = [], None, None
        for layer, band_no in refs:
            data, band_valid, band_info = rn.read_bands(by_id[layer.id()].source(), [band_no])
            arrays.append(data[:, :, 0])
            valid = band_valid if valid is None else (valid & band_valid)
            info = info or band_info
        is_geographic, metres_per_unit = crs_area_kind(info["projection"])
        row_ha = rc.row_areas_ha(info["geotransform"], arrays[0].shape[0], is_geographic, metres_per_unit)
        tab = rc.cross_tab(arrays[0], arrays[1], valid, row_ha)
    except ValueError as e:
        return {"error": f"calculate_change_matrix: {e}"}
    except Exception as e:
        return {"error": f"The change matrix could not be computed: {e}"}
    if not tab["classes"]:
        return {"error": "There are no cells that are valid in both rasters, so there is nothing to compare."}
    per_class, transitions, totals = rc.summarise(tab, names)
    area_known = row_ha is not None
    base = (output_name or "").strip() or "change_matrix"
    try:
        table_names = _write_tables(base, per_class, transitions, area_known)
    except ValueError as e:
        return {"error": str(e)}
    result = {
        "success": True, "layers_created": table_names, "classes": tab["classes"], "per_class": per_class, "totals": totals,
        "from_raster": refs[0][0].name(), "to_raster": refs[1][0].name(),
        "area_method": (("exact for the projected CRS: cell width x height in metres" if is_geographic is False else
                         "approximate for the geographic CRS: each row's cell area on a sphere with the WGS84 authalic radius, not the ellipsoid")
                        if area_known else "not available: the raster's CRS is neither projected nor geographic, so only cell counts are given"),
        "limits": "Only cells valid in both rasters are counted. Class values must be whole numbers. Class names are only those you gave.",
    }
    if len(tab["classes"]) <= MATRIX_IN_REPLY_MAX_CLASSES:
        result["matrix"] = {"rows_are": "from (raster_a)", "columns_are": "to (raster_b)", "classes": tab["classes"], "cells": tab["counts"].tolist()}
    else:
        result["matrix_note"] = f"{len(tab['classes'])} classes: the full matrix is in the table layer '{base}'."
    changes = sorted((t for t in transitions if t["from"] != t["to"]), key=lambda t: -t["cells"])
    result["largest_changes"] = changes[:TRANSITIONS_IN_REPLY_MAX]
    if len(changes) > TRANSITIONS_IN_REPLY_MAX:
        result["changes_note"] = f"{len(changes)} class changes; the {TRANSITIONS_IN_REPLY_MAX} largest are listed, all are in the table layer '{base}'."
    if chart:
        path, note = _chart(per_class, area_known)
        if path:
            result["chart_path"] = path
        else:
            result["chart_note"] = note
    return _with_alignment_note(result, align_note)
