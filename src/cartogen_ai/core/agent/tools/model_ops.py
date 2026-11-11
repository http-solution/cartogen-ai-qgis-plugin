"""Processing model (.model3) reading and the approval check (PLAN-023 R11-1), pure Python (no QGIS, no numpy).

run_processing_model (model_tool.py) runs a model the user built in QGIS's graphical modeler. A model is a small program: a chain of Processing algorithms whose parameters can hold
expressions. The rule here is the same as for run_allowlisted_processing_algorithm, applied to every step: a model is REFUSED unless EVERY algorithm it contains is on the approved
list, and the refusal names the first one that is not. In detail:

* the file is read as XML text, at most MAX_BYTES, with any XML entity declaration refused (an entity bomb cannot be parsed);
* every algorithm id found anywhere in the file must be on the approved list (a nested model, `model:...`, and a Python script, `script:...`, are never on it);
* a child algorithm whose id cannot be read at all makes the whole model refused (fail closed: an unknown layout is not trusted);
* an algorithm that changes the user's own layer (a selection) is refused inside a model;
* every parameter goes through the same parameter_violation check as the single-algorithm tool (no FORMULA, no EXTRA, no raw backend text), and every expression a child takes goes through
  the expression screen, so eval(), env() and file functions are refused;
* at most MAX_CHILDREN steps.
The tool then checks the ids a SECOND time from QGIS's own parse of the file and refuses on any disagreement with this parse. Known answers (the tests): a model of native:buffer then
native:centroids is accepted; a model with script:anything is refused naming it; a child that calls eval() is refused naming the child."""
import re
from xml.etree import ElementTree

from ...validators.expression_screen import screen_expression
from ._processing_allowlist import ALLOWED_ALGORITHM_IDS, MUTATES_INPUT_ALGORITHM_IDS, parameter_violation

MAX_BYTES = 1_000_000
MAX_CHILDREN = 30
ALGORITHM_KEYS = ("alg_id", "algorithm_id")
_ENTITY = re.compile(r"<!\s*ENTITY", re.IGNORECASE)


def _convert(element):
    """The Python value of one <Option> element: a dict for a Map, a list for a List, else the value attribute text. Pure."""
    kind = element.get("type", "")
    if kind == "Map":
        return {child.get("name", ""): _convert(child) for child in element}
    if kind == "List":
        return [_convert(child) for child in element]
    return element.get("value", "")


def parse_model(text):
    """(model dict, error text): {'name', 'children': [{'id', 'algorithm', 'description', 'parameters': {name: [source dicts]}}], 'algorithm_ids': sorted set of every id found, 'inputs': [...]}.
    The error text is returned for a file that is too big, declares an XML entity, is not XML, or has no children. Pure."""
    if not isinstance(text, str) or not text.strip():
        return None, "The model file is empty."
    if len(text.encode("utf-8", "replace")) > MAX_BYTES:
        return None, f"The model file is larger than {MAX_BYTES // 1000} KB, which is more than a model made in the modeler needs."
    if _ENTITY.search(text):
        return None, "The model file declares an XML entity, which a model made by QGIS never does; it is not read."
    try:
        root = ElementTree.fromstring(text)  # noqa: S314 -- entity declarations were refused above, the size is capped, and expat fetches no external entity or DTD; defusedxml is not shipped with QGIS
    except ElementTree.ParseError as e:
        return None, f"The model file is not valid XML ({str(e)[:80]})."
    if root.tag != "Option" or root.get("type") != "Map":
        return None, "This does not look like a QGIS model file (.model3)."
    try:
        data = _convert(root)
    except RecursionError:
        return None, "The model file is nested far deeper than a model made in the modeler ever is; it is not read."
    children_map = data.get("children")
    if not isinstance(children_map, dict) or not children_map:
        return None, "The model has no steps (no child algorithms), so there is nothing to run."
    children, found = [], set()
    for child_id, child in children_map.items():
        algorithm = next((child.get(k) for k in ALGORITHM_KEYS if isinstance(child, dict) and isinstance(child.get(k), str) and child.get(k)), None)
        if algorithm is None:
            return None, f"Step '{child_id}' of the model has no algorithm id that can be read, so the model is refused (an unknown layout is not trusted)."
        params = child.get("params", {}) if isinstance(child.get("params"), dict) else {}
        children.append({"id": child_id, "algorithm": algorithm, "description": str(child.get("component_description") or child.get("description") or child_id),
                         "parameters": {name: [s for s in sources if isinstance(s, dict)] for name, sources in params.items() if isinstance(sources, list)}})
        found.add(algorithm)
    try:
        found |= _all_algorithm_ids(data)
    except RecursionError:
        return None, "The model file is nested far deeper than a model made in the modeler ever is; it is not read."
    inputs = data.get("parameters") if isinstance(data.get("parameters"), dict) else {}
    return {"name": str(data.get("model_name") or data.get("name") or ""), "children": children, "algorithm_ids": sorted(found), "inputs": sorted(inputs)}, None


def _all_algorithm_ids(value):
    """Every string stored under an algorithm-id key anywhere in the converted file. Pure."""
    found = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key in ALGORITHM_KEYS and isinstance(item, str) and item:
                found.add(item)
            else:
                found |= _all_algorithm_ids(item)
    elif isinstance(value, list):
        for item in value:
            found |= _all_algorithm_ids(item)
    return found


def not_approved(algorithm_ids):
    """The first id (sorted) that is not on the approved list, with the reason, as (id, reason); None when all are approved. Pure."""
    for alg_id in sorted(algorithm_ids):
        if alg_id.startswith(("model:", "script:")) or ":" not in alg_id:
            kind = "another model" if alg_id.startswith("model:") else "a Python script" if alg_id.startswith("script:") else "an unknown kind of algorithm"
            return alg_id, f"'{alg_id}' is {kind}, which a model run here may not contain."
        if alg_id in MUTATES_INPUT_ALGORITHM_IDS:
            return alg_id, f"'{alg_id}' changes the user's own layer (a selection), which a model run here may not do."
        if alg_id not in ALLOWED_ALGORITHM_IDS:
            return alg_id, f"'{alg_id}' is not on the approved algorithm list."
    return None


def check_model(model):
    """The refusal text for a parsed model, or None when it may run. Names the step and the algorithm. Pure."""
    if len(model["children"]) > MAX_CHILDREN:
        return f"The model has {len(model['children'])} steps; more than {MAX_CHILDREN} is not run here."
    bad = not_approved(model["algorithm_ids"])
    if bad:
        step = next((c for c in model["children"] if c["algorithm"] == bad[0]), None)
        where = f" (step '{step['description']}')" if step else ""
        return f"Model refused: {bad[1]}{where}"
    for child in model["children"]:
        text = _child_violation(child)
        if text:
            return f"Model refused: step '{child['description']}' ({child['algorithm']}): {text}"
    return None


def _child_violation(child):
    """The first problem in one step's parameters, or None. Static values go through parameter_violation; every expression goes through the expression screen. Pure."""
    static = {}
    for name, sources in child["parameters"].items():
        for source in sources:
            for key, value in source.items():
                if "expression" in key.lower() and isinstance(value, str) and value.strip():
                    blocked = screen_expression(value)
                    if blocked:
                        return f"parameter {name}: {blocked}"
                if key == "static_value":
                    static[name] = value
    for name in child["parameters"]:
        static.setdefault(name, "")
    return parameter_violation(child["algorithm"], static)


def input_help(model_inputs):
    """'INPUT, DISTANCE' style listing for an error message. Pure."""
    return ", ".join(model_inputs) if model_inputs else "(the model has no inputs)"
