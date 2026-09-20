# -*- coding: utf-8 -*-
"""Snapshot/restore pairs for a priority subset of MODIFY/DELETE tools --
the real, still-open half of point 20 of
docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md that
models/transactions.py's own docstring names but doesn't close: "no
rollback exists for a MODIFY call... or a DELETE call."

Explicit {tool_name: (snapshot_fn, restore_fn)} registry, not one generic
reflection-based snapshotter -- matches this codebase's existing
preference for explicit per-tool logic over central magic (e.g.
tool_operations.py's hand-classified operation types rather than a
name-guessing heuristic). Each snapshot_fn(arguments) -> a small dict
describing exactly enough state to reverse the call, or None if there is
nothing to snapshot (layer not found, etc.); each restore_fn(snapshot) ->
True/False, never raises. agent.py calls snapshot_fn BEFORE dispatching a
registered tool call and stores the result on the turn's transaction log
entry only if the call succeeds; transaction_tools.py's undo_last_operation
calls restore_fn when a logged entry carries one.

Priority subset covered here (see docs/MASTER_TASK_REGISTRY.md's v1.7.0
workstream-2 entry for why these and not the full named list):
- remove_layer (DELETE)
- field_calculator, calculate_area, calculate_length (MODIFY, field-write)
- apply_categorized_style, apply_graduated_style, apply_graduated_symbol_style
  (MODIFY, style)
- set_dataset_status, set_layer_sensitivity, set_layer_confidence, run_query
  (MODIFY, single-property overwrite)

Explicitly NOT covered, a real follow-up gap not silently promised: load_project,
and any MODIFY tool not listed above (advance_dataset_status, the four
composite-index tools' optional output_field, etc.) -- see transactions.py's
own docstring for the same standing caveat.
"""

try:
    from qgis.core import QgsProject
    from qgis.PyQt.QtXml import QDomDocument
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False

from ....infrastructure.settings_keys import (
    PROJECT_PROPERTY_DATASET_STATUS,
    PROJECT_PROPERTY_SENSITIVITY,
    PROJECT_PROPERTY_CONFIDENCE,
)


def _find_layer(layer_name):
    if not QGIS_AVAILABLE or not layer_name:
        return None
    layers = QgsProject.instance().mapLayersByName(layer_name)
    return layers[0] if layers else None


def _layer_by_id(layer_id):
    if not QGIS_AVAILABLE or not layer_id:
        return None
    return QgsProject.instance().mapLayer(layer_id)


# -- remove_layer (DELETE) ---------------------------------------------------
#
# Confirmed live against real QGIS 4.2.2: QgsProject.removeMapLayer()
# destroys the underlying C++ object immediately, not deferred -- a plain
# Python reference held BEFORE removal becomes a dead SIP wrapper the
# instant removeMapLayer() is called ("RuntimeError: wrapped C/C++ object
# of type QgsVectorLayer has been deleted" on any access afterward, and
# re-adding it fails the same way). layer.clone() called BEFORE removal
# produces a genuinely independent C++ object that survives the original's
# destruction -- confirmed live: real feature data intact after the
# original was removed, and QgsProject.addMapLayer(clone) succeeds,
# restoring a fully working layer (under a new layer id, which is fine --
# the user gets their layer and data back, they don't track ids).

def _snapshot_remove_layer(arguments):
    layer = _find_layer(arguments.get("layer_name"))
    if layer is None:
        return None
    try:
        return {"kind": "restore_layer", "clone": layer.clone()}
    except Exception:
        return None


def _restore_remove_layer(snapshot):
    try:
        QgsProject.instance().addMapLayer(snapshot["clone"])
        return True
    except Exception:
        return False


# -- field_calculator / calculate_area / calculate_length (MODIFY, field-write) --
#
# All three funnel through vector_tools._add_calculated_field(layer, field_name, ...).
# calculate_area/calculate_length always target a fixed field name
# ("area_sqm"/"length_m"); field_calculator's target field name is
# caller-supplied (`new_field`). If the field didn't already exist, undo
# deletes it entirely; if it did, undo restores every feature's prior value.
# Only snapshots when confirmed=True is actually being passed this call --
# these tools are gated behind a PREVIEW_REQUIRED confirm step, and a
# preview-only call never mutates anything, so snapshotting on it would be
# pure wasted work (a full per-feature field read on every preview,
# repeated again on the real confirmed call).

def _snapshot_field_write(field_name_fn):
    def snapshot_fn(arguments):
        if not arguments.get("confirmed"):
            return None
        layer = _find_layer(arguments.get("layer_name"))
        if layer is None:
            return None
        field_name = field_name_fn(arguments)
        try:
            idx = layer.fields().indexOf(field_name)
            if idx == -1:
                return {"kind": "restore_field", "layer_id": layer.id(), "field_name": field_name, "field_existed": False}
            values = {f.id(): f.attribute(idx) for f in layer.getFeatures()}
            return {"kind": "restore_field", "layer_id": layer.id(), "field_name": field_name, "field_existed": True, "values": values}
        except Exception:
            return None
    return snapshot_fn


def _restore_field_write(snapshot):
    layer = _layer_by_id(snapshot["layer_id"])
    if layer is None:
        return False
    try:
        idx = layer.fields().indexOf(snapshot["field_name"])
        if idx == -1:
            return True  # already gone some other way -- nothing left to undo
        layer.startEditing()
        if not snapshot["field_existed"]:
            layer.dataProvider().deleteAttributes([idx])
            layer.updateFields()
        else:
            for fid, old_value in snapshot["values"].items():
                layer.changeAttributeValue(fid, idx, old_value)
        layer.commitChanges()
        return True
    except Exception:
        try:
            if layer.isEditable():
                layer.rollBack()
        except Exception:
            pass
        return False


# -- apply_categorized_style / apply_graduated_style / apply_graduated_symbol_style
# (MODIFY, style) --
#
# QgsMapLayer.exportNamedStyle(doc)/.importNamedStyle(doc) both take a real
# QDomDocument, not a bare string -- confirmed live (a no-arg call raises
# TypeError). exportNamedStyle(doc) mutates doc in place and returns an
# error-message string (empty on success); doc.toString() is the real XML.
# importNamedStyle(doc) returns (success_bool, error_message) -- confirmed
# live, a real style round-trips through exactly this sequence.

def _snapshot_style(arguments):
    layer = _find_layer(arguments.get("layer_name"))
    if layer is None:
        return None
    try:
        doc = QDomDocument()
        layer.exportNamedStyle(doc)
        return {"kind": "restore_style", "layer_id": layer.id(), "xml": doc.toString()}
    except Exception:
        return None


def _restore_style(snapshot):
    layer = _layer_by_id(snapshot["layer_id"])
    if layer is None:
        return False
    try:
        doc = QDomDocument()
        doc.setContent(snapshot["xml"])
        ok, _err = layer.importNamedStyle(doc)
        if ok:
            layer.triggerRepaint()
        return bool(ok)
    except Exception:
        return False


# -- set_dataset_status / set_layer_sensitivity / set_layer_confidence / run_query
# (MODIFY, single-property overwrite) --
#
# All four overwrite exactly one string-shaped property on the layer
# (a customProperty for the first three, subsetString for run_query) with
# no other side effect -- same snapshot/restore shape, parameterized by
# which getter/setter pair applies. set_dataset_status specifically only
# ever runs on an untracked layer (refuses otherwise, per its own tool
# description), so its "old value" is always the untracked/empty state --
# still handled generically here rather than as a special case, since
# reading-then-restoring the same key works identically either way.

def _customproperty_getter(key):
    def get(layer):
        return layer.customProperty(key, "")
    return get


def _customproperty_setter(key):
    def set_(layer, value):
        layer.setCustomProperty(key, value)
    return set_


def _subsetstring_get(layer):
    return layer.subsetString()


def _subsetstring_set(layer, value):
    layer.setSubsetString(value)


def _make_property_snapshot_fn(get_old_value):
    def snapshot_fn(arguments):
        layer = _find_layer(arguments.get("layer_name"))
        if layer is None:
            return None
        try:
            return {"kind": "restore_property", "layer_id": layer.id(), "old_value": get_old_value(layer)}
        except Exception:
            return None
    return snapshot_fn


def _make_property_restore_fn(set_value):
    def restore_fn(snapshot):
        layer = _layer_by_id(snapshot["layer_id"])
        if layer is None:
            return False
        try:
            set_value(layer, snapshot["old_value"])
            return True
        except Exception:
            return False
    return restore_fn


SNAPSHOT_REGISTRY = {
    "remove_layer": (_snapshot_remove_layer, _restore_remove_layer),
    "field_calculator": (
        _snapshot_field_write(lambda args: args.get("new_field")),
        _restore_field_write,
    ),
    "calculate_area": (
        _snapshot_field_write(lambda args: "area_sqm"),
        _restore_field_write,
    ),
    "calculate_length": (
        _snapshot_field_write(lambda args: "length_m"),
        _restore_field_write,
    ),
    "apply_categorized_style": (_snapshot_style, _restore_style),
    "apply_graduated_style": (_snapshot_style, _restore_style),
    "apply_graduated_symbol_style": (_snapshot_style, _restore_style),
    "set_dataset_status": (
        _make_property_snapshot_fn(_customproperty_getter(PROJECT_PROPERTY_DATASET_STATUS)),
        _make_property_restore_fn(_customproperty_setter(PROJECT_PROPERTY_DATASET_STATUS)),
    ),
    "set_layer_sensitivity": (
        _make_property_snapshot_fn(_customproperty_getter(PROJECT_PROPERTY_SENSITIVITY)),
        _make_property_restore_fn(_customproperty_setter(PROJECT_PROPERTY_SENSITIVITY)),
    ),
    "set_layer_confidence": (
        _make_property_snapshot_fn(_customproperty_getter(PROJECT_PROPERTY_CONFIDENCE)),
        _make_property_restore_fn(_customproperty_setter(PROJECT_PROPERTY_CONFIDENCE)),
    ),
    "run_query": (
        _make_property_snapshot_fn(_subsetstring_get),
        _make_property_restore_fn(_subsetstring_set),
    ),
}


def get_snapshot_fn(tool_name):
    entry = SNAPSHOT_REGISTRY.get(tool_name)
    return entry[0] if entry else None


def get_restore_fn(kind, tool_name):
    """restore_fn is looked up by tool_name (not by the snapshot's own
    "kind" string) since several tools can share the same restore
    mechanism (e.g. every style tool restores via _restore_style) --
    kind is kept on the snapshot dict for readability/debugging only."""
    entry = SNAPSHOT_REGISTRY.get(tool_name)
    return entry[1] if entry else None
