"""M3 (roadmap completion plan, package A): the editing operations that were still MISSING after attribute_edit_tools.py.

set_layer_filter        provider filter (definition query) on a layer, or clear it
transform_features      move / rotate / scale the matching or selected features
merge_features          union the matching or selected features into one
split_features_by_line  cut the matching or selected features along a line
undo_manual_edit / redo_manual_edit   step through the layer's own edit history while it is in edit mode
change_field_type       convert a field to string / integer / long / double
set_layer_editing       start editing, save the edits, or discard them

Same rules as attribute_edit_tools.py: every data-changing write goes through _edit_session.edit_command, anything that removes or rewrites
data returns PREVIEW_REQUIRED with exact counts first, model-written expressions pass the expression screen, and a layer the user already
has in edit mode keeps its session (the reply says the change is unsaved). The validation is pure and tested offline (edit_options.py);
the QGIS calls are read back from real layers by tests/test_edit_ops_tools_live.py, whose first CI run is its first execution."""
from .attribute_edit_tools import _expression_ok, _layer, _matching_ids, _unsaved_note, preview
from .edit_options import conversion_kind, convert_value, describe_transform, filter_violation, transform_options
from .registry import register_tool

try:
    from qgis.core import Qgis, QgsFeatureRequest, QgsField, QgsGeometry, QgsPointXY, QgsProject
    from qgis.PyQt.QtCore import QVariant
    from qgis.PyQt.QtGui import QTransform
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False

_SELECTOR = {"layer_name": {"type": "string"}, "expression": {"type": "string", "description": "QGIS expression choosing the features"},
             "only_selected": {"type": "boolean", "description": "use the currently selected features instead"}}


def _targets(layer, expression, only_selected, what):
    """(ids, error): exactly one of expression / only_selected, both checked, at least one feature."""
    if bool(expression) == bool(only_selected):
        return None, {"error": "Give exactly one of expression or only_selected=true."}
    if expression:
        problem = _expression_ok(expression)
        if problem:
            return None, {"error": problem}
    ids = _matching_ids(layer, expression, only_selected)
    if not ids:
        return None, {"error": f"No features match, nothing to {what}." if expression else f"Nothing is selected, nothing to {what}."}
    return ids, None


def _is_geographic(layer):
    return bool(layer.crs().isValid() and layer.crs().isGeographic())


def _finish(out, owned):
    if _unsaved_note(owned):
        out["note"] = _unsaved_note(owned)
    return out


@register_tool(
    "set_layer_filter",
    "Set or clear a layer's filter (definition query): only features matching the filter are shown and used. The filter is a plain "
    "condition in the data source's own syntax, such as \"population\" > 1000. Statements, comments and semicolons are refused. "
    "clear=true removes the filter. The data is not changed.",
    {"type": "object", "properties": {"layer_name": {"type": "string"}, "filter": {"type": "string"},
                                      "clear": {"type": "boolean"}}, "required": ["layer_name"]})
def set_layer_filter(layer_name, filter=None, clear=False):  # noqa: A002 - the parameter name is the tool's public argument
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    layer, err = _layer(layer_name)
    if err:
        return err
    previous = layer.subsetString()
    condition = ""
    if not clear:
        problem = filter_violation(filter)
        if problem:
            return {"error": problem}
        condition = filter
    if not layer.setSubsetString(condition):
        layer.setSubsetString(previous)
        return {"error": "The data source rejected that filter (check the field names and quoting); the previous filter is unchanged.",
                "filter": previous}
    return {"success": True, "layer_name": layer_name, "filter": layer.subsetString(), "previous_filter": previous,
            "feature_count": layer.featureCount()}


@register_tool(
    "transform_features",
    "Move, rotate and/or scale features of a layer: those matching an expression, or the selected ones (only_selected). move_x and "
    "move_y are in the layer's units, rotate_degrees is clockwise about each feature's centre, scale_factor scales about each feature's "
    "centre. Changes geometry: a preview with the exact count is shown for confirmation first.",
    {"type": "object", "properties": {**_SELECTOR, "move_x": {"type": "number"}, "move_y": {"type": "number"},
                                      "rotate_degrees": {"type": "number"}, "scale_factor": {"type": "number"}},
     "required": ["layer_name"]})
def transform_features(layer_name, expression=None, only_selected=False, move_x=None, move_y=None, rotate_degrees=None,
                       scale_factor=None, confirmed=False):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    layer, err = _layer(layer_name)
    if err:
        return err
    opts, problem = transform_options(move_x, move_y, rotate_degrees, scale_factor)
    if problem:
        return {"error": problem}
    ids, err = _targets(layer, expression, only_selected, "transform")
    if err:
        return err
    units = "degrees" if _is_geographic(layer) else "layer units"
    if not confirmed:
        out = preview("transform_features", {"layer_name": layer_name, "expression": expression, "only_selected": only_selected, **opts},
                      f"{describe_transform(opts).capitalize()} for {len(ids)} feature(s) of '{layer_name}' ({units}).",
                      f"layer.startEditing()\nfor f in {len(ids)} features: geometry.translate / rotate / transform\nlayer.commitChanges()")
        if _is_geographic(layer):
            out["rationale"] += " The layer is in a geographic CRS, so distances are in degrees and shapes distort away from the equator."
        return out
    from ._edit_session import EditError, edit_command
    done = 0
    try:
        with edit_command(layer, "Cartogen AI: transform features") as owned:
            for feature in layer.getFeatures(QgsFeatureRequest().setFilterFids(ids)):
                geometry = QgsGeometry(feature.geometry())
                if geometry.isNull():
                    continue
                centre = geometry.boundingBox().center()
                if "scale_factor" in opts:
                    s = opts["scale_factor"]
                    matrix = QTransform().translate(centre.x(), centre.y()).scale(s, s).translate(-centre.x(), -centre.y())
                    if geometry.transform(matrix) != Qgis.GeometryOperationResult.Success:
                        raise EditError(f"feature {feature.id()} could not be scaled.")
                if "rotate_degrees" in opts and geometry.rotate(opts["rotate_degrees"], QgsPointXY(centre)) != Qgis.GeometryOperationResult.Success:
                    raise EditError(f"feature {feature.id()} could not be rotated.")
                if ("move_x" in opts or "move_y" in opts) and geometry.translate(
                        opts.get("move_x", 0.0), opts.get("move_y", 0.0)) != Qgis.GeometryOperationResult.Success:
                    raise EditError(f"feature {feature.id()} could not be moved.")
                if not layer.changeGeometry(feature.id(), geometry):
                    raise EditError("the layer refused the geometry change (read-only source?).")
                done += 1
    except EditError as e:
        return {"error": f"Nothing was changed: {e}"}
    return _finish({"success": True, "layer_name": layer_name, "transformed": done, "applied": describe_transform(opts)}, owned)


@register_tool(
    "merge_features",
    "Merge (union) several features of a layer into one: those matching an expression or the selected ones. The first feature keeps its "
    "attributes and gets the combined geometry; the others are deleted. Needs at least two features. Destructive: a preview is shown first.",
    {"type": "object", "properties": _SELECTOR, "required": ["layer_name"]})
def merge_features(layer_name, expression=None, only_selected=False, confirmed=False):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    layer, err = _layer(layer_name)
    if err:
        return err
    ids, err = _targets(layer, expression, only_selected, "merge")
    if err:
        return err
    if len(ids) < 2:
        return {"error": "Merging needs at least two features."}
    ids = sorted(ids)
    if not confirmed:
        return preview("merge_features", {"layer_name": layer_name, "expression": expression, "only_selected": only_selected},
                       f"Merge {len(ids)} features of '{layer_name}' into feature {ids[0]} (it keeps its attributes; the other "
                       f"{len(ids) - 1} are deleted).",
                       f"layer.startEditing()\nlayer.changeGeometry({ids[0]}, unaryUnion)\nlayer.deleteFeatures({len(ids) - 1} ids)\n"
                       "layer.commitChanges()")
    geometries = [f.geometry() for f in layer.getFeatures(QgsFeatureRequest().setFilterFids(ids)) if not f.geometry().isNull()]
    if len(geometries) != len(ids):
        return {"error": "Some of those features have no geometry, so they cannot be merged."}
    merged = QgsGeometry.unaryUnion(geometries)
    if merged.isNull() or merged.isEmpty():
        return {"error": "The union of those features is empty."}
    from ._edit_session import EditError, edit_command
    try:
        with edit_command(layer, "Cartogen AI: merge features") as owned:
            if not layer.changeGeometry(ids[0], merged):
                raise EditError("the layer refused the geometry change (read-only source, or the geometry type does not fit the layer).")
            if not layer.deleteFeatures(ids[1:]):
                raise EditError("the layer refused to delete the merged features.")
    except EditError as e:
        return {"error": f"Nothing was merged: {e}"}
    return _finish({"success": True, "layer_name": layer_name, "kept_feature_id": ids[0], "merged": len(ids),
                    "remaining": layer.featureCount()}, owned)


@register_tool(
    "split_features_by_line",
    "Cut features of a polygon or line layer along a line given as WKT (LINESTRING(x1 y1, x2 y2, ...)) in the layer's CRS or in the CRS "
    "given. Splits the features matching an expression or the selected ones that the line crosses. Changes data: a preview is shown first.",
    {"type": "object", "properties": {**_SELECTOR, "line_wkt": {"type": "string"}, "crs": {"type": "string", "description": "e.g. EPSG:4326"}},
     "required": ["layer_name", "line_wkt"]})
def split_features_by_line(layer_name, line_wkt, expression=None, only_selected=False, crs=None, confirmed=False):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    layer, err = _layer(layer_name)
    if err:
        return err
    if layer.geometryType() not in (Qgis.GeometryType.Line, Qgis.GeometryType.Polygon):
        return {"error": "Only line and polygon layers can be split."}
    line = QgsGeometry.fromWkt(str(line_wkt or ""))
    if line.isNull() or line.wkbType() not in (Qgis.WkbType.LineString, Qgis.WkbType.LineString25D, Qgis.WkbType.LineStringZ):
        return {"error": "line_wkt must be a LINESTRING, for example LINESTRING(0 0, 10 10)."}
    if crs:
        from qgis.core import QgsCoordinateReferenceSystem, QgsCoordinateTransform
        source = QgsCoordinateReferenceSystem(crs)
        if not source.isValid():
            return {"error": f"CRS '{crs}' is not valid."}
        if source != layer.crs() and line.transform(QgsCoordinateTransform(source, layer.crs(), QgsProject.instance())) != 0:
            return {"error": "The line could not be transformed to the layer's CRS."}
    ids, err = _targets(layer, expression, only_selected, "split")
    if err:
        return err
    if not confirmed:
        return preview("split_features_by_line",
                       {"layer_name": layer_name, "line_wkt": line_wkt, "crs": crs, "expression": expression, "only_selected": only_selected},
                       f"Split up to {len(ids)} feature(s) of '{layer_name}' along the line; features the line does not cross stay as they are.",
                       f"layer.startEditing()\nlayer.selectByIds({len(ids)} ids)\nlayer.splitFeatures(line_points)\nlayer.commitChanges()")
    points = [QgsPointXY(p.x(), p.y()) for p in line.asPolyline()]
    before = layer.featureCount()
    previous_selection = list(layer.selectedFeatureIds())
    from ._edit_session import EditError, edit_command
    try:
        with edit_command(layer, "Cartogen AI: split features") as owned:
            layer.selectByIds(ids)
            result = layer.splitFeatures(points, False)
            if result != Qgis.GeometryOperationResult.Success:
                raise EditError(_split_message(result))
    except EditError as e:
        layer.selectByIds(previous_selection)
        return {"error": f"Nothing was split: {e}"}
    layer.selectByIds(previous_selection)
    return _finish({"success": True, "layer_name": layer_name, "features_before": before, "features_after": layer.featureCount()}, owned)


def _split_message(result):
    names = {name: getattr(Qgis.GeometryOperationResult, name, None) for name in
             ("NothingHappened", "InvalidInputGeometryType", "InvalidBaseGeometry", "InvalidInput", "GeometryEngineError", "AddPartSelectedGeometryNotFound")}
    for name, value in names.items():
        if value is not None and value == result:
            return {"NothingHappened": "the line does not cross any of those features.",
                    "InvalidInputGeometryType": "the layer's geometry type cannot be split.",
                    "InvalidBaseGeometry": "a feature has an invalid geometry; fix it first.",
                    "InvalidInput": "the splitting line is not valid.",
                    "GeometryEngineError": "the geometry engine failed on that line."}.get(name, f"the split failed ({name}).")
    return "the split failed."


def _undo_stack(layer_name, action):
    """(layer, stack, error). Only a layer in edit mode has a history this tool may step through."""
    layer, err = _layer(layer_name)
    if err:
        return None, None, err
    if not layer.isEditable():
        return None, None, {"error": f"'{layer_name}' is not in edit mode, so it has no manual edits to {action}. Use undo_last_operation "
                                     "to undo something the assistant did."}
    return layer, layer.undoStack(), None


@register_tool(
    "undo_manual_edit",
    "Undo the last edit step on a layer that is in edit mode (the layer's own undo history, including edits made by hand). Use "
    "undo_last_operation for assistant operations on a layer not in edit mode.",
    {"type": "object", "properties": {"layer_name": {"type": "string"}}, "required": ["layer_name"]})
def undo_manual_edit(layer_name):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    _layer_obj, stack, err = _undo_stack(layer_name, "undo")
    if err:
        return err
    if not stack.canUndo():
        return {"error": "There is nothing to undo on that layer."}
    text = stack.undoText()
    stack.undo()
    return {"success": True, "layer_name": layer_name, "undone": text, "can_undo_more": stack.canUndo(), "can_redo": stack.canRedo()}


@register_tool(
    "redo_manual_edit",
    "Redo the last undone edit step on a layer that is in edit mode.",
    {"type": "object", "properties": {"layer_name": {"type": "string"}}, "required": ["layer_name"]})
def redo_manual_edit(layer_name):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    _layer_obj, stack, err = _undo_stack(layer_name, "redo")
    if err:
        return err
    if not stack.canRedo():
        return {"error": "There is nothing to redo on that layer."}
    text = stack.redoText()
    stack.redo()
    return {"success": True, "layer_name": layer_name, "redone": text, "can_undo": stack.canUndo(), "can_redo_more": stack.canRedo()}


@register_tool(
    "change_field_type",
    "Change the data type of a field to string, integer, long or double, converting the values. Values that cannot be converted become "
    "NULL and numbers lose their fraction when going to integer: the preview says how many. The field moves to the end of the table.",
    {"type": "object", "properties": {"layer_name": {"type": "string"}, "field": {"type": "string"}, "new_type": {"type": "string"}},
     "required": ["layer_name", "field", "new_type"]})
def change_field_type(layer_name, field, new_type, confirmed=False):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    layer, err = _layer(layer_name)
    if err:
        return err
    index = layer.fields().indexOf(field)
    if index < 0:
        return {"error": f"Field '{field}' not found. The layer has: {', '.join(layer.fields().names())}."}
    kind = conversion_kind(new_type)
    if kind is None:
        return {"error": f"new_type '{new_type}' is not supported. Use string, integer, long or double."}
    if index in layer.primaryKeyAttributes():
        return {"error": f"'{field}' is a key field and cannot be converted."}
    values = [(f.id(), f[field]) for f in layer.getFeatures()]
    converted = [(fid, *convert_value(v, kind)) for fid, v in values]
    lossy = sum(1 for _, _, bad in converted if bad)
    if not confirmed:
        note = f" {lossy} value(s) cannot be converted exactly (they become NULL or lose their fraction)." if lossy else ""
        return preview("change_field_type", {"layer_name": layer_name, "field": field, "new_type": new_type},
                       f"Convert '{field}' to {kind} on {len(values)} feature(s) of '{layer_name}'.{note} The field moves to the end of the table.",
                       f"layer.startEditing()\nadd temp field, copy converted values, delete '{field}', rename temp\nlayer.commitChanges()")
    temp = f"{field}_conv_tmp"
    while layer.fields().indexOf(temp) >= 0:
        temp += "_"
    qtype = getattr(QVariant, kind)
    from ._edit_session import EditError, edit_command
    try:
        with edit_command(layer, "Cartogen AI: change field type") as owned:
            if not layer.addAttribute(QgsField(temp, qtype)):
                raise EditError("the layer refused the new field (read-only or no support for new fields).")
            layer.updateFields()
            new_index = layer.fields().indexOf(temp)
            for fid, value, _bad in converted:
                if not layer.changeAttributeValue(fid, new_index, value):
                    raise EditError("the layer refused a converted value.")
            if not layer.deleteAttribute(layer.fields().indexOf(field)):
                raise EditError("the layer refused to remove the old field (the provider cannot delete fields?).")
            layer.updateFields()
            if not layer.renameAttribute(layer.fields().indexOf(temp), field):
                raise EditError("the layer refused to rename the converted field (the provider cannot rename fields?).")
            layer.updateFields()
    except EditError as e:
        return {"error": f"The field was not converted: {e}"}
    return _finish({"success": True, "layer_name": layer_name, "field": field, "new_type": kind, "values": len(values),
                    "became_null_or_rounded": lossy}, owned)


@register_tool(
    "set_layer_editing",
    "Start editing a layer, save its edits, or discard them (action: start, save or discard). Discarding unsaved edits is destructive "
    "and needs confirmation.",
    {"type": "object", "properties": {"layer_name": {"type": "string"}, "action": {"type": "string", "description": "start, save or discard"}},
     "required": ["layer_name", "action"]})
def set_layer_editing(layer_name, action, confirmed=False):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    layer, err = _layer(layer_name)
    if err:
        return err
    action = str(action or "").strip().lower()
    if action == "start":
        if layer.isEditable():
            return {"success": True, "layer_name": layer_name, "editing": True, "note": "The layer was already in edit mode."}
        if not layer.startEditing():
            return {"error": "The layer could not be switched to edit mode (is the source read-only?)."}
        return {"success": True, "layer_name": layer_name, "editing": True}
    if action in ("save", "discard"):
        if not layer.isEditable():
            return {"error": f"'{layer_name}' is not in edit mode."}
        if action == "save":
            if not layer.commitChanges():
                errors = "; ".join(str(e) for e in layer.commitErrors())
                return {"error": "The provider rejected the edits" + (f": {errors}" if errors else ".") + " The layer is still in edit mode."}
            return {"success": True, "layer_name": layer_name, "editing": False, "saved": True}
        if layer.isModified() and not confirmed:
            return preview("set_layer_editing", {"layer_name": layer_name, "action": "discard"},
                           f"Discard all unsaved edits on '{layer_name}' and leave edit mode.", "layer.rollBack()")
        layer.rollBack()
        return {"success": True, "layer_name": layer_name, "editing": False, "discarded": True}
    return {"error": "action must be start, save or discard."}

