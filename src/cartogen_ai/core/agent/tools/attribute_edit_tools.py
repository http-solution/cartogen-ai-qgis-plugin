"""M3 (roadmap 2026-10-14): selection, attribute and feature editing through the chat.

Why: the coverage audit listed these as MISSING: clear/select all, select by any expression, delete features, edit one value, add /
rename / delete a field, add a feature from WKT. Before 1.16.0-rc4 a script could do them; each is now a checked tool.

Rules every tool here follows:
  * every write runs through _edit_session.edit_command (one atomic edit command; a layer the user already has in edit mode keeps its
    session and the reply says the change is unsaved; a failed commit rolls back and says why);
  * every change that removes or overwrites data returns PREVIEW_REQUIRED first (the user's Apply button sets `confirmed`, the model
    cannot) and reports exactly how many features or values it would touch;
  * every expression the model wrote goes through validators/expression_screen.py;
  * nothing deletes "everything" by default: delete_features needs an expression or only_selected.

The pure helpers (value coercion, previews, field specs) are unit-tested offline; the tools themselves by
tests/test_attribute_edit_tools_live.py, whose first CI run is its first execution (written without a QGIS install)."""
from ...validators.expression_screen import screen_expression
from .registry import register_tool

try:
    from qgis.core import QgsExpression, QgsFeature, QgsFeatureRequest, QgsGeometry, QgsProject, QgsVectorLayer
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False

SELECT_MODES = ("replace", "add", "remove", "intersect")
FIELD_TYPE_WORDS = {"string": "String", "text": "String", "integer": "Int", "int": "Int", "long": "LongLong", "bigint": "LongLong",
                    "double": "Double", "float": "Double", "real": "Double", "decimal": "Double", "date": "Date", "datetime": "DateTime"}


def preview(tool, arguments, rationale, snippet):
    """The PREVIEW_REQUIRED result the Apply button turns into a confirmed call."""
    return {"status": "PREVIEW_REQUIRED", "requires_confirmation": True, "is_destructive": True, "tool_name": tool,
            "arguments": {**arguments, "confirmed": True}, "code_snippet": snippet, "rationale": rationale,
            "message": f"Confirmation required: {rationale}"}


def coerce_value(value, kind):
    """(converted value, error) for a field of `kind` (a FIELD_TYPE_WORDS value or 'Numeric'); None stays NULL. Pure.

    Refuses rather than guesses: 'abc' into an integer field is an error, not a NULL, so a typo cannot silently blank a value."""
    if value is None or (isinstance(value, str) and value.strip().lower() in ("null", "none")):
        return None, None
    try:
        if kind in ("Int", "LongLong"):
            number = float(value)
            if number != int(number):
                return None, f"'{value}' is not a whole number."
            return int(number), None
        if kind in ("Double", "Numeric"):
            return float(value), None
    except (TypeError, ValueError, OverflowError):
        return None, f"'{value}' is not a number."
    return str(value), None


def new_field_type(word):
    return FIELD_TYPE_WORDS.get(str(word or "string").strip().lower())


def _layer(layer_name):
    layers = QgsProject.instance().mapLayersByName(layer_name) if QGIS_AVAILABLE else []
    if not layers or not isinstance(layers[0], QgsVectorLayer):
        return None, {"error": f"Vector layer '{layer_name}' not found."}
    return layers[0], None


def _expression_ok(text):
    blocked = screen_expression(text)
    if blocked:
        return blocked
    parsed = QgsExpression(text)
    if parsed.hasParserError():
        return f"Invalid expression: {parsed.parserErrorString()}"
    return None


def _matching_ids(layer, expression=None, only_selected=False):
    if only_selected:
        return list(layer.selectedFeatureIds())
    return [f.id() for f in layer.getFeatures(QgsFeatureRequest(QgsExpression(expression)))]


def _unsaved_note(owned):
    return None if owned else ("The layer is already in edit mode, so the change is in your edit session and is NOT saved: "
                               "save or discard the layer edits yourself.")


@register_tool(
    "select_by_expression",
    "Select features of a layer with any QGIS expression (for example \"population\" > 1000 AND \"type\" = 'school'). mode: replace "
    "(default), add, remove or intersect with the current selection.",
    {"type": "object", "properties": {"layer_name": {"type": "string"}, "expression": {"type": "string"},
                                      "mode": {"type": "string", "description": "replace, add, remove or intersect"}},
     "required": ["layer_name", "expression"]})
def select_by_expression(layer_name, expression, mode="replace"):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    layer, err = _layer(layer_name)
    if err:
        return err
    mode = str(mode or "replace").lower()
    if mode not in SELECT_MODES:
        return {"error": f"mode must be one of {', '.join(SELECT_MODES)}."}
    problem = _expression_ok(expression)
    if problem:
        return {"error": problem}
    from qgis.core import Qgis
    behaviour = {"replace": Qgis.SelectBehavior.SetSelection, "add": Qgis.SelectBehavior.AddToSelection,
                 "remove": Qgis.SelectBehavior.RemoveFromSelection, "intersect": Qgis.SelectBehavior.IntersectSelection}[mode]
    layer.selectByExpression(expression, behaviour)
    return {"success": True, "layer_name": layer_name, "mode": mode, "selected_count": layer.selectedFeatureCount(),
            "expression": expression}


@register_tool(
    "select_all_features",
    "Select every feature of a layer.",
    {"type": "object", "properties": {"layer_name": {"type": "string"}}, "required": ["layer_name"]})
def select_all_features(layer_name):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    layer, err = _layer(layer_name)
    if err:
        return err
    layer.selectAll()
    return {"success": True, "layer_name": layer_name, "selected_count": layer.selectedFeatureCount()}


@register_tool(
    "clear_selection",
    "Deselect all features: of one layer, or of every layer in the project when layer_name is omitted.",
    {"type": "object", "properties": {"layer_name": {"type": "string"}}, "required": []})
def clear_selection(layer_name=None):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    if layer_name:
        layer, err = _layer(layer_name)
        if err:
            return err
        layer.removeSelection()
        return {"success": True, "cleared_layers": [layer_name]}
    cleared = []
    for lyr in QgsProject.instance().mapLayers().values():
        if isinstance(lyr, QgsVectorLayer) and lyr.selectedFeatureCount():
            lyr.removeSelection()
            cleared.append(lyr.name())
    return {"success": True, "cleared_layers": cleared}


@register_tool(
    "delete_features",
    "Delete features from a layer: those matching an expression, or the currently selected ones (only_selected). Destructive: a preview "
    "with the exact count is shown for confirmation first. Never deletes everything unless the expression says so.",
    {"type": "object", "properties": {"layer_name": {"type": "string"}, "expression": {"type": "string"}, "only_selected": {"type": "boolean"}},
     "required": ["layer_name"]})
def delete_features(layer_name, expression=None, only_selected=False, confirmed=False):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    layer, err = _layer(layer_name)
    if err:
        return err
    if bool(expression) == bool(only_selected):
        return {"error": "Give exactly one of expression or only_selected=true."}
    if expression:
        problem = _expression_ok(expression)
        if problem:
            return {"error": problem}
    ids = _matching_ids(layer, expression, only_selected)
    if not ids:
        return {"error": "No features match, nothing to delete." if expression else "Nothing is selected, nothing to delete."}
    what = f"matching {expression}" if expression else "currently selected"
    if not confirmed:
        return preview("delete_features", {"layer_name": layer_name, "expression": expression, "only_selected": only_selected},
                       f"Delete {len(ids)} of {layer.featureCount()} features ({what}) from '{layer_name}'.",
                       f"layer.startEditing()\nlayer.deleteFeatures({len(ids)} ids)  # {what}\nlayer.commitChanges()")
    from ._edit_session import EditError, edit_command
    try:
        with edit_command(layer, "Cartogen AI: delete features") as owned:
            if not layer.deleteFeatures(ids):
                raise EditError("the layer refused the deletion (read-only source?).")
    except EditError as e:
        return {"error": f"Nothing was deleted: {e}"}
    out = {"success": True, "layer_name": layer_name, "deleted": len(ids), "remaining": layer.featureCount()}
    if _unsaved_note(owned):
        out["note"] = _unsaved_note(owned)
    return out


@register_tool(
    "set_attribute_value",
    "Set one field to a value on specific features: pick them by feature_id or by an expression. Numeric fields need numbers; a typo is "
    "refused, not turned into NULL. Use the string null to clear a value. Changes data: a preview with the count is shown first.",
    {"type": "object", "properties": {"layer_name": {"type": "string"}, "field": {"type": "string"}, "value": {"type": "string"},
                                      "feature_id": {"type": "integer"}, "expression": {"type": "string"}},
     "required": ["layer_name", "field", "value"]})
def set_attribute_value(layer_name, field, value, feature_id=None, expression=None, confirmed=False):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    layer, err = _layer(layer_name)
    if err:
        return err
    if (feature_id is None) == (not expression):
        return {"error": "Give exactly one of feature_id or expression."}
    index = layer.fields().indexOf(field)
    if index < 0:
        return {"error": f"Field '{field}' not found. The layer has: {', '.join(layer.fields().names())}."}
    field_def = layer.fields().at(index)
    kind = ("Int" if "int" in field_def.typeName().lower() else "Numeric") if field_def.isNumeric() else "String"
    converted, bad = coerce_value(value, kind)
    if bad:
        return {"error": f"Field '{field}' is numeric: {bad}"}
    if expression:
        problem = _expression_ok(expression)
        if problem:
            return {"error": problem}
        ids = _matching_ids(layer, expression)
    else:
        ids = [feature_id] if layer.getFeature(feature_id).isValid() else []
    if not ids:
        return {"error": "No feature matches, nothing was changed."}
    if not confirmed:
        return preview("set_attribute_value", {"layer_name": layer_name, "field": field, "value": value, "feature_id": feature_id,
                                               "expression": expression},
                       f"Set '{field}' to {converted!r} on {len(ids)} feature(s) of '{layer_name}'.",
                       f"layer.startEditing()\nlayer.changeAttributeValue(fid, {index}, {converted!r})  # {len(ids)} feature(s)\nlayer.commitChanges()")
    from ._edit_session import EditError, edit_command, set_value
    try:
        with edit_command(layer, "Cartogen AI: set attribute value") as owned:
            for fid in ids:
                set_value(layer, fid, index, converted)
    except EditError as e:
        return {"error": f"Nothing was changed: {e}"}
    out = {"success": True, "layer_name": layer_name, "field": field, "features_updated": len(ids)}
    if _unsaved_note(owned):
        out["note"] = _unsaved_note(owned)
    return out


@register_tool(
    "add_field",
    "Add an empty field to a layer. field_type: string, integer, long, double, date or datetime.",
    {"type": "object", "properties": {"layer_name": {"type": "string"}, "field_name": {"type": "string"}, "field_type": {"type": "string"}},
     "required": ["layer_name", "field_name"]})
def add_field(layer_name, field_name, field_type="string"):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    layer, err = _layer(layer_name)
    if err:
        return err
    word = new_field_type(field_type)
    if word is None:
        return {"error": f"field_type '{field_type}' is not supported. Use string, integer, long, double, date or datetime."}
    from .data_source_tools import build_field_specs
    if build_field_specs([{"name": field_name}])[1]:
        return {"error": build_field_specs([{"name": field_name}])[1]}
    if layer.fields().indexOf(field_name) >= 0:
        return {"error": f"Field '{field_name}' already exists."}
    from qgis.core import QgsField
    from qgis.PyQt.QtCore import QVariant
    qtype = getattr(QVariant, word)   # same enum access as _edit_session.add_numeric_field, which CI exercises
    from ._edit_session import EditError, edit_command
    try:
        with edit_command(layer, "Cartogen AI: add field") as owned:
            if not layer.addAttribute(QgsField(field_name, qtype)):
                raise EditError("the layer refused the new field (read-only or does not support new fields).")
            layer.updateFields()
    except EditError as e:
        return {"error": f"The field was not added: {e}"}
    out = {"success": True, "layer_name": layer_name, "field": field_name, "type": word}
    if _unsaved_note(owned):
        out["note"] = _unsaved_note(owned)
    return out


@register_tool(
    "rename_field",
    "Rename a field of a layer.",
    {"type": "object", "properties": {"layer_name": {"type": "string"}, "field_name": {"type": "string"}, "new_name": {"type": "string"}},
     "required": ["layer_name", "field_name", "new_name"]})
def rename_field(layer_name, field_name, new_name):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    layer, err = _layer(layer_name)
    if err:
        return err
    index = layer.fields().indexOf(field_name)
    if index < 0:
        return {"error": f"Field '{field_name}' not found. The layer has: {', '.join(layer.fields().names())}."}
    from .data_source_tools import build_field_specs
    problem = build_field_specs([{"name": new_name}])[1]
    if problem:
        return {"error": problem}
    if layer.fields().indexOf(new_name) >= 0:
        return {"error": f"A field called '{new_name}' already exists."}
    from ._edit_session import EditError, edit_command
    try:
        with edit_command(layer, "Cartogen AI: rename field") as owned:
            if not layer.renameAttribute(index, new_name):
                raise EditError("the layer refused the rename (read-only or the provider cannot rename fields).")
    except EditError as e:
        return {"error": f"The field was not renamed: {e}"}
    out = {"success": True, "layer_name": layer_name, "old_name": field_name, "new_name": new_name}
    if _unsaved_note(owned):
        out["note"] = _unsaved_note(owned)
    return out


@register_tool(
    "delete_field",
    "Delete a field (column) and all its values from a layer. Destructive: a preview is shown for confirmation first.",
    {"type": "object", "properties": {"layer_name": {"type": "string"}, "field_name": {"type": "string"}},
     "required": ["layer_name", "field_name"]})
def delete_field(layer_name, field_name, confirmed=False):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    layer, err = _layer(layer_name)
    if err:
        return err
    index = layer.fields().indexOf(field_name)
    if index < 0:
        return {"error": f"Field '{field_name}' not found. The layer has: {', '.join(layer.fields().names())}."}
    if not confirmed:
        return preview("delete_field", {"layer_name": layer_name, "field_name": field_name},
                       f"Delete the field '{field_name}' and its values on {layer.featureCount()} feature(s) of '{layer_name}'.",
                       f"layer.startEditing()\nlayer.deleteAttribute({index})  # {field_name}\nlayer.commitChanges()")
    from ._edit_session import EditError, edit_command
    try:
        with edit_command(layer, "Cartogen AI: delete field") as owned:
            if not layer.deleteAttribute(index):
                raise EditError("the layer refused to delete the field (read-only, or it is a key field).")
    except EditError as e:
        return {"error": f"The field was not deleted: {e}"}
    out = {"success": True, "layer_name": layer_name, "deleted_field": field_name}
    if _unsaved_note(owned):
        out["note"] = _unsaved_note(owned)
    return out


@register_tool(
    "add_feature_from_wkt",
    "Add one feature to an existing layer from WKT geometry (POINT, LINESTRING, POLYGON ...). crs is the CRS of the WKT coordinates "
    "(default: the layer's own); it is transformed in code. attributes is {field: value}. The geometry type must match the layer.",
    {"type": "object", "properties": {"layer_name": {"type": "string"}, "wkt": {"type": "string"},
                                      "attributes": {"type": "object"}, "crs": {"type": "string", "description": "e.g. EPSG:4326"}},
     "required": ["layer_name", "wkt"]})
def add_feature_from_wkt(layer_name, wkt, attributes=None, crs=None):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    from qgis.core import QgsCoordinateReferenceSystem, QgsCoordinateTransform
    layer, err = _layer(layer_name)
    if err:
        return err
    geometry = QgsGeometry.fromWkt(str(wkt or ""))
    if geometry is None or geometry.isNull() or geometry.isEmpty():
        return {"error": "The WKT could not be read. Example: POINT(35.9 31.95) or POLYGON((0 0, 1 0, 1 1, 0 0))."}
    if geometry.type() != layer.geometryType():
        return {"error": f"The WKT is not the geometry type of '{layer_name}' (points, lines and polygons cannot be mixed in one layer)."}
    if crs:
        source = QgsCoordinateReferenceSystem(crs)
        if not source.isValid():
            return {"error": f"Unknown crs '{crs}'. Use a code such as EPSG:4326."}
        if source != layer.crs():
            geometry.transform(QgsCoordinateTransform(source, layer.crs(), QgsProject.instance()))
    feature = QgsFeature(layer.fields())
    feature.setGeometry(geometry)
    names = set(layer.fields().names())
    unknown = [k for k in (attributes or {}) if k not in names]
    if unknown:
        return {"error": f"Unknown field(s): {', '.join(unknown)}. The layer has: {', '.join(layer.fields().names())}."}
    for key, raw in (attributes or {}).items():
        field = layer.fields().at(layer.fields().indexOf(key))
        value, bad = coerce_value(raw, "Numeric" if field.isNumeric() else "String")
        if bad:
            return {"error": f"Field '{key}' is numeric: {bad}"}
        feature.setAttribute(key, value)
    from ._edit_session import EditError, begin_feature_edits, finish_feature_edits
    try:
        owned = begin_feature_edits(layer)
        if not layer.addFeature(feature):
            if owned:
                layer.rollBack()
            return {"error": "The layer refused the new feature (read-only source?)."}
        finish_feature_edits(layer, owned)
    except EditError as e:
        return {"error": f"The feature was not added: {e}"}
    out = {"success": True, "layer_name": layer_name, "feature_count": layer.featureCount()}
    if _unsaved_note(owned):
        out["note"] = _unsaved_note(owned)
    return out
