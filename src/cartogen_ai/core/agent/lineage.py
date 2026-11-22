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
from ..logger import log_event

LINEAGE_PROPERTY_KEY = PROJECT_PROPERTY_LINEAGE
LINEAGE_UNREADABLE_COPY_KEY = PROJECT_PROPERTY_LINEAGE + "_unreadable_copy"
UNREADABLE_LINEAGE_TOOL = "lineage_unreadable"


def unreadable_lineage_entry():
    """The entry that stands in for a lineage history that cannot be read. Its `unreadable` flag is what the protection check looks for: a layer
    whose ancestry is unknown is treated as protected (owner decision 2026-11-22), instead of its history being dropped and the layer looking
    open. The entry names no sources; it only records that they are unknown. Pure apart from the clock."""
    return {"tool": UNREADABLE_LINEAGE_TOOL, "params": {}, "sources": [], "source_ids": [], "unreadable": True,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")}


def lineage_is_unreadable(entries):
    """True when any entry stands in for an unreadable history. Pure."""
    return any(isinstance(e, dict) and e.get("unreadable") for e in entries or [])


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


def source_layer_ids(source_names, layers):
    """Ids of every loaded layer whose name is in `source_names` (all layers sharing a name, not just the first). Pure over
    (name, id) pairs: `layers` is any iterable of objects with name() and id()."""
    wanted = set(source_names or [])
    return sorted(layer.id() for layer in layers if layer.name() in wanted)


def effective_source_names(entry, layers):
    """The loaded-layer names a lineage entry's sources point at NOW (GitHub #150). A source recorded by name goes stale when the
    layer is renamed, and a derived output of a protected layer would then look open to the egress gate; the recorded ids still
    resolve to the renamed layer. The recorded names are kept too (a name now held by another layer is judged by the gate's
    strictest-layer rule), so this only ever adds names. Pure over name()/id() objects."""
    names = [s for s in (entry.get("sources") or []) if isinstance(s, str)]
    by_id = {layer.id(): layer.name() for layer in layers}
    for sid in entry.get("source_ids") or []:
        current = by_id.get(sid)
        if current and current not in names:
            names.append(current)
    return names


def tag_layer_lineage(layer, tool_name: str, params: dict, source_layers: list | None = None, source_ids: list | None = None, extra: dict | None = None) -> bool:
    """Attaches tool execution lineage metadata to a layer's custom properties. `extra` adds fields to the entry (PLAN-048: the workflow file a run came from)."""
    if not QGIS_AVAILABLE or layer is None:
        return False

    try:
        existing_raw = layer.customProperty(LINEAGE_PROPERTY_KEY, "[]")
        history = []
        if isinstance(existing_raw, str) and existing_raw.strip():
            try:
                history = json.loads(existing_raw)
                if not isinstance(history, list):
                    raise ValueError("the stored lineage is not a list")
            except Exception as exc:
                # A corrupt history used to be replaced by an empty one, which dropped the earlier sources that carry protection to a derived
                # layer. Now the corrupt text is kept under a second property and the history restarts with an "unreadable" entry, so the layer
                # stays protected until someone re-tags it (owner decision 2026-11-22: fail closed).
                log_event("lineage_history_unreadable", tag="LineageEngine", error_class=type(exc).__name__)
                layer.setCustomProperty(LINEAGE_UNREADABLE_COPY_KEY, existing_raw)
                history = [unreadable_lineage_entry()]

        entry = {
            "tool": tool_name,
            "params": params,
            "sources": source_layers or [],
            "source_ids": source_ids or [],
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        if extra:
            entry.update({k: v for k, v in extra.items() if k not in entry})

        history.append(entry)
        layer.setCustomProperty(LINEAGE_PROPERTY_KEY, json.dumps(history))
        return True
    except Exception as e:
        log_event("failed_to_tag_layer_lineage", tag="LineageEngine", error_class=type(e).__name__, error=True)
        return False


def get_layer_lineage(layer) -> list:
    """Reads layer lineage history list."""
    if not QGIS_AVAILABLE or layer is None:
        return []

    try:
        raw = layer.customProperty(LINEAGE_PROPERTY_KEY, "[]")
        if isinstance(raw, str) and raw.strip():
            history = json.loads(raw)
            if not isinstance(history, list):
                raise ValueError("the stored lineage is not a list")
            return history
    except Exception as e:
        log_event("failed_to_read_layer_lineage", tag="LineageEngine", error_class=type(e).__name__, error=True)
        return [unreadable_lineage_entry()]       # a history that is stored but unreadable is not "no history": see unreadable_lineage_entry
    return []
