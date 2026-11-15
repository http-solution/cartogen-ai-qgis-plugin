"""copy_features_between_layers (PLAN-023 R9-4): copy the selected, filtered or all features of one vector layer into another, with the field mapping shown first.

Only to a layer of the same geometry type (point, line or polygon); a mismatch is refused. Single and multi-part forms convert (a single polygon into a MultiPolygon layer);
a multi-part feature into a single-part layer is refused when it really has several parts. Different CRS: the geometry is transformed into the target's. The field mapping is
resolved and every value converted BEFORE anything is written, so a value that does not fit stops the copy with nothing changed; see copy_ops.py for the rules. It returns a
PREVIEW_REQUIRED card first (which features, which fields go where, which target fields stay empty, which source fields are not copied) and applies in the repo's edit command:
one undoable step (undo_manual_edit), no takeover of a layer already in edit mode. The source layer is never changed.

Written without a QGIS install; tests/test_copy_features_tool_live.py is its first execution in CI."""
from . import copy_ops as co
from .attribute_edit_tools import _expression_ok, _layer, _unsaved_note, preview
from .registry import register_tool

try:
    from qgis.core import NULL, QgsCoordinateTransform, QgsFeature, QgsFeatureRequest, QgsProject, QgsWkbTypes
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False


def _scope(source, filter_expression, only_selected):
    """(features, how, error): the features to copy and which rule chose them. Needs QGIS."""
    if filter_expression:
        problem = _expression_ok(filter_expression)
        if problem:
            return None, None, problem
        request = QgsFeatureRequest().setFilterExpression(filter_expression)
        return list(source.getFeatures(request)), "filter", None
    if only_selected or (only_selected is None and source.selectedFeatureCount()):
        if not source.selectedFeatureCount():
            return None, None, f"'{source.name()}' has no selected features. Select some, give a filter_expression, or pass only_selected false to copy all."
        return source.selectedFeatures(), "selected", None
    return list(source.getFeatures()), "all", None


def _geometry_for(feature, source, target, transform, target_multi):
    """(geometry for the target, error text or None). Needs QGIS."""
    geometry = feature.geometry()
    if geometry.isNull():
        return geometry, None
    if transform is not None:
        moved = geometry.transform(transform)                       # QGIS 4 returns an enum named Success, QGIS 3 the int 0
        if getattr(moved, "name", None) != "Success" and moved != 0:
            return None, f"feature {feature.id()} could not be transformed to the target CRS."
    if geometry.isMultipart() and not target_multi:
        if geometry.constGet().partCount() > 1:
            return None, f"feature {feature.id()} has {geometry.constGet().partCount()} parts but '{target.name()}' holds single-part geometries."
        geometry.convertToSingleType()
    elif target_multi and not geometry.isMultipart():
        geometry.convertToMultiType()
    return geometry, None


def _build(features, source, target, pairs, kinds, transform):
    """([new features], [problems]) with every value converted; nothing is written. Needs QGIS."""
    target_multi = QgsWkbTypes.isMultiType(target.wkbType())
    built, problems = [], []
    for f in features:
        geometry, why = _geometry_for(f, source, target, transform, target_multi)
        if why:
            problems.append(why)
            continue
        new = QgsFeature(target.fields())
        if geometry is not None and not geometry.isNull():
            new.setGeometry(geometry)
        for s, t in pairs:
            raw = f[s]
            value, error = co.convert_value(None if raw is None or raw == NULL else raw, kinds[t])
            if error:
                problems.append(f"feature {f.id()}, field '{s}' into '{t}': {error}")
            elif value is not None:
                new[t] = value
        built.append(new)
    return built, problems


@register_tool(
    "copy_features_between_layers",
    "Copy features from one vector layer into another existing layer of the SAME geometry type (point, line or polygon; a mismatch is refused): the selected features (default when "
    "some are selected), those matching filter_expression, or all of them. field_mapping is {target field: source field}; fields with the same name are matched automatically, the "
    "rest stay empty, and a value that does not fit the target field's type stops the copy with nothing changed. A different CRS is transformed to the target's. Changes the target "
    "layer: a preview with the mapping is shown for confirmation first, the edit is one undoable step (undo_manual_edit), and the source layer is never changed.",
    {"type": "object", "properties": {
        "source_layer": {"type": "string", "description": "The vector layer to copy from."},
        "target_layer": {"type": "string", "description": "The existing vector layer to copy into (same geometry type)."},
        "only_selected": {"type": "boolean", "description": "Copy only the selected features (default: yes when the source has a selection, else all)."},
        "filter_expression": {"type": "string", "description": "A QGIS expression: copy the features it is true for (instead of the selection)."},
        "field_mapping": {"type": "object", "additionalProperties": {"type": "string"}, "description": "{target field: source field}; unnamed target fields match a source field of the same name."}},
     "required": ["source_layer", "target_layer"]},
    keywords=["copy features", "copy the selected features", "copy features to", "paste features", "copy the features into", "move features between layers", "append features", "copy to another layer"],
)
def copy_features_between_layers(source_layer, target_layer, only_selected=None, filter_expression=None, field_mapping=None, confirmed=False):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    problem = co.check_request(source_layer, target_layer, field_mapping, filter_expression, only_selected)
    if problem:
        return {"error": problem}
    source, err = _layer(source_layer)
    if err:
        return err
    target, err = _layer(target_layer)
    if err:
        return err
    if QgsWkbTypes.geometryType(source.wkbType()) != QgsWkbTypes.geometryType(target.wkbType()):
        return {"error": f"'{source_layer}' and '{target_layer}' have different geometry types ({QgsWkbTypes.displayString(source.wkbType())} and "
                         f"{QgsWkbTypes.displayString(target.wkbType())}); features are only copied between layers of the same type."}
    pairs, empty, unused, why = co.resolve_mapping([f.name() for f in source.fields()], [f.name() for f in target.fields()], field_mapping)
    if why:
        return {"error": why}
    features, how, why = _scope(source, filter_expression, only_selected)
    if why:
        return {"error": why}
    if not features:
        return {"error": "No features match, so there is nothing to copy."}
    if len(features) > co.MAX_FEATURES:
        return {"error": f"{len(features)} features is more than the {co.MAX_FEATURES} one copy handles; filter or select fewer."}
    transform = None
    if source.crs().isValid() and target.crs().isValid() and source.crs() != target.crs():
        transform = QgsCoordinateTransform(source.crs(), target.crs(), QgsProject.instance())
    kinds = {f.name(): co.kind_from_type_name(f.typeName()) for f in target.fields()}
    built, problems = _build(features, source, target, pairs, kinds, transform)
    if problems:
        return {"error": f"Nothing was copied: {len(problems)} problem(s), for example " + "; ".join(problems[:co.LIST_MAX])}
    if not confirmed:
        mapped = ", ".join(f"{s} -> {t}" for s, t in pairs) or "(none)"
        rationale = (f"Copy {co.describe_scope(how, len(built), source.featureCount())} from '{source_layer}' into '{target_layer}'. Fields copied: {mapped}. "
                     f"Left empty in the target: {co.list_some(empty) or '(none)'}. Not copied from the source: {co.list_some(unused) or '(none)'}."
                     + (" The geometry is transformed to the target's CRS." if transform is not None else ""))
        arguments = {"source_layer": source_layer, "target_layer": target_layer, "field_mapping": {t: s for s, t in pairs}}
        if filter_expression:
            arguments["filter_expression"] = filter_expression
        else:
            arguments["only_selected"] = how == "selected"
        return preview("copy_features_between_layers", arguments, rationale,
                       "target.startEditing()\ntarget.addFeatures(new_features)   # field values converted to the target's types\ntarget.commitChanges()")
    from ._edit_session import EditError, edit_command
    try:
        with edit_command(target, "Cartogen AI: copy features") as owned:
            if not target.addFeatures(built):
                raise EditError("the target layer refused the features (read-only source?).")
    except EditError as e:
        return {"error": f"Nothing was copied: {e}"}
    out = {"success": True, "source_layer": source_layer, "target_layer": target_layer, "features_copied": len(built), "scope": how,
           "fields_copied": [{"from": s, "to": t} for s, t in pairs], "fields_left_empty": empty, "fields_not_copied": unused,
           "undo": "undo_manual_edit steps it back while the target layer is in edit mode."}
    if transform is not None:
        out["crs_note"] = f"The geometry was transformed from {source.crs().authid()} to {target.crs().authid()}."
    note = _unsaved_note(owned)
    if note:
        out["note"] = note
    return out
