"""
Registry for Cartogen AI tools. Provides @register_tool decorator to register
functions along with their OpenAI-compatible schema definitions.
"""

import functools
import re

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


def register_tool(name, description, parameters, keywords=()):
    """
    Decorator to register a function into the global tool registry and schema list.

    :param name: Unique name of the tool function.
    :param description: High-level description of what the tool does.
    :param parameters: JSON schema dictionary of input parameters.
    :param keywords: lower-case phrases users say for this tool that share no word with its name or description; the router scores them
        like the curated aliases in tool_router._TOOL_ALIASES (a phrase may be in either place, not both).
    """
    def decorator(func):
        TOOL_REGISTRY[name] = _refuse_wrong_layer_kind(name, func)
        if keywords:
            TOOL_KEYWORDS[name] = tuple(keywords)
        TOOLS_SCHEMA.append({
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": parameters,
            },
        })
        return func
    return decorator


def get_tool_registry():
    return TOOL_REGISTRY


def get_tools_schema():
    return TOOLS_SCHEMA
