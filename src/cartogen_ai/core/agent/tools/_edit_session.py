# -*- coding: utf-8 -*-
"""
Owned, checked attribute edits on a vector layer (GitHub #143 and #144; audit F07 and F08).

Why this module exists. The field-writing tools (field_calculator, calculate_area/length, the road impedance field and the undo
restore of those) each did `layer.startEditing()` ... `layer.commitChanges()` themselves, and

  * took over a layer the USER already had in edit mode: they committed the user's unrelated pending edits on success, or rolled
    them back in the error path (F07);
  * added the new field straight to the data provider, bypassing the edit buffer, so a later failure could not undo it (F07);
  * never looked at the result of addAttributes / startEditing / changeAttributeValue / commitChanges, and QGIS providers report
    most failures by returning False rather than raising, so a read-only layer or a bad expression still ended in "success" (F08).

`edit_command` is the one place that now does this correctly:

  * if the layer is not editable it starts editing, and then (and only then) owns the commit / rollback;
  * if the layer is already editable the changes go into the user's edit buffer and are left for the user to save or discard;
  * every change runs inside an edit command, so a failure undoes exactly this tool's changes (`destroyEditCommand`), also inside
    the user's session;
  * a failed commit rolls back and raises with the provider's own error text.

It needs a real QgsVectorLayer; tests/test_edit_session.py checks the control flow with fakes and tests/test_edit_session_live.py
runs it in QGIS. Neither has been run against every provider type.
"""
from contextlib import contextmanager


class EditError(Exception):
    """An attribute edit could not be completed; nothing from this edit command is left applied."""


@contextmanager
def edit_command(layer, label):
    """Context manager around one atomic set of edits to `layer`. Yields True when this call started the edit session (and so
    will commit it), False when the layer was already being edited by someone else. Raises EditError on failure."""
    owned = False
    if not layer.isEditable():
        if not layer.startEditing():
            raise EditError("the layer could not be switched to edit mode (is the source read-only?)")
        owned = True
    layer.beginEditCommand(label)
    try:
        yield owned
    except BaseException:
        layer.destroyEditCommand()
        if owned and layer.isEditable():
            layer.rollBack()
        raise
    layer.endEditCommand()
    if owned:
        if not layer.commitChanges():
            try:
                errors = "; ".join(str(e) for e in layer.commitErrors())
            except Exception:
                errors = ""
            if layer.isEditable():
                layer.rollBack()
            raise EditError("the provider rejected the changes" + (f": {errors}" if errors else "."))


def begin_feature_edits(layer):
    """For tools that add or remove FEATURES in a loop (re-indenting that loop into `edit_command` would bury the logic). Starts
    editing unless the layer is already being edited; returns True when this call owns the session. Raises EditError."""
    if layer.isEditable():
        return False
    if not layer.startEditing():
        raise EditError("the layer could not be switched to edit mode (is the source read-only?)")
    return True


def finish_feature_edits(layer, owned):
    """Commits when `owned`, checking the result (rolling back and raising EditError with the provider's text on failure). A
    layer the user is editing is left alone: the added features sit in the user's buffer for them to save or discard."""
    if not owned:
        return
    if not layer.commitChanges():
        try:
            errors = "; ".join(str(e) for e in layer.commitErrors())
        except Exception:
            errors = ""
        if layer.isEditable():
            layer.rollBack()
        raise EditError("the provider rejected the changes" + (f": {errors}" if errors else "."))


def add_numeric_field(layer, field_name):
    """Index of `field_name` on `layer`, adding it as a Double field THROUGH THE EDIT BUFFER if it does not exist. Call inside
    edit_command. Raises EditError if the field exists but is not numeric, or cannot be added."""
    from qgis.core import QgsField
    from qgis.PyQt.QtCore import QVariant
    idx = layer.fields().indexOf(field_name)
    if idx >= 0:
        if not layer.fields().at(idx).isNumeric():
            raise EditError(f"field '{field_name}' already exists with a non-numeric type; refusing to overwrite it.")
        return idx
    if not layer.addAttribute(QgsField(field_name, QVariant.Double)):
        raise EditError(f"field '{field_name}' could not be added to this layer.")
    layer.updateFields()
    idx = layer.fields().indexOf(field_name)
    if idx < 0:
        raise EditError(f"field '{field_name}' was not found after adding it.")
    return idx


def set_value(layer, feature_id, field_index, value):
    """changeAttributeValue with its result checked. Raises EditError on failure."""
    if not layer.changeAttributeValue(feature_id, field_index, value):
        raise EditError(f"could not write a value to feature {feature_id} (read-only or incompatible field?).")
