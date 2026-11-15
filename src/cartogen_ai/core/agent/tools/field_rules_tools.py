"""add_virtual_field, remove_virtual_field, set_field_constraint and set_default_value (PLAN-023 R10-1): the attribute-table rules QGIS keeps in the project.

None of the four edits the data. A virtual field is computed from its expression each time the layer is read and is never written into the file; a constraint (not null, unique, or an
expression, hard or soft) is a rule QGIS checks when a value is entered; a default value fills a new feature. They are stored with the PROJECT (save it to keep them) and are not on the
layer's undo stack, so each reply says what it replaced and how to remove the rule. Every expression goes through the repo's expression screen (denied functions are refused) and must
parse; a virtual field's expression must also evaluate on the first feature. set_field_constraint reads the rule back and checks the existing features against it, reporting how many
break it (they are reported, never changed).

Written without a QGIS install; tests/test_field_rules_tools_live.py is their first execution in CI."""
from . import field_rules as fr
from .attribute_edit_tools import FIELD_TYPE_WORDS, _expression_ok, _layer
from .registry import register_tool

try:
    from qgis.core import (QgsDefaultValue, QgsExpression, QgsExpressionContext, QgsExpressionContextUtils, QgsField, QgsFieldConstraints, QgsVectorLayerUtils)
    from qgis.PyQt.QtCore import QVariant
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False

MAX_CHECKED = 50000
PROJECT_NOTE = "Stored with the project, not in the data file: save the project to keep it."


def _field_index(layer, field):
    idx = layer.fields().indexOf(str(field or ""))
    return idx, (None if idx >= 0 else {"error": f"Field '{field}' not found in '{layer.name()}'."})


def _first_value(layer, expression):
    """(value, error text or None) of `expression` on the first feature of `layer`; (None, None) when the layer is empty. Needs QGIS."""
    parsed = QgsExpression(expression)
    context = QgsExpressionContext(QgsExpressionContextUtils.globalProjectLayerScopes(layer))
    for f in layer.getFeatures():
        context.setFeature(f)
        value = parsed.evaluate(context)
        return (None, f"it does not evaluate: {parsed.evalErrorString()}") if parsed.hasEvalError() else (value, None)
    return None, None


@register_tool(
    "add_virtual_field",
    "Add a virtual (calculated) field to a layer: its value is computed from a QGIS expression every time the layer is read, and nothing is written into the data file, so it can "
    "never be out of date. For example density = \"population\" / $area. field_type: string, integer, long, double, date or datetime. The expression must be valid and evaluate on the first "
    "feature. Stored with the project, not in the file. Remove it with remove_virtual_field.",
    {"type": "object", "properties": {
        "layer_name": {"type": "string", "description": "The vector layer."},
        "name": {"type": "string", "description": "The new field's name (letters, digits, underscore, spaces)."},
        "field_type": {"type": "string", "description": "string, integer, long, double, date or datetime (default string)."},
        "expression": {"type": "string", "description": "The QGIS expression that gives the value."}},
     "required": ["layer_name", "name", "expression"]},
    keywords=["virtual field", "add a virtual field", "calculated field that is not saved", "virtual column", "computed field", "field from an expression without writing it"],
)
def add_virtual_field(layer_name, name, expression, field_type="string"):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    problem = fr.check_virtual(name, field_type, expression)
    if problem:
        return {"error": problem}
    layer, err = _layer(layer_name)
    if err:
        return err
    name = str(name).strip()
    if layer.fields().indexOf(name) >= 0:
        return {"error": f"Field '{name}' already exists on '{layer_name}'."}
    problem = _expression_ok(expression)
    if problem:
        return {"error": problem}
    sample, why = _first_value(layer, expression)
    if why:
        return {"error": f"The expression was not accepted: {why}"}
    word = FIELD_TYPE_WORDS[str(field_type or "string").strip().lower()]
    if layer.addExpressionField(expression, QgsField(name, getattr(QVariant, word))) < 0:
        return {"error": "QGIS refused to add the virtual field."}
    layer.updateFields()
    shown = None if sample is None else (sample if isinstance(sample, int | float | str | bool) else str(sample))
    return {"success": True, "layer_name": layer_name, "field": name, "type": word, "expression": expression, "value_on_first_feature": shown,
            "note": PROJECT_NOTE + " Remove it with remove_virtual_field."}


@register_tool(
    "remove_virtual_field",
    "Remove a virtual field made with add_virtual_field. Only virtual fields can be removed this way; a real column is never touched (use delete_field for that, which asks first).",
    {"type": "object", "properties": {"layer_name": {"type": "string"}, "name": {"type": "string", "description": "The virtual field's name."}},
     "required": ["layer_name", "name"]},
    keywords=["remove the virtual field", "delete the virtual field", "remove a virtual field", "drop the virtual field"],
)
def remove_virtual_field(layer_name, name):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    layer, err = _layer(layer_name)
    if err:
        return err
    idx, why = _field_index(layer, name)
    if why:
        return why
    expression = layer.expressionField(idx)
    if not expression:
        return {"error": f"'{name}' is a real column, not a virtual field, so it is not removed here."}
    layer.removeExpressionField(idx)
    layer.updateFields()
    return {"success": True, "layer_name": layer_name, "removed": name, "expression_was": expression,
            "note": "Nothing in the data changed; add it again with add_virtual_field and the same expression if needed."}


def _constraint_state(layer, idx):
    flags = layer.fieldConstraints(idx)
    return {"not_null": bool(flags & QgsFieldConstraints.Constraint.ConstraintNotNull), "unique": bool(flags & QgsFieldConstraints.Constraint.ConstraintUnique),
            "expression": layer.constraintExpression(idx) or "", "description": layer.constraintDescription(idx) or ""}


def _violations(layer, idx):
    """(summary dict) of the existing features that break the rules of field `idx`, at most MAX_CHECKED scanned. Needs QGIS."""
    rows, scanned = [], 0
    for f in layer.getFeatures():
        if scanned >= MAX_CHECKED:
            break
        scanned += 1
        try:
            result = QgsVectorLayerUtils.validateAttribute(layer, f, idx)
        except TypeError:                                   # a build whose signature wants the output list
            errors = []
            result = (QgsVectorLayerUtils.validateAttribute(layer, f, idx, errors), errors)
        ok, errors = result if isinstance(result, tuple) else (result, [])
        if not ok:
            rows.append((f.id(), [str(e) for e in errors]))
    summary = fr.summarise_violations(rows, scanned)
    if scanned >= MAX_CHECKED:
        summary["note"] = f"Only the first {MAX_CHECKED} features were checked."
    return summary


@register_tool(
    "set_field_constraint",
    "Set or remove the rules QGIS enforces on a field: not_null, unique and/or an expression (with a description shown when it fails), hard (blocks the value) or soft (warns). A rule that "
    "is given is set (true / a text) or removed (false / an empty text); one that is left out is untouched. The reply reads the rules back and checks the existing features against them: "
    "how many break them is reported, nothing is changed. Stored with the project, not in the data file.",
    {"type": "object", "properties": {
        "layer_name": {"type": "string", "description": "The vector layer."},
        "field": {"type": "string", "description": "The field the rules are on."},
        "not_null": {"type": "boolean", "description": "true: the value may not be empty; false: remove that rule."},
        "unique": {"type": "boolean", "description": "true: no two features may have the same value; false: remove that rule."},
        "expression": {"type": "string", "description": "A QGIS expression that must be true, for example \"population\" >= 0; empty text removes it."},
        "description": {"type": "string", "description": "The message shown when the expression fails."},
        "strength": {"type": "string", "enum": list(fr.STRENGTHS), "description": "hard (default) blocks the value, soft only warns."}},
     "required": ["layer_name", "field"]},
    keywords=["field constraint", "set a constraint", "not null constraint", "make the field unique", "make the field mandatory", "require a value", "validation rule", "constraint on the field"],
)
def set_field_constraint(layer_name, field, not_null=None, unique=None, expression=None, description=None, strength="hard"):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    problem = fr.check_constraint(not_null, unique, expression, description, strength)
    if problem:
        return {"error": problem}
    layer, err = _layer(layer_name)
    if err:
        return err
    idx, why = _field_index(layer, field)
    if why:
        return why
    if expression:
        problem = _expression_ok(expression)
        if problem:
            return {"error": problem}
    before = _constraint_state(layer, idx)
    level = QgsFieldConstraints.ConstraintStrength.ConstraintStrengthHard if str(strength or "hard").lower() == "hard" else QgsFieldConstraints.ConstraintStrength.ConstraintStrengthSoft
    for wanted, kind in ((not_null, QgsFieldConstraints.Constraint.ConstraintNotNull), (unique, QgsFieldConstraints.Constraint.ConstraintUnique)):
        if wanted is True:
            layer.setFieldConstraint(idx, kind, level)
        elif wanted is False:
            layer.removeFieldConstraint(idx, kind)
    if expression is not None:
        layer.setConstraintExpression(idx, expression, description or "")
    return {"success": True, "layer_name": layer_name, "field": field, "rules_now": _constraint_state(layer, idx), "rules_before": before,
           "existing_features": _violations(layer, idx), "note": PROJECT_NOTE + " Features that already break a rule are reported here and left as they are."}


@register_tool(
    "set_default_value",
    "Set or remove the default value of a field: a QGIS expression QGIS evaluates to fill the field of every NEW feature (for example now(), @user_account_name or a number). "
    "apply_on_update also re-evaluates it whenever the feature is edited. An empty expression removes the default. Existing features are not changed. Stored with the project, "
    "not in the data file.",
    {"type": "object", "properties": {
        "layer_name": {"type": "string", "description": "The vector layer."},
        "field": {"type": "string", "description": "The field that gets the default."},
        "expression": {"type": "string", "description": "The QGIS expression; empty text removes the default."},
        "apply_on_update": {"type": "boolean", "description": "Also re-evaluate when the feature is edited (default false)."}},
     "required": ["layer_name", "field", "expression"]},
    keywords=["default value", "set a default value", "default for the field", "fill new features with", "remove the default value", "auto fill the field"],
)
def set_default_value(layer_name, field, expression, apply_on_update=False):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    problem = fr.check_default(expression, apply_on_update)
    if problem:
        return {"error": problem}
    layer, err = _layer(layer_name)
    if err:
        return err
    idx, why = _field_index(layer, field)
    if why:
        return why
    if expression.strip():
        problem = _expression_ok(expression)
        if problem:
            return {"error": problem}
    before = layer.defaultValueDefinition(idx)
    layer.setDefaultValueDefinition(idx, QgsDefaultValue(expression.strip(), bool(apply_on_update)) if expression.strip() else QgsDefaultValue())
    now = layer.defaultValueDefinition(idx)
    return {"success": True, "layer_name": layer_name, "field": field, "default_now": now.expression(), "apply_on_update": bool(now.applyOnUpdate()),
            "default_before": before.expression(), "note": PROJECT_NOTE + " Existing features are not changed; new features get the value."}
