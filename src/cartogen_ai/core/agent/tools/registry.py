# -*- coding: utf-8 -*-
"""
Registry for Cartogen AI tools. Provides @register_tool decorator to register
functions along with their OpenAI-compatible schema definitions.
"""

TOOL_REGISTRY = {}
TOOLS_SCHEMA = []


def register_tool(name, description, parameters):
    """
    Decorator to register a function into the global tool registry and schema list.

    :param name: Unique name of the tool function.
    :param description: High-level description of what the tool does.
    :param parameters: JSON schema dictionary of input parameters.
    """
    def decorator(func):
        TOOL_REGISTRY[name] = func
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
