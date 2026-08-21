# -*- coding: utf-8 -*-
"""
Layer Metadata and Lineage Tracking Engine for Cartogen AI.
Tags modified or generated layers with tool lineage, parameters, source layers, and execution timestamps.
"""

import json
import time

try:
    from qgis.core import QgsProject
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False

LINEAGE_PROPERTY_KEY = "cartogen_ai/lineage"


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
