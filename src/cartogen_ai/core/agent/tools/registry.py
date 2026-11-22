"""
Registry for Cartogen AI tools. Provides @register_tool decorator to register
functions along with their OpenAI-compatible schema definitions.
"""

import functools
import inspect
import re
import types
import typing

TOOL_REGISTRY: dict = {}
TOOLS_SCHEMA: list = []
# Routing-only phrases a tool declares next to its own definition (PLAN-042 step 2). Never sent to the model: they are not part of the schema.
TOOL_KEYWORDS: dict = {}

# "'QgsRasterLayer' object has no attribute 'fields'": a tool that looked a layer up by name and got a layer of the other kind.
_WRONG_LAYER_KIND = re.compile(r"'Qgs(Raster|Vector|Mesh|PointCloud|VectorTile|Annotation|TiledScene)Layer' object has no attribute '(\w+)'")


def _refuse_wrong_layer_kind(name, func):
    """The function as the registry calls it: an AttributeError that means "this layer is not the kind the tool works on" becomes an
    error result that says so, instead of "Execution failed". Found by tests/test_every_tool_live.py (hostile pass, 2026-10-26): 28
    tools raised it when a raster was named where a vector layer is needed. A safety net for the whole class, not a substitute for a
    tool checking its own input where it can say more; any other exception passes through unchanged."""
    @functools.wraps(func)
    def guarded(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except AttributeError as e:
            match = _WRONG_LAYER_KIND.search(str(e))
            if not match:
                raise
            kind = {"VectorTile": "vector tile", "PointCloud": "point cloud", "TiledScene": "3D tiles"}.get(match.group(1), match.group(1).lower())
            return {"error": (f"{name} was given a {kind} layer, which has no '{match.group(2)}': it works on a different kind of layer "
                              "(for example a vector layer of features, or a raster). Check the layer names with get_layers and pass "
                              "a layer of the right kind.")}
    return guarded


_JSON_TYPES = {str: "string", int: "integer", float: "number", bool: "boolean", dict: "object"}
# Arguments a write tool takes but must NEVER advertise to the model: the dispatcher strips anything outside the schema, which is what stops a model
# injecting confirmed=True (tests/test_analysis_tools.py, test_dispatcher_schema_filtering_prevents_bypass_for_severity_index). A derived schema leaves
# them out for the same reason.
UNADVERTISED_ARGUMENTS = frozenset({"confirmed"})


def _json_type(hint, where):
    """The JSON-schema fragment for one type hint: str, int, float, bool, dict, list[X], Optional[X], Literal[...]. Anything else raises, so a tool
    cannot be registered with a guessed type."""
    origin, args = typing.get_origin(hint), typing.get_args(hint)
    if origin is typing.Union or origin is types.UnionType:
        inner = [a for a in args if a is not type(None)]
        if len(inner) == 1:
            return _json_type(inner[0], where)
    if origin is typing.Literal:
        kinds = {type(a) for a in args}
        if len(kinds) == 1 and kinds <= {str, int}:
            return {"type": _JSON_TYPES[kinds.pop()], "enum": list(args)}
    if origin is list:
        return {"type": "array", "items": _json_type(args[0], where)} if args else {"type": "array"}
    if hint is list:
        return {"type": "array"}
    if hint in _JSON_TYPES:
        return {"type": _JSON_TYPES[hint]}
    raise TypeError(f"{where}: the type {hint!r} cannot be turned into a tool schema; use str, int, float, bool, dict, list[X], Optional[X] or Literal")


def schema_from_signature(func, arg_docs, hidden=()):
    """The JSON schema `register_tool` uses when a tool is registered without a hand-written one (PLAN-033 item 4, LEAD-4): built from the function
    signature and its type hints, so an argument cannot exist in the function and not in the schema, or the reverse.

    Rules, all enforced by raising at import time rather than guessing: every offered argument has a type hint and a one-line description in
    `arg_docs`; `arg_docs` names no argument the function lacks; an argument with no default is required; a plain default (str, int, float, bool)
    is recorded as the property's "default". `confirmed` and anything in `hidden` stay in the function but out of the schema (UNADVERTISED_ARGUMENTS).
    *args and **kwargs are refused, since they would be arguments the schema cannot name.
    NEW tools only: the existing hand-written schemas are not converted, and their descriptions are not touched."""
    where = func.__name__
    params = inspect.signature(func).parameters
    for p in params.values():
        if p.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            raise TypeError(f"{where}: *args and **kwargs cannot be described by a derived schema")
    skipped = UNADVERTISED_ARGUMENTS | set(hidden)
    offered = [n for n in params if n not in skipped]
    unknown = sorted(set(arg_docs) - set(offered))
    if unknown:
        raise TypeError(f"{where}: arg_docs names arguments the function does not offer: {unknown}")
    undocumented = [n for n in offered if not str(arg_docs.get(n, "")).strip()]
    if undocumented:
        raise TypeError(f"{where}: every offered argument needs a description in arg_docs; missing: {undocumented}")
    hints = typing.get_type_hints(func)
    properties, required = {}, []
    for name in offered:
        if name not in hints:
            raise TypeError(f"{where}: argument {name!r} has no type hint")
        prop = _json_type(hints[name], f"{where}({name})")
        prop["description"] = str(arg_docs[name]).strip()
        default = params[name].default
        if default is inspect.Parameter.empty:
            required.append(name)
        elif type(default) in (str, int, float, bool):
            prop["default"] = default
        properties[name] = prop
    return {"type": "object", "properties": properties, "required": required}


def register_tool(name, description, parameters=None, keywords=(), *, arg_docs=None, hidden=()):
    """
    Decorator to register a function into the global tool registry and schema list.

    :param name: Unique name of the tool function.
    :param description: High-level description of what the tool does.
    :param parameters: JSON schema dictionary of input parameters. Leave it out (None) on a NEW tool to have it built from the function signature and
        type hints with `arg_docs`; see schema_from_signature. Existing tools keep their hand-written schemas.
    :param arg_docs: with no `parameters`, {argument: one-line description for the model}, required for every offered argument.
    :param hidden: with no `parameters`, extra argument names kept out of the schema (`confirmed` is always kept out).
    :param keywords: lower-case phrases users say for this tool that share no word with its name or description; the router scores them
        ("concept:<name>" pulls in a shared group from core/services/routing_concepts.json). Keep the why-comment above the list.
    """
    def decorator(func):
        schema = parameters if parameters is not None else schema_from_signature(func, arg_docs or {}, hidden)
        TOOL_REGISTRY[name] = _refuse_wrong_layer_kind(name, func)
        if keywords:
            TOOL_KEYWORDS[name] = tuple(keywords)
        TOOLS_SCHEMA.append({
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": schema,
            },
        })
        return func
    return decorator


def get_tool_registry():
    return TOOL_REGISTRY


def get_tools_schema():
    return TOOLS_SCHEMA
