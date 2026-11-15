"""reshape_geometry, offset_curve, reverse_line and trim_extend_lines (PLAN-023 R9-3).

Three of them change geometry in place, so each returns a PREVIEW_REQUIRED card first and applies inside the repo's edit command (_edit_session.edit_command): one undoable step
(undo_manual_edit), no takeover of a layer the user already has in edit mode, nothing applied when anything fails. offset_curve is non-destructive: it writes a new memory layer.

* reshape_geometry: QGIS's reshapeGeometry. A line drawn across a polygon or line (given as WKT in the layer's CRS) cuts a new edge; a line that does not cross the feature changes nothing
  and says so.
* offset_curve: QgsGeometry.offsetCurve for each line, a positive distance to the left of the line and a negative to the right, round / miter / bevel joins.
* reverse_line: reverses the vertex order of every line part of the chosen features (or all).
* trim_extend_lines: moves line ends onto the nearest point of another line within a tolerance, see line_ops.py (it is pure and tested offline).

Written without a QGIS install; tests/test_line_edit_tools_live.py is their first execution in CI."""
from . import line_ops as lo
from ._layer_checks import degrees_value_problem, require_valid_layer
from .attribute_edit_tools import _layer, _unsaved_note, preview
from .registry import register_tool

try:
    from qgis.core import Qgis, QgsFeature, QgsGeometry, QgsLineString, QgsPointXY, QgsProject, QgsVectorLayer, QgsWkbTypes
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False

SKIPPED_NOTE_MAX = 5


def _success(result):
    return getattr(result, "name", None) == "Success" or result == 0


def _line_layer(layer_name, allow_polygon=False):
    """(layer, error): the named vector layer when it is a line layer (or, with allow_polygon, a polygon layer too). Needs QGIS."""
    layer, err = _layer(layer_name)
    if err:
        return None, err
    kind = QgsWkbTypes.geometryType(layer.wkbType())
    ok = kind == QgsWkbTypes.GeometryType.LineGeometry or (allow_polygon and kind == QgsWkbTypes.GeometryType.PolygonGeometry)
    if not ok:
        return None, {"error": f"'{layer_name}' is not a {'line or polygon' if allow_polygon else 'line'} layer."}
    return layer, None


def _line_parts(geometry):
    """([points of each line part as (x, y)], is_multipart). Needs QGIS."""
    if geometry.isMultipart():
        return [[(p.x(), p.y()) for p in part] for part in geometry.asMultiPolyline()], True
    return [[(p.x(), p.y()) for p in geometry.asPolyline()]], False


def _build_line(parts, multipart):
    lines = [[QgsPointXY(x, y) for x, y in part] for part in parts]
    return QgsGeometry.fromMultiPolylineXY(lines) if multipart else QgsGeometry.fromPolylineXY(lines[0])


def _features(layer, feature_ids):
    """([features with a geometry], error): all features, or the ones named in feature_ids. Needs QGIS."""
    if feature_ids:
        try:
            wanted = [int(i) for i in feature_ids]
        except (TypeError, ValueError):
            return None, "feature_ids must be whole numbers."
        found = [layer.getFeature(i) for i in wanted]
        missing = [i for i, f in zip(wanted, found, strict=True) if not f.isValid()]
        if missing:
            return None, f"Feature(s) {missing[:SKIPPED_NOTE_MAX]} not found in '{layer.name()}'."
        return [f for f in found if not f.geometry().isNull()], None
    return [f for f in layer.getFeatures() if not f.geometry().isNull()], None


def _apply_changes(layer, label, changes):
    """Applies {feature id: new QgsGeometry} in one edit command; returns (error or None, owned). Needs QGIS."""
    from ._edit_session import EditError, edit_command
    try:
        with edit_command(layer, label) as owned:
            for fid, geometry in changes.items():
                if not layer.changeGeometry(fid, geometry):
                    raise EditError(f"the layer refused the geometry change of feature {fid} (read-only source?).")
    except EditError as e:
        return f"Nothing was changed: {e}", False
    return None, owned


def _finish(out, owned, layer):
    if layer.crs().isValid() and layer.crs().isGeographic():
        out["note_crs"] = "The layer is in a geographic CRS, so distances and tolerances are in degrees."
    note = _unsaved_note(owned)
    if note:
        out["note"] = note
    return out


@register_tool(
    "reshape_geometry",
    "Reshape one feature of a line or polygon layer with a line drawn across it: line_wkt (a LINESTRING in the layer's CRS) cuts a new edge where it enters and leaves the feature, "
    "as QGIS's Reshape tool does. A line that does not cross the feature changes nothing and the reply says so. Changes geometry: a preview is shown for confirmation first, the edit "
    "is one undoable step (undo_manual_edit), and a result that would make a valid geometry invalid is refused.",
    {"type": "object", "properties": {
        "layer_name": {"type": "string", "description": "A line or polygon layer."},
        "feature_id": {"type": "integer", "description": "The feature's id (the QGIS feature id)."},
        "line_wkt": {"type": "string", "description": "The reshaping line as WKT in the layer's CRS, for example LINESTRING(-1 5, 5 7, 11 5)."}},
     "required": ["layer_name", "feature_id", "line_wkt"]},
    keywords=["reshape", "reshape a feature", "reshape the polygon", "reshape the line", "cut a new edge", "change the outline"],
)
def reshape_geometry(layer_name, feature_id, line_wkt, confirmed=False):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    points, problem = lo.check_reshape(line_wkt)
    if problem:
        return {"error": problem}
    layer, err = _line_layer(layer_name, allow_polygon=True)
    if err:
        return err
    try:
        fid = int(feature_id)
    except (TypeError, ValueError):
        return {"error": "feature_id must be a whole number."}
    feature = layer.getFeature(fid)
    if not feature.isValid() or feature.geometry().isNull():
        return {"error": f"Feature {fid} was not found in '{layer_name}' or has no geometry."}
    is_polygon = QgsWkbTypes.geometryType(layer.wkbType()) == QgsWkbTypes.GeometryType.PolygonGeometry
    geometry = QgsGeometry(feature.geometry())
    label, before = ("area", geometry.area()) if is_polygon else ("length", geometry.length())
    if not confirmed:
        return preview("reshape_geometry", {"layer_name": layer_name, "feature_id": fid, "line_wkt": str(line_wkt)},
                       f"Reshape feature {fid} of '{layer_name}' with a {len(points)}-point line ({label} now {before:g}).",
                       f"layer.startEditing()\ngeometry = layer.getFeature({fid}).geometry()\ngeometry.reshapeGeometry(QgsLineString(...))\n"
                       "layer.changeGeometry(feature_id, geometry)\nlayer.commitChanges()")
    result = geometry.reshapeGeometry(QgsLineString([QgsPointXY(x, y) for x, y in points]))
    name = getattr(result, "name", None) or str(result)
    if name == "NothingHappened":
        return {"error": "Nothing was changed: the line does not cross this feature, so it reshapes nothing."}
    if not _success(result):
        return {"error": f"Nothing was changed: QGIS could not reshape with that line ({name})."}
    if not geometry.isGeosValid() and feature.geometry().isGeosValid():
        return {"error": "Nothing was changed: the result would not be a valid geometry."}
    problem, owned = _apply_changes(layer, "Cartogen AI: reshape", {fid: geometry})
    if problem:
        return {"error": problem}
    return _finish({"success": True, "layer_name": layer_name, "feature_id": fid, f"{label}_before": round(before, 6),
                    f"{label}_after": round(geometry.area() if is_polygon else geometry.length(), 6),
                    "undo": "undo_manual_edit steps it back while the layer is in edit mode."}, owned, layer)


@register_tool(
    "reverse_line",
    "Reverse the direction of the lines of a line layer (the first vertex becomes the last): all features, or only feature_ids. Use it when a one-way street, a river or a pipeline "
    "points the wrong way. Changes geometry: a preview with the number of features is shown for confirmation first, and the edit is one undoable step (undo_manual_edit).",
    {"type": "object", "properties": {
        "layer_name": {"type": "string", "description": "A line layer."},
        "feature_ids": {"type": "array", "items": {"type": "integer"}, "description": "Only these features (default: all)."}},
     "required": ["layer_name"]},
    keywords=["reverse a line", "reverse the line", "reverse the direction", "flip the direction", "wrong way", "reverse line direction"],
)
def reverse_line(layer_name, feature_ids=None, confirmed=False):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    layer, err = _line_layer(layer_name)
    if err:
        return err
    features, why = _features(layer, feature_ids)
    if why:
        return {"error": why}
    if not features:
        return {"error": f"'{layer_name}' has no features with a geometry to reverse."}
    if not confirmed:
        arguments = {"layer_name": layer_name}
        if feature_ids:
            arguments["feature_ids"] = [f.id() for f in features]
        return preview("reverse_line", arguments, f"Reverse the direction of {len(features)} feature(s) of '{layer_name}'.",
                       "layer.startEditing()\nfor f in features: reverse each part's vertex order\nlayer.changeGeometry(f.id(), geometry)\nlayer.commitChanges()")
    changes = {}
    for f in features:
        parts, multi = _line_parts(f.geometry())
        changes[f.id()] = _build_line([lo.reverse_points(p) for p in parts], multi)
    problem, owned = _apply_changes(layer, "Cartogen AI: reverse lines", changes)
    if problem:
        return {"error": problem}
    return _finish({"success": True, "layer_name": layer_name, "features_reversed": len(changes),
                    "undo": "undo_manual_edit steps it back while the layer is in edit mode."}, owned, layer)


@register_tool(
    "trim_extend_lines",
    "Close small gaps and overshoots between lines of a line layer: the two ends of every line move onto the nearest point of ANOTHER line when that point is within `tolerance` "
    "(layer units): a line that stops short is extended to it, a line that overshoots is trimmed back to where they cross. Only line ends move; no vertex is added or removed. "
    "Changes geometry: a preview with the number of ends that would move is shown for confirmation first, and the edit is one undoable step (undo_manual_edit).",
    {"type": "object", "properties": {
        "layer_name": {"type": "string", "description": "A line layer."},
        "tolerance": {"type": "number", "description": "The largest move of one end, in the layer's units (degrees on a geographic layer)."}},
     "required": ["layer_name", "tolerance"]},
    keywords=["trim lines", "extend lines", "trim and extend", "close the gaps between lines", "snap line ends", "undershoot", "overshoot", "dangles", "connect the line ends"],
)
def trim_extend_lines(layer_name, tolerance, confirmed=False):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    problem = lo.check_snap(tolerance)
    if problem:
        return {"error": problem}
    layer, err = _line_layer(layer_name)
    if err:
        return err
    problem = degrees_value_problem(layer, tolerance, "tolerance")
    if problem:
        return {"error": problem}
    tol = float(tolerance)
    features, _why = _features(layer, None)
    split = {f.id(): _line_parts(f.geometry()) for f in features}
    moves = lo.snap_ends([((fid, n), pts) for fid, (parts, _m) in split.items() for n, pts in enumerate(parts)], tol)
    ends = sum((a is not None) + (b is not None) for a, b in moves.values())
    if not moves:
        return {"success": True, "layer_name": layer_name, "ends_moved": 0, "features_changed": 0,
                "message": f"No line end is within {tol:g} of another line (or they already touch), so nothing needed changing."}
    changed = sorted({fid for fid, _n in moves})
    if not confirmed:
        return preview("trim_extend_lines", {"layer_name": layer_name, "tolerance": tol},
                       f"Move {ends} line end(s) of {len(changed)} feature(s) of '{layer_name}' onto the nearest other line within {tol:g}.",
                       "layer.startEditing()\nfor each end within tolerance: move it to the nearest point of another line\n"
                       "layer.changeGeometry(feature_id, geometry)\nlayer.commitChanges()")
    changes = {}
    for fid in changed:
        parts, multi = split[fid]
        parts = [list(p) for p in parts]
        for n, pts in enumerate(parts):
            first, last = moves.get((fid, n), (None, None))
            if first is not None:
                pts[0] = first
            if last is not None:
                pts[-1] = last
        changes[fid] = _build_line(parts, multi)
    problem, owned = _apply_changes(layer, "Cartogen AI: trim and extend lines", changes)
    if problem:
        return {"error": problem}
    return _finish({"success": True, "layer_name": layer_name, "ends_moved": ends, "features_changed": len(changed), "tolerance": tol,
                    "undo": "undo_manual_edit steps it back while the layer is in edit mode."}, owned, layer)


@register_tool(
    "offset_curve",
    "Make a parallel copy of every line of a line layer at `distance` (layer units; positive to the left of the line's direction, negative to the right) as a NEW layer; the input is "
    "not changed. join is round (default), miter or bevel. Attributes are copied. Lines that cannot be offset by that distance (for example a tight bend inwards) are counted in the reply.",
    {"type": "object", "properties": {
        "layer_name": {"type": "string", "description": "A line layer."},
        "distance": {"type": "number", "description": "Offset distance in the layer's units; negative = the other side."},
        "join": {"type": "string", "enum": list(lo.JOINS), "description": "Corner style (default round)."},
        "segments": {"type": "integer", "description": "Segments per quarter circle for round joins, 1 to 64 (default 8)."},
        "miter_limit": {"type": "number", "description": "Miter limit, 1 or more (default 2)."},
        "output_name": {"type": "string", "description": "Name of the new layer (default <layer>_offset)."}},
     "required": ["layer_name", "distance"]},
    keywords=["offset a line", "offset curve", "parallel line", "parallel copy", "offset the lines", "copy the line parallel"],
)
def offset_curve(layer_name, distance, join="round", segments=8, miter_limit=2.0, output_name=None):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    problem = lo.check_offset(distance, join, segments, miter_limit)
    if problem:
        return {"error": problem}
    layer, err = _line_layer(layer_name)
    if err:
        return err
    problem = degrees_value_problem(layer, distance, "distance")
    if problem:
        return {"error": problem}
    style = getattr(Qgis.JoinStyle, str(join or "round").strip().capitalize())
    base = (output_name or "").strip() or f"{layer_name}_offset"
    crs = layer.crs().authid() or "EPSG:4326"
    out = QgsVectorLayer(f"{QgsWkbTypes.displayString(layer.wkbType())}?crs={crs}", base, "memory")
    try:
        require_valid_layer(out)
    except ValueError as e:
        return {"error": str(e)}
    out.dataProvider().addAttributes(layer.fields().toList())
    out.updateFields()
    made, skipped = [], 0
    for f in layer.getFeatures():
        shifted = None if f.geometry().isNull() else f.geometry().offsetCurve(float(distance), int(float(segments)), style, float(miter_limit))
        if shifted is None or shifted.isNull() or shifted.isEmpty():
            skipped += 1
            continue
        if shifted.isMultipart() != QgsWkbTypes.isMultiType(layer.wkbType()):
            (shifted.convertToMultiType if QgsWkbTypes.isMultiType(layer.wkbType()) else shifted.convertToSingleType)()
        new = QgsFeature(out.fields())
        new.setAttributes(f.attributes())
        new.setGeometry(shifted)
        made.append(new)
    out.dataProvider().addFeatures(made)
    QgsProject.instance().addMapLayer(out)
    result = {"success": True, "layer_name": base, "features": len(made), "skipped": skipped, "distance": float(distance), "join": str(join or "round").lower(),
              "note": "Positive distances are to the left of each line's direction, negative to the right."}
    if skipped:
        result["skipped_note"] = f"{skipped} line(s) could not be offset by that distance and are not in the new layer."
    if layer.crs().isValid() and layer.crs().isGeographic():
        result["note_crs"] = "The layer is in a geographic CRS, so the distance is in degrees."
    return result
