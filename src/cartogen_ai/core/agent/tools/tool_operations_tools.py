# -*- coding: utf-8 -*-
"""
Agent-facing introspection over the READ/CREATE/MODIFY/DELETE/PUBLISH
taxonomy in agent/tool_operations.py (point 20 of
docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md). Both tools here
are pure lookups over that static, hand-reviewed dict -- they never touch
QGIS or the live project, hence both are READ themselves.
"""

from .registry import register_tool
from .. import tool_operations as _ops


@register_tool(
    "get_tool_operation_type",
    "Look up which operation-type category (READ, CREATE, MODIFY, DELETE, or PUBLISH) a "
    "registered Cartogen AI tool falls into -- e.g. before deciding whether a planned call is "
    "safe to make without asking first. Returns an error if the name isn't a registered tool.",
    {
        "type": "object",
        "properties": {
            "tool_name": {"type": "string", "description": "Exact registered tool name, e.g. 'remove_layer'."},
        },
        "required": ["tool_name"],
    },
)
def get_tool_operation_type(tool_name: str):
    op = _ops.get_tool_operation_type(tool_name)
    if op is None:
        return {"error": f"'{tool_name}' is not a registered tool name."}
    return {"tool_name": tool_name, "operation_type": op}


@register_tool(
    "list_tools_by_operation_type",
    "List every registered tool classified under one operation-type category (READ, CREATE, "
    "MODIFY, DELETE, or PUBLISH). Use this to see, for example, every tool that can write an "
    "external file (PUBLISH) or remove/replace project state (DELETE).",
    {
        "type": "object",
        "properties": {
            "operation_type": {
                "type": "string",
                "enum": sorted(_ops.VALID_OPERATION_TYPES),
                "description": "One of READ, CREATE, MODIFY, DELETE, PUBLISH.",
            },
        },
        "required": ["operation_type"],
    },
)
def list_tools_by_operation_type(operation_type: str):
    try:
        names = _ops.list_tools_by_operation_type(operation_type)
    except ValueError as e:
        return {"error": str(e)}
    return {"operation_type": operation_type, "tool_names": names, "count": len(names)}
