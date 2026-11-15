"""Field rules helpers (PLAN-023 R10-1): the request checks for virtual fields, constraints and default values and the violation summary, pure Python (no QGIS, no numpy).

field_rules_tools.py applies them through QGIS (addExpressionField, setFieldConstraint, setConstraintExpression, setDefaultValueDefinition). These three settings are layer
properties stored in the PROJECT, not edits to the data: a virtual field is computed from its expression every time and never written into the file, a constraint is a rule QGIS
checks when a value is typed, and a default value fills a new feature. They change nothing in existing rows. Because they are not data edits they are not on the layer's undo stack:
each reply says what was replaced and how to remove the rule (a virtual field with remove_virtual_field, a constraint or a default by sending it empty).
Known answers (the tests): a name with ':' is refused, 'not_null' with a hard strength is a valid constraint request, a request that sets nothing is refused, 12 violations are
summarised as a count of 12 with the first 10 feature ids."""
from .attribute_edit_tools import FIELD_TYPE_WORDS

STRENGTHS = ("hard", "soft")
MAX_EXPRESSION = 2000
LIST_MAX = 10


def _expression_problem(expression, what):
    if not isinstance(expression, str) or not expression.strip():
        return f"{what} needs an expression, for example \"population\" / \"area\"."
    if len(expression) > MAX_EXPRESSION:
        return f"The expression is longer than {MAX_EXPRESSION} characters."
    return None


def check_virtual(name, field_type, expression):
    """Error text for an add_virtual_field request that cannot be run, else None. Pure."""
    from .data_source_tools import build_field_specs
    problem = build_field_specs([{"name": name}])[1]
    if problem:
        return problem
    if FIELD_TYPE_WORDS.get(str(field_type or "string").strip().lower()) is None:
        return f"type '{field_type}' is not supported. Use string, integer, long, double, date or datetime."
    return _expression_problem(expression, "A virtual field")


def check_constraint(not_null=None, unique=None, expression=None, description=None, strength="hard"):
    """Error text for a set_field_constraint request that cannot be run, else None. Each of not_null, unique and expression that is given is set (True / a text) or removed
    (False / an empty text); one that is left out is untouched. Pure."""
    for label, value in (("not_null", not_null), ("unique", unique)):
        if value is not None and not isinstance(value, bool):
            return f"{label} must be true or false."
    if expression is not None and not isinstance(expression, str):
        return "expression must be text (an empty text removes the rule)."
    if expression and len(expression) > MAX_EXPRESSION:
        return f"The expression is longer than {MAX_EXPRESSION} characters."
    if str(strength or "hard").strip().lower() not in STRENGTHS:
        return f"strength must be one of {', '.join(STRENGTHS)} (hard blocks the value, soft only warns)."
    if description is not None and (not isinstance(description, str) or not expression):
        return "description goes with an expression: it is the message shown when the rule fails."
    if not_null is None and unique is None and expression is None:
        return "Nothing to set: give not_null, unique and/or expression."
    return None


def check_default(expression, apply_on_update=False):
    """Error text for a set_default_value request that cannot be run, else None. An empty expression removes the default. Pure."""
    if not isinstance(expression, str):
        return "expression must be text (an empty text removes the default)."
    if len(expression) > MAX_EXPRESSION:
        return f"The expression is longer than {MAX_EXPRESSION} characters."
    if not isinstance(apply_on_update, bool):
        return "apply_on_update must be true or false."
    if apply_on_update and not expression.strip():
        return "apply_on_update needs an expression."
    return None


def summarise_violations(rows, scanned):
    """{'checked': n, 'violations': count, 'feature_ids': first LIST_MAX, 'examples': first 3 messages} for `rows`, a list of (feature id, [messages]). Pure."""
    examples = []
    for _fid, messages in rows:
        for message in messages:
            if message not in examples and len(examples) < 3:
                examples.append(message)
    return {"checked": scanned, "violations": len(rows), "feature_ids": [fid for fid, _m in rows[:LIST_MAX]], "examples": examples}
