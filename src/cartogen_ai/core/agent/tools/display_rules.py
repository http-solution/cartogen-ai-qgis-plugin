"""Conditional formatting, map tips and layer actions helpers (PLAN-023 R10-2): the request checks, pure Python (no QGIS, no numpy).

layer_display_tools.py applies them through QGIS (QgsConditionalStyle, setMapTipTemplate, QgsAction); what can be checked offline is here.

Policy, stated once: the assistant never makes QGIS RUN A COMMAND. A layer action that runs Python, a shell command or a program (QGIS's Python, Windows, Mac and Unix action types) is
refused with the reason; the only action it will add opens a web address (http or https) built from the feature's own values, which opens a page and runs nothing. A map tip is HTML
with [% expression %] fields only: script, frame, object, embed, form, link, meta and base tags, event-handler attributes and javascript:, vbscript: and data: addresses are refused, and
every expression inside goes through the same expression screen as every other tool. Known answers (the tests): a template with a <script> tag is refused, the two expressions of
'<b>[% "name" %]</b> [% "pop" * 2 %]' are read as "name" and "pop" * 2, a python action is refused with a reason that names command execution."""
import re

MAX_RULES = 20
MAX_TEMPLATE = 4000
MAX_URL = 1000
ACTION_ALLOWED = "open_url"
ACTION_REFUSED = {"python", "generic", "script", "shell", "command", "cmd", "bash", "exec", "program", "windows", "mac", "unix", "submit_url", "submit"}
_COLOR = re.compile(r"^(#[0-9a-fA-F]{6}|#[0-9a-fA-F]{8}|[a-zA-Z]{3,20})$")
_FIELD_EXPR = re.compile(r"\[%(.*?)%\]", re.DOTALL)
_BAD_TAG = re.compile(r"<\s*/?\s*(script|iframe|frame|frameset|object|embed|applet|form|link|meta|base)\b", re.IGNORECASE)
_EVENT = re.compile(r"\bon[a-z]{3,20}\s*=", re.IGNORECASE)
_BAD_URL = re.compile(r"(javascript|vbscript|data)\s*:", re.IGNORECASE)


def map_tip_expressions(template):
    """The expressions written as [% ... %] in `template`, stripped. Pure."""
    return [m.strip() for m in _FIELD_EXPR.findall(str(template or ""))]


def check_map_tip(template):
    """Error text when a map tip template cannot be used, else None. An empty template is allowed (it removes the tip). Pure."""
    if not isinstance(template, str):
        return "template must be text (HTML with [% expression %] fields; empty removes the map tip)."
    if len(template) > MAX_TEMPLATE:
        return f"The template is longer than {MAX_TEMPLATE} characters."
    if _BAD_TAG.search(template):
        return "The template has a script, frame, object, embed, form, link, meta or base tag, which a map tip may not use. Use plain HTML (text, bold, tables, images) and [% expression %] fields."
    if _EVENT.search(template):
        return "The template has an event-handler attribute (onclick=, onload=, ...), which a map tip may not use."
    if _BAD_URL.search(template):
        return "The template has a javascript:, vbscript: or data: address, which a map tip may not use."
    return None


def check_formatting(rules):
    """Error text for a conditional-formatting rule list that cannot be used, else None. Each rule: {condition, background_color?, text_color?, name?}; at least one colour. Pure."""
    if not isinstance(rules, list) or not 1 <= len(rules) <= MAX_RULES:
        return f"rules must be a list of 1 to {MAX_RULES} rules like {{\"condition\": \"@value > 100\", \"background_color\": \"#ffcccc\"}}."
    for i, rule in enumerate(rules, 1):
        if not isinstance(rule, dict):
            return f"rule {i} must be an object with a condition and a colour."
        condition = rule.get("condition")
        if not isinstance(condition, str) or not condition.strip() or len(condition) > 500:
            return f"rule {i} needs a condition: a QGIS expression (use @value for the cell's value), at most 500 characters."
        colours = [rule.get(k) for k in ("background_color", "text_color") if rule.get(k) is not None]
        if not colours:
            return f"rule {i} needs a background_color and/or a text_color."
        if any(not isinstance(c, str) or not _COLOR.match(c.strip()) for c in colours):
            return f"rule {i}: a colour is a name (red) or a hex code (#ff0000)."
        if rule.get("name") is not None and (not isinstance(rule["name"], str) or len(rule["name"]) > 60):
            return f"rule {i}: name must be text of at most 60 characters."
    return None


def check_action(name, action_type, url):
    """Error text for a layer-action request that must not or cannot be run, else None. Only the open_url type is ever added; the command types are refused with the policy. Pure."""
    kind = str(action_type or "").strip().lower()
    if kind in ACTION_REFUSED:
        return ("Refused: this assistant does not add layer actions that run a command, Python code or a program (that is a policy, not a missing feature), because such an action "
                "runs on the user's computer every time someone clicks a feature. What it can add is an open_url action, which opens a web address built from the feature's values.")
    if kind != ACTION_ALLOWED:
        return f"action_type must be {ACTION_ALLOWED} (the command types are refused by policy)."
    if not isinstance(name, str) or not name.strip() or len(name) > 60:
        return "name must be text of 1 to 60 characters: the label shown in the action menu."
    if not isinstance(url, str) or len(url) > MAX_URL or not re.match(r"^https?://", url.strip(), re.IGNORECASE):
        return "url must start with http:// or https:// (it may contain [% expression %] fields) and be at most 1000 characters."
    if re.search(r"\s", _FIELD_EXPR.sub("", url.strip())):
        return "url must not contain spaces outside [% expression %] fields."
    return None
