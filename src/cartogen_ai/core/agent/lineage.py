# -*- coding: utf-8 -*-
"""
Layer Metadata and Lineage Tracking Engine for Cartogen AI.
Tags modified or generated layers with tool lineage, parameters, source layers, and execution timestamps.
"""

import json
import time

try:
    from qgis.core import QgsProject  # noqa: F401 -- import used only to gate QGIS_AVAILABLE
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False

from ...infrastructure.settings_keys import PROJECT_PROPERTY_LINEAGE

LINEAGE_PROPERTY_KEY = PROJECT_PROPERTY_LINEAGE


# --- which layers a call read, and which it made (GitHub #150, audit F14) ---------------------------------------------------------
# Sources used to be "top-level string arguments whose KEY contains 'layer'", so list inputs (raster_layers, layer_names_list),
# nested Processing params and the layers named inside SQL were never recorded, and only a result's "layer_name" was ever tagged;
# an output with no ancestry looks open to the egress gate. Both now use the same value-based rule as the gate.
_CREATED_KEY_HINTS = ("layer", "layers_created", "output", "route")


def derive_sources(tool_name, arguments, known_names):
    """Sorted names of the loaded layers a tool call read: every string equal to a loaded layer name, anywhere in the arguments
    (lists and nested objects included), plus the layers named in a SQL query. Pure."""
    from ..models.egress_gate import argument_layer_names
    names, _unresolved = argument_layer_names(tool_name, arguments, list(known_names))
    return sorted(names)


def created_layer_names(result, sources, known_names):
    """Names of the loaded layers a tool result says it created: any top-level result value under a key that mentions a layer or
    output, as a string or a list of strings, that is a loaded layer and is NOT one of the call's own sources (a result that
    echoes its input layer must not be tagged as derived from itself). Order kept, duplicates dropped. Pure."""
    if not isinstance(result, dict):
        return []
    known, skip = set(known_names), set(sources or [])
    out = []
    for key, value in result.items():
        if not any(h in str(key).lower() for h in _CREATED_KEY_HINTS):
            continue
        values = value if isinstance(value, (list, tuple)) else [value]
        for v in values:
            if isinstance(v, str) and v in known and v not in skip and v not in out:
                out.append(v)
    return out


def tag_layer_lineage(layer, tool_name: str, params: dict, source_layers: list = None) -> bool:
    """Attaches tool execution lineage metadata to a layer's custom properties."""
    if not QGIS_AVAILABLE or layer is None:
        return False

    try:
        existing_raw = layer.customProperty(LINEAGE_PROPERTY_KEY, "[]")
        history = []
        if isinstance(existing_raw, str) and existing_raw.strip():
            try:
                history = json.loads(existing_raw)
            except Exception:
                history = []

        entry = {
            "tool": tool_name,
            "params": params,
            "sources": source_layers or [],
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        }

        history.append(entry)
        layer.setCustomProperty(LINEAGE_PROPERTY_KEY, json.dumps(history))
        return True
    except Exception as e:
        print(f"[LineageEngine] Failed to tag layer lineage: {e}")
        return False


def get_layer_lineage(layer) -> list:
    """Reads layer lineage history list."""
    if not QGIS_AVAILABLE or layer is None:
        return []

    try:
        raw = layer.customProperty(LINEAGE_PROPERTY_KEY, "[]")
        if isinstance(raw, str) and raw.strip():
            return json.loads(raw)
    except Exception as e:
        print(f"[LineageEngine] Failed to read layer lineage: {e}")
    return []
