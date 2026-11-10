"""set_conditional_formatting, set_map_tip and add_feature_action (PLAN-023 R10-2): how the attribute table and the map show a layer's features.

All three are layer properties stored in the PROJECT (save it to keep them); none edits data. Conditional formatting colours attribute-table cells (or whole rows) by a QGIS expression
(@value is the cell's value); a map tip is the HTML bubble shown when the pointer rests on a feature, written with [% expression %] fields; a layer action is an entry in the feature's
action menu. Every expression goes through the repo's expression screen and must parse. POLICY (see display_rules.py): a layer action that runs a command, Python code or a program is
REFUSED and the reply says why; only an open_url action (http or https, built from the feature's values) is added. Map tips only show when the user has "Show Map Tips" on (a canvas
setting these tools do not toggle), and the reply says so.

Written without a QGIS install; tests/test_layer_display_tools_live.py is their first execution in CI."""
from . import display_rules as dr
from .attribute_edit_tools import _expression_ok, _layer
from .registry import register_tool

try:
    from qgis.core import Qgis, QgsAction, QgsConditionalStyle
    from qgis.PyQt.QtGui import QColor
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False

PROJECT_NOTE = "Stored with the project, not in the data file: save the project to keep it."


def _colour(text):
    """(QColor, error): the colour named by `text` (a name or #rrggbb). Needs QGIS."""
    colour = QColor(str(text).strip())
    return (colour, None) if colour.isValid() else (None, f"'{text}' is not a colour QGIS knows (use a name like red or a hex code like #ff0000).")


def _styles(rules):
    """([QgsConditionalStyle], error) built from the rule dicts. Needs QGIS."""
    built = []
    for i, rule in enumerate(rules, 1):
        problem = _expression_ok(rule["condition"])
        if problem:
            return None, f"rule {i}: {problem}"
        style = QgsConditionalStyle()
        style.setRule(rule["condition"])
        style.setName(str(rule.get("name") or f"rule {i}")[:60])
        for key, setter in (("background_color", style.setBackgroundColor), ("text_color", style.setTextColor)):
            if rule.get(key) is not None:
                colour, why = _colour(rule[key])
                if why:
                    return None, f"rule {i}: {why}"
                setter(colour)
        built.append(style)
    return built, None


@register_tool(
    "set_conditional_formatting",
    "Colour the cells of a layer's attribute table by rules: each rule is a QGIS expression condition (@value is the cell's value, or use any field) and a background_color and/or "
    "text_color, for one field, or for whole rows when `field` is left out. For example {\"condition\": \"@value > 1000\", \"background_color\": \"#ffcccc\"}. The rules replace the ones "
    "already set for that field (or the row rules); an empty list is not accepted, use clear true to remove them. Stored with the project, not in the data file. Display only: no data changes.",
    {"type": "object", "properties": {
        "layer_name": {"type": "string", "description": "The vector layer."},
        "field": {"type": "string", "description": "The field to colour; leave out to colour whole rows."},
        "rules": {"type": "array", "items": {"type": "object"}, "description": "[{condition, background_color, text_color, name}], 1 to 20 rules, the first that matches wins."},
        "clear": {"type": "boolean", "description": "true: remove the rules of that field (or the row rules) instead of setting any."}},
     "required": ["layer_name"]},
    keywords=["conditional formatting", "colour the cells", "color the cells", "highlight cells in the attribute table", "highlight the values above", "format the table cells", "colour rows in the table"],
)
def set_conditional_formatting(layer_name, rules=None, field=None, clear=False):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    layer, err = _layer(layer_name)
    if err:
        return err
    if field is not None and layer.fields().indexOf(str(field)) < 0:
        return {"error": f"Field '{field}' not found in '{layer_name}'."}
    target = layer.conditionalStyles()
    before = len(target.fieldStyles(str(field))) if field is not None else len(target.rowStyles())
    if clear:
        built = []
    else:
        problem = dr.check_formatting(rules)
        if problem:
            return {"error": problem}
        built, why = _styles(rules)
        if why:
            return {"error": why}
    if field is not None:
        target.setFieldStyles(str(field), built)
        now = len(target.fieldStyles(str(field)))
    else:
        target.setRowStyles(built)
        now = len(target.rowStyles())
    return {"success": True, "layer_name": layer_name, "field": field, "rules_before": before, "rules_now": now,
            "note": PROJECT_NOTE + " It shows in the attribute table; this changes no data."}


@register_tool(
    "set_map_tip",
    "Set the map tip of a layer: the HTML bubble shown when the pointer rests on a feature, written with [% expression %] fields, for example '<b>[% \"name\" %]</b><br>Population [% \"pop\" %]'. "
    "Only plain HTML and expression fields are allowed: script, frame, object, embed, form, link, meta and base tags, event handlers and javascript: addresses are refused. An empty template "
    "removes the tip. Stored with the project. Map tips only show while View > Show Map Tips is on, which this tool does not change.",
    {"type": "object", "properties": {
        "layer_name": {"type": "string", "description": "The vector layer."},
        "template": {"type": "string", "description": "HTML with [% expression %] fields; empty text removes the map tip."}},
     "required": ["layer_name", "template"]},
    keywords=["map tip", "map tips", "hover text", "tooltip on the map", "show a popup when hovering", "what shows when I hover over a feature", "hover over a feature"],
)
def set_map_tip(layer_name, template):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    problem = dr.check_map_tip(template)
    if problem:
        return {"error": problem}
    layer, err = _layer(layer_name)
    if err:
        return err
    expressions = dr.map_tip_expressions(template)
    for expression in expressions:
        problem = _expression_ok(expression)
        if problem:
            return {"error": f"The expression [% {expression[:60]} %] was not accepted: {problem}"}
    before = layer.mapTipTemplate()
    layer.setMapTipTemplate(template)
    return {"success": True, "layer_name": layer_name, "map_tip_now": layer.mapTipTemplate(), "had_a_map_tip_before": bool(before), "expressions": len(expressions),
            "note": PROJECT_NOTE + " The tip shows only while View > Show Map Tips is on."}


@register_tool(
    "add_feature_action",
    "Add an action to a layer's feature action menu that OPENS A WEB ADDRESS built from the feature's values (action_type open_url, url starting with http:// or https://, with "
    "[% expression %] fields, for example https://en.wikipedia.org/wiki/[% \"name\" %]). Actions that run a command, Python code or a program are REFUSED by policy: they run on the "
    "user's computer on every click. Stored with the project.",
    {"type": "object", "properties": {
        "layer_name": {"type": "string", "description": "The vector layer."},
        "name": {"type": "string", "description": "The label shown in the action menu."},
        "action_type": {"type": "string", "description": "open_url (the only type that is added; command types are refused)."},
        "url": {"type": "string", "description": "http(s) address, may contain [% expression %] fields."}},
     "required": ["layer_name", "name", "action_type"]},
    keywords=["layer action", "add an action to the layer", "feature action", "run a command on click", "action on click", "open a url for the feature", "run a script when I click", "open a web page for the feature"],
)
def add_feature_action(layer_name, name, action_type, url=None):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    problem = dr.check_action(name, action_type, url)
    if problem:
        return {"error": problem}
    layer, err = _layer(layer_name)
    if err:
        return err
    address = str(url).strip()
    for expression in dr.map_tip_expressions(address):
        problem = _expression_ok(expression)
        if problem:
            return {"error": f"The expression [% {expression[:60]} %] in the url was not accepted: {problem}"}
    kinds = getattr(Qgis, "AttributeActionType", None) or QgsAction.ActionType            # QGIS 4 / QGIS 3 spelling of the same enum
    layer.actions().addAction(QgsAction(kinds.OpenUrl, str(name).strip(), address))
    names = [a.name() for a in layer.actions().actions()]
    return {"success": True, "layer_name": layer_name, "action": str(name).strip(), "url": address, "actions_now": names,
            "note": PROJECT_NOTE + " It opens a page; it runs nothing."}
